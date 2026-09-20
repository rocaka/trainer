import SwiftUI
import Security

final class GitHubNoRedirect: NSObject, URLSessionTaskDelegate {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) {
        completionHandler(nil)
    }
}

enum GitHubCredential {
    static let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
        kSecAttrService as String: "com.trainer.github", kSecAttrAccount as String: "oauth"]
    static func read() throws -> String? {
        var result: CFTypeRef?
        let status = SecItemCopyMatching(query.merging([kSecReturnData as String: true]) { _, new in new } as CFDictionary, &result)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess, let data = result as? Data, let value = String(data: data, encoding: .utf8) else {
            throw GitHubFailure("无法读取 GitHub 钥匙串凭据。")
        }
        return value
    }
    static func save(_ token: String) throws {
        let data = Data(token.utf8)
        var status = SecItemUpdate(query as CFDictionary, [kSecValueData as String: data] as CFDictionary)
        if status == errSecItemNotFound {
            status = SecItemAdd(query.merging([kSecValueData as String: data,
                kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly]) { _, new in new } as CFDictionary, nil)
        }
        guard status == errSecSuccess else { throw GitHubFailure("无法保存 GitHub 钥匙串凭据。") }
    }
    static func remove() throws {
        let status = SecItemDelete(query as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else { throw GitHubFailure("无法删除本机 GitHub 凭据。") }
    }
}

struct GitHubFailure: LocalizedError {
    let message: String
    init(_ message: String) { self.message = message }
    var errorDescription: String? { message }
}

struct GitHubDevice: Decodable {
    let device_code, user_code, verification_uri: String
    let expires_in, interval: Int
}
struct GitHubToken: Decodable {
    let access_token: String?
    let error: String?
}
struct GitHubGraph: Decodable {
    let data: Payload?
    let errors: [GraphError]?
    struct GraphError: Decodable { let message: String }
    struct Payload: Decodable { let viewer: Viewer }
    struct Viewer: Decodable {
        let login: String
        let contributionsCollection: Contributions
        let repositories: Repositories
    }
    struct Contributions: Decodable {
        let totalCommitContributions, totalPullRequestContributions, totalIssueContributions: Int
        let contributionCalendar: CalendarData
    }
    struct CalendarData: Decodable { let totalContributions: Int; let weeks: [Week] }
    struct Week: Decodable { let contributionDays: [Day] }
    struct Repositories: Decodable { let nodes: [Repository] }
    struct Repository: Decodable { let languages: Languages }
    struct Languages: Decodable { let edges: [LanguageEdge] }
    struct LanguageEdge: Decodable { let size: Int; let node: Language }
    struct Language: Decodable { let name: String }
    struct Day: Decodable {
        let date: String
        let contributionCount: Int
        var intensity: Double { contributionCount == 0 ? 0.08 : min(0.95, 0.25 + Double(contributionCount) * 0.07) }
    }
}

enum GitHubOAuthConfig {
    static var clientID: String {
        let bundled = (Bundle.main.object(forInfoDictionaryKey: "TrainerGitHubClientID") as? String ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        #if DEBUG
        return bundled.isEmpty ? (ProcessInfo.processInfo.environment["TRAINER_GITHUB_CLIENT_ID"] ?? "") : bundled
        #else
        return bundled
        #endif
    }
}

extension Notification.Name {
    static let trainerGitHubInsightsSynced = Notification.Name("trainer.github.insights.synced")
}

@MainActor
final class GitHubConnectionModel: ObservableObject {
    @Published var busy = false
    @Published var connected = false
    @Published var code: String?
    @Published var message: String?
    @Published var viewer: GitHubGraph.Viewer?
    @Published private(set) var syncRevision = 0
    private var operation: Task<Void, Never>?
    private let delegate = GitHubNoRedirect()
    private lazy var session = URLSession(configuration: .ephemeral, delegate: delegate, delegateQueue: nil)

    private func request(_ url: String, body: [String: String], token: String? = nil) async throws -> Data {
        var request = URLRequest(url: URL(string: url)!)
        request.httpMethod = "POST"
        request.timeoutInterval = 25
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Trainer", forHTTPHeaderField: "User-Agent")
        if let token { request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization") }
        request.httpBody = try JSONEncoder().encode(body)
        let (data, response) = try await session.data(for: request)
        try Task.checkCancellation()
        guard let http = response as? HTTPURLResponse else { throw GitHubFailure("GitHub 响应无效。") }
        guard http.statusCode == 200 else {
            if http.statusCode == 401 { connected = false }
            throw GitHubFailure(http.statusCode == 401 ? "GitHub 授权已失效，请重新连接。" : "GitHub 请求未完成（HTTP \(http.statusCode)），请稍后重试。")
        }
        return data
    }

    func restore() {
        guard !busy else { return }
        busy = true
        operation = Task {
            defer { busy = false }
            do {
                guard let token = try GitHubCredential.read() else { connected = false; return }
                var request = URLRequest(url: URL(string: "https://api.github.com/user")!)
                request.timeoutInterval = 15
                request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
                request.setValue("Trainer", forHTTPHeaderField: "User-Agent")
                let (_, response) = try await session.data(for: request)
                try Task.checkCancellation()
                guard let http = response as? HTTPURLResponse else { throw GitHubFailure("GitHub 登录状态暂时无法确认。") }
                connected = http.statusCode == 200
                message = connected ? "GitHub 登录有效；可立即同步最新仓库语言。" :
                    (http.statusCode == 401 ? "GitHub 授权已失效，请重新连接；当前显示的是上次同步数据。" : "GitHub 登录状态检查失败（HTTP \(http.statusCode)）。")
            } catch {
                if !Task.isCancelled { connected = false; message = "无法确认 GitHub 登录状态：\(error.localizedDescription)" }
            }
        }
    }

    func connect(clientID: String) {
        guard !busy else { return }
        let client = clientID.trimmingCharacters(in: .whitespacesAndNewlines)
        guard client.range(of: "^[A-Za-z0-9_-]{8,128}$", options: .regularExpression) != nil else {
            message = "请填写 GitHub OAuth App 的 Client ID，并在 GitHub 启用 Device Flow。"; return
        }
        busy = true; message = nil
        operation = Task {
            defer { busy = false; code = nil }
            do {
                let response = try await request("https://github.com/login/device/code", body: ["client_id": client, "scope": "read:user"])
                let device = try JSONDecoder().decode(GitHubDevice.self, from: response)
                guard device.verification_uri == "https://github.com/login/device",
                      (1...1800).contains(device.expires_in), (1...60).contains(device.interval) else {
                    throw GitHubFailure("GitHub 设备授权响应无效。")
                }
                code = device.user_code
                message = "在 GitHub 输入下方代码并确认授权。"
                let deadline = Date().addingTimeInterval(Double(device.expires_in))
                var interval = device.interval
                while Date() < deadline {
                    try await Task.sleep(for: .seconds(interval))
                    let data = try await request("https://github.com/login/oauth/access_token", body: [
                        "client_id": client, "device_code": device.device_code,
                        "grant_type": "urn:ietf:params:oauth:grant-type:device_code"])
                    let result = try JSONDecoder().decode(GitHubToken.self, from: data)
                    if let token = result.access_token, !token.isEmpty {
                        try GitHubCredential.save(token)
                        connected = true
                        try await fetchInsights(token: token)
                        return
                    }
                    switch result.error {
                    case "authorization_pending": continue
                    case "slow_down": interval += 5
                    case "access_denied": throw GitHubFailure("你已取消 GitHub 授权。")
                    case "expired_token": throw GitHubFailure("授权码已过期，请重新连接。")
                    default: throw GitHubFailure("授权未完成，请检查 Client ID 和 Device Flow 设置。")
                    }
                }
                throw GitHubFailure("授权码已过期，请重新连接。")
            } catch is CancellationError { message = "已停止等待授权。" }
            catch { if !Task.isCancelled { message = error.localizedDescription } }
        }
    }

    private func fetchInsights(token: String) async throws {
        let query = """
        query { viewer { login contributionsCollection {
          totalCommitContributions totalPullRequestContributions totalIssueContributions
          contributionCalendar { totalContributions weeks { contributionDays { date contributionCount } } }
        } repositories(first: 100, affiliations: OWNER, isFork: false, orderBy: {field: UPDATED_AT, direction: DESC}) {
          nodes { languages(first: 20, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name } } } }
        } } }
        """
        let result = try JSONDecoder().decode(GitHubGraph.self, from: await request("https://api.github.com/graphql", body: ["query": query], token: token))
        guard result.errors == nil, let value = result.data?.viewer else { throw GitHubFailure("GitHub 未返回完整统计，请稍后刷新。") }
        viewer = value
        try await persistInsights(value)
        syncRevision += 1
        NotificationCenter.default.post(name: .trainerGitHubInsightsSynced, object: nil)
        message = "已同步贡献日历与仓库语言到个人档案。"
    }

    private func claimAccount(login: String) async throws {
        let defaults = UserDefaults.standard
        let preferences: [String: Any] = [
            "readingSize": defaults.double(forKey: "trainer.reading.size"),
            "readingStyle": defaults.string(forKey: "trainer.reading.style") ?? "system",
            "codeSize": defaults.double(forKey: "trainer.code.size"),
            "motion": defaults.object(forKey: "trainer.motion.enabled") as? Bool ?? true,
        ]
        var request = URLRequest(url: URL(string: "http://127.0.0.1:8787/v1/account/claim")!)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(LocalGatewaySession.token, forHTTPHeaderField: "X-Trainer-Session")
        request.httpBody = try JSONSerialization.data(withJSONObject: ["login": login, "preferences": preferences])
        let (data, response) = try await URLSession.shared.data(for: request)
        guard (response as? HTTPURLResponse)?.statusCode == 200 else {
            let detail = (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["error"] as? String
            throw GitHubFailure(detail ?? "GitHub 已连接，但未能认领本机档案。")
        }
    }

    private func persistInsights(_ value: GitHubGraph.Viewer) async throws {
        var totals: [String: (bytes: Int, repositories: Int)] = [:]
        for repository in value.repositories.nodes {
            var countedInRepository = Set<String>()
            for edge in repository.languages.edges where !edge.node.name.isEmpty && edge.size >= 0 {
                let existing = totals[edge.node.name] ?? (0, 0)
                totals[edge.node.name] = (existing.bytes + edge.size,
                                         existing.repositories + (countedInRepository.insert(edge.node.name).inserted ? 1 : 0))
            }
        }
        let collection = value.contributionsCollection
        let payload: [String: Any] = [
            "login": value.login,
            "repositoryCount": value.repositories.nodes.count,
            "languages": totals.map { ["name": $0.key, "bytes": $0.value.bytes, "repositories": $0.value.repositories] },
            "activity": collection.contributionCalendar.weeks.flatMap(\.contributionDays).map { ["day": $0.date, "count": $0.contributionCount] },
            "totalContributions": collection.contributionCalendar.totalContributions,
            "commitCount": collection.totalCommitContributions,
            "pullRequestCount": collection.totalPullRequestContributions,
            "issueCount": collection.totalIssueContributions,
        ]
        var request = URLRequest(url: URL(string: "http://127.0.0.1:8787/v1/github/insights")!)
        request.httpMethod = "POST"
        request.timeoutInterval = 15
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(LocalGatewaySession.token, forHTTPHeaderField: "X-Trainer-Session")
        request.httpBody = try JSONSerialization.data(withJSONObject: payload)
        let (_, response) = try await URLSession.shared.data(for: request)
        guard (response as? HTTPURLResponse)?.statusCode == 200 else { throw GitHubFailure("GitHub 数据已读取，但未能同步到个人档案。") }
    }

    func refresh() {
        guard !busy else { return }
        busy = true
        operation = Task {
            defer { busy = false }
            do {
                guard let token = try GitHubCredential.read() else { connected = false; return }
                try await fetchInsights(token: token)
            } catch { if !Task.isCancelled { message = error.localizedDescription } }
        }
    }

    func cancel() { operation?.cancel() }
    func disconnect() {
        guard !busy else { return }
        do {
            try GitHubCredential.remove()
            connected = false; viewer = nil
            message = "已断开本机连接。GitHub 账户中的应用授权可在 GitHub 设置中撤销。"
        } catch { message = error.localizedDescription }
    }
}

struct GitHubConnectionView: View {
    @StateObject private var model = GitHubConnectionModel()
    var onInsightsSynced: (() -> Void)? = nil
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label("GitHub 活动", systemImage: "point.3.connected.trianglepath.dotted").font(.headline)
                Spacer()
                Text(model.connected ? "已授权" : "未连接").foregroundStyle(.secondary)
            }
            if !model.connected {
                if GitHubOAuthConfig.clientID.isEmpty {
                    Label("此发行包尚未配置 GitHub OAuth App。请由产品管理员在构建时提供 Client ID 并启用 Device Flow。", systemImage: "building.2")
                        .font(.caption).foregroundStyle(.secondary)
                } else {
                    Text("此应用已配置 GitHub OAuth App。仅请求 read:user；同步近一年贡献日历，以及最多 100 个你的公开仓库的语言聚合。")
                        .font(.caption).foregroundStyle(.secondary)
                    Button("连接 GitHub") { model.connect(clientID: GitHubOAuthConfig.clientID) }.disabled(model.busy)
                }
            } else {
                HStack {
                    Button("刷新活动") { model.refresh() }.disabled(model.busy)
                    Button("断开本机连接") { model.disconnect() }.disabled(model.busy)
                    Link("管理 GitHub 授权", destination: URL(string: "https://github.com/settings/applications")!)
                }
            }
            if model.busy { HStack { ProgressView().controlSize(.small); Button("取消") { model.cancel() } } }
            if let code = model.code {
                Text(code).font(.system(.title, design: .monospaced)).textSelection(.enabled)
                Link("打开 GitHub 输入授权码", destination: URL(string: "https://github.com/login/device")!)
            }
            if let viewer = model.viewer {
                Text("@" + viewer.login).font(.headline)
                let collection = viewer.contributionsCollection
                HStack {
                    metric("贡献", collection.contributionCalendar.totalContributions)
                    metric("提交", collection.totalCommitContributions)
                    metric("拉取请求", collection.totalPullRequestContributions)
                    metric("议题", collection.totalIssueContributions)
                }
                Label("已分析 \(viewer.repositories.nodes.count) 个可访问的本人仓库 · \(Set(viewer.repositories.nodes.flatMap { $0.languages.edges.map { $0.node.name } }).count) 种项目语言", systemImage: "arrow.triangle.2.circlepath")
                    .font(.caption).foregroundStyle(.secondary)
                Text("贡献热力图和项目语言信号已同步到「个人主页」。语言信号不等同于课堂评估分数或编程时长。")
                    .font(.caption).foregroundStyle(.secondary)
            }
            if let message = model.message { Text(message).font(.caption).textSelection(.enabled) }
        }.padding(16).background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 14))
            .onAppear { model.restore() }.onDisappear { model.cancel() }
            .onChange(of: model.syncRevision) { _, revision in if revision > 0 { onInsightsSynced?() } }
    }
    private func metric(_ title: String, _ count: Int) -> some View {
        VStack(alignment: .leading) { Text("\(count)").font(.title2.bold()); Text(title).font(.caption).foregroundStyle(.secondary) }
            .frame(maxWidth: .infinity, alignment: .leading)
    }
}
