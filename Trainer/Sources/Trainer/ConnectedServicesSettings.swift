import SwiftUI

private struct IntegrationStatus: Decodable { let cloud: ServiceState; let github: GitHubState }
private struct ServiceState: Decodable { let state: String; let configured: Bool; let endpoint: String?; let mode, message: String }
private struct GitHubState: Decodable { let state: String; let configured: Bool; let scopes, optionalScopes, collects, excludes: [String]; let message: String }
private struct AccountDevice: Decodable, Identifiable { let id, name, platform, createdAt, lastSeenAt: String; let current: Bool }
private struct CloudDevice: Decodable, Identifiable { let id, name: String; let seen: Double; let revoked: Int; let current: Bool }
private struct CloudDevices: Decodable { let devices: [CloudDevice] }
private struct AccountState: Decodable {
    let signedIn: Bool
    let accountId, provider, login, claimedAt, lastSyncAt: String?
    let mode, message: String
    let pendingChanges: Int
    let devices: [AccountDevice]
    let preparedChanges: Int?
    let cloudSessionActive: Bool?
    let lastBackgroundSyncAt, lastBackgroundError: String?
    let conflicts: Int?
}
private struct CloudConflict: Decodable, Identifiable {
    let id, kind, localSummary, remoteSummary: String
}
private struct CloudConflicts: Decodable { let conflicts: [CloudConflict] }

struct ConnectedServicesSettings: View {
    @Environment(\.dismiss) private var dismiss
    @AppStorage("trainer.reading.size") private var readingSize = 15.0
    @AppStorage("trainer.reading.style") private var readingStyle = "system"
    @AppStorage("trainer.code.size") private var codeSize = 14.0
    @AppStorage("trainer.motion.enabled") private var motion = true
    @AppStorage("trainer.cloud.endpoint") private var cloudEndpoint = ""
    @State private var status: IntegrationStatus?
    @State private var account: AccountState?
    @State private var error: String?
    @State private var busy = false
    @State private var confirmDelete = false
    @State private var cloudDevices: [CloudDevice] = []
    @State private var cloudConflicts: [CloudConflict] = []
    @State private var confirmCloudDelete = false

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack {
                Label("账户与同步", systemImage: "person.crop.circle.badge.checkmark").font(.title2.bold())
                Spacer(); Button("完成") { dismiss() }
            }
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    accountCard
                    cloudEndpointCard
                    GitHubConnectionView(onInsightsSynced: { Task { await load() } })
                    privacyCard
                    if let error { Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(.orange) }
                }.frame(maxWidth: .infinity)
            }
        }
        .padding(24).frame(width: 640, height: 700)
        .task { await load() }
        .confirmationDialog("删除 Trainer 账户关系？", isPresented: $confirmDelete, titleVisibility: .visible) {
            Button("删除账户关系", role: .destructive) { Task { await action("delete", confirmed: true) } }
            Button("取消", role: .cancel) {}
        } message: { Text("会清除本机账户与待同步队列；课程、学习记录和项目文件仍保留。GitHub 授权需在下方单独断开。") }
        .confirmationDialog("永久删除云端账户？", isPresented: $confirmCloudDelete, titleVisibility: .visible) {
            Button("删除云端账户和同步数据", role: .destructive) { Task { await cloudAction("delete-cloud", body: ["confirmed": true]) } }
            Button("取消", role: .cancel) {}
        } message: { Text("所有设备的云会话与云端记录将被删除。本机课程和学习记录保留。") }
    }

    private var accountCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label("Trainer 账户", systemImage: "person.text.rectangle").font(.headline)
                Spacer()
                Text(account?.signedIn == true ? "已登录" : "本机模式")
                    .font(.caption.weight(.semibold)).padding(.horizontal, 9).padding(.vertical, 5)
                    .background((account?.signedIn == true ? Color.green : Color.secondary).opacity(0.14), in: Capsule())
            }
            if let account, account.signedIn {
                Text("@\(account.login ?? "GitHub 用户")").font(.title3.bold())
                Text("GitHub 身份已认领当前本机档案。账户编号 \((account.accountId ?? "").prefix(8))")
                    .font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                HStack {
                    Label("\(account.pendingChanges) 项待同步", systemImage: "arrow.triangle.2.circlepath")
                    if let last = account.lastSyncAt { Text("上次云同步 \(last.prefix(16))") }
                    else { Text(status?.cloud.configured == true ? "尚未执行云同步" : "云服务未配置") }
                }.font(.caption).foregroundStyle(.secondary)
                if account.cloudSessionActive == true {
                    Text(account.lastBackgroundSyncAt.map { "后台同步：\($0.prefix(16))" } ?? "后台同步已开启；有新学习记录时会自动检查。")
                        .font(.caption).foregroundStyle(.secondary)
                }
                if let backgroundError = account.lastBackgroundError, !backgroundError.isEmpty {
                    Label("后台同步暂未完成：\(backgroundError)", systemImage: "wifi.exclamationmark")
                        .font(.caption).foregroundStyle(.orange)
                }
                HStack {
                    Button("登录云同步") { Task { await action("claim") } }.disabled(busy || status?.cloud.configured != true)
                    Button("立即同步") { Task { await action("sync") } }.buttonStyle(.borderedProminent).disabled(busy || status?.cloud.configured != true)
                }
                Text(status?.cloud.configured == true ? "登录后会在后台自动同步课程、进度与学习摘要；冲突不会覆盖，需由你选择保留版本。重启应用后请重新登录云同步。" : "云服务尚未配置，数据继续保存在本机。")
                    .font(.caption).foregroundStyle(.secondary)
                if (account.conflicts ?? 0) > 0 {
                    Divider(); Label("需要处理的同步冲突（\(account.conflicts ?? 0)）", systemImage: "arrow.triangle.branch")
                        .font(.subheadline.bold())
                    Button("查看冲突") { Task { await loadConflicts() } }.disabled(busy)
                    ForEach(cloudConflicts) { conflict in
                        VStack(alignment: .leading, spacing: 5) {
                            Text(conflict.kind == "course-plan" ? "课程版本不同" : "同步版本不同").font(.caption.bold())
                            Text("本机：\(conflict.localSummary)\n云端：\(conflict.remoteSummary)")
                                .font(.caption).foregroundStyle(.secondary)
                            HStack {
                                Button("保留本机") { Task { await resolve(conflict, decision: "keep-local") } }
                                Button("采用云端") { Task { await resolve(conflict, decision: "use-cloud") } }
                                    .buttonStyle(.bordered)
                            }
                        }.padding(10).background(.orange.opacity(0.08), in: RoundedRectangle(cornerRadius: 9))
                    }
                }
                Divider(); Text("设备").font(.subheadline.bold())
                Button("刷新云端设备") { Task { await cloudAction("devices") } }.disabled(busy || status?.cloud.configured != true)
                ForEach(cloudDevices.filter { $0.revoked == 0 }) { device in
                    HStack {
                        Text(device.name + (device.current ? " · 当前云会话" : ""))
                        Spacer()
                        if !device.current { Button("退出此设备") { Task { await cloudAction("revoke-device", body: ["deviceId": device.id]) } } }
                    }
                }
                ForEach(account.devices) { device in
                    HStack {
                        Image(systemName: device.current ? "laptopcomputer.and.arrow.down" : "laptopcomputer")
                        VStack(alignment: .leading) {
                            Text(device.name + (device.current ? " · 当前设备" : ""))
                            Text(device.platform + " · 最近活动 " + String(device.lastSeenAt.prefix(16))).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }
                HStack {
                    Button("退出 Trainer 账户") { Task { await action("sign-out") } }.disabled(busy)
                    Button("删除账户关系", role: .destructive) { confirmDelete = true }.disabled(busy)
                    Button("删除云端账户", role: .destructive) { confirmCloudDelete = true }.disabled(busy || status?.cloud.configured != true)
                }
            } else {
                Text("连接 GitHub 后，点击登录以认领本机档案。云同步仅发送资料、进度与学习摘要。")
                    .foregroundStyle(.secondary)
                Button("使用 GitHub 登录并认领档案") { Task { await action("claim") } }.disabled(busy)
            }
            if busy { ProgressView().controlSize(.small) }
            if let message = account?.message { Text(message).font(.caption).foregroundStyle(.secondary) }
        }.trainerAccountCard()
    }

    private var privacyCard: some View {
        VStack(alignment: .leading, spacing: 9) {
            Label("同步边界", systemImage: "lock.shield").font(.headline)
            Text("可同步：个人资料、完整课程教学内容、课程进度、学习证据摘要、成就状态和阅读偏好。")
            Text("永不同步：API 密钥、GitHub 令牌、项目源码、工作区路径、终端原文、回答正文和项目私密内容。")
            Text("GitHub 令牌继续保存在 macOS 钥匙串；退出 Trainer 账户不会删除学习数据。")
        }.font(.caption).foregroundStyle(.secondary).trainerAccountCard()
    }

    private var cloudEndpointCard: some View {
        VStack(alignment: .leading, spacing: 9) {
            Label("云同步服务", systemImage: "icloud.and.arrow.up").font(.headline)
            TextField("HTTPS 服务地址", text: $cloudEndpoint, prompt: Text("https://your-domain/trainer-account"))
                .textFieldStyle(.roundedBorder)
            Text("保存后重启 Trainer，使本地 Gateway 使用新的服务地址。地址必须是 HTTPS；不填写则继续使用本机档案。")
                .font(.caption).foregroundStyle(.secondary)
            if !cloudEndpoint.isEmpty && !validCloudEndpoint {
                Label("请输入完整 HTTPS 地址，不能包含账号、密码、查询参数或片段。", systemImage: "exclamationmark.triangle")
                    .font(.caption).foregroundStyle(.orange)
            }
        }.trainerAccountCard()
    }

    private var validCloudEndpoint: Bool {
        guard let url = URL(string: cloudEndpoint), url.scheme == "https", url.host != nil else { return false }
        return url.user == nil && url.password == nil && url.query == nil && url.fragment == nil
    }

    private func preferences() -> [String: Any] { ["readingSize": readingSize, "readingStyle": readingStyle, "codeSize": codeSize, "motion": motion] }

    @MainActor private func cloudAction(_ name: String, body: [String: Any] = [:]) async {
        busy = true; defer { busy = false }
        do {
            let data = try await request("/v1/account/" + name, method: "POST", payload: body)
            if name == "devices" { cloudDevices = try JSONDecoder().decode(CloudDevices.self, from: data).devices }
            else if name == "delete-cloud" { cloudDevices = []; await load() }
            else { cloudDevices = try JSONDecoder().decode(CloudDevices.self, from: try await request("/v1/account/devices", method: "POST", payload: [:])).devices }
            error = nil
        } catch { self.error = error.localizedDescription }
    }

    @MainActor private func load() async {
        busy = true; defer { busy = false }
        do {
            status = try JSONDecoder().decode(IntegrationStatus.self, from: try await request("/v1/integrations/status"))
            account = try JSONDecoder().decode(AccountState.self, from: try await request("/v1/account")); error = nil
        } catch { self.error = "无法读取账户状态：\(error.localizedDescription)" }
    }

    @MainActor private func loadConflicts() async {
        busy = true; defer { busy = false }
        do {
            cloudConflicts = try JSONDecoder().decode(CloudConflicts.self, from: try await request("/v1/account/conflicts", method: "POST", payload: [:])).conflicts
            error = nil
        } catch { self.error = error.localizedDescription }
    }

    @MainActor private func resolve(_ conflict: CloudConflict, decision: String) async {
        busy = true; defer { busy = false }
        do {
            account = try JSONDecoder().decode(AccountState.self, from: try await request("/v1/account/resolve-conflict", method: "POST", payload: ["id": conflict.id, "decision": decision]))
            cloudConflicts.removeAll { $0.id == conflict.id }
            error = nil
        } catch { self.error = error.localizedDescription }
    }

    @MainActor private func action(_ name: String, confirmed: Bool = false) async {
        busy = true; defer { busy = false }
        do {
            let payload: [String: Any] = ["preferences": preferences(), "confirmed": confirmed, "cloud": status?.cloud.configured == true]
            let data = try await request("/v1/account/\(name)", method: "POST", payload: payload)
            if name == "delete" { await load() } else { account = try JSONDecoder().decode(AccountState.self, from: data) }
            error = nil
        } catch { self.error = error.localizedDescription }
    }

    private func request(_ path: String, method: String = "GET", payload: [String: Any]? = nil) async throws -> Data {
        var request = URLRequest(url: URL(string: "http://127.0.0.1:8787" + path)!)
        request.httpMethod = method; request.setValue(LocalGatewaySession.token, forHTTPHeaderField: "X-Trainer-Session")
        if let payload { request.setValue("application/json", forHTTPHeaderField: "Content-Type"); request.httpBody = try JSONSerialization.data(withJSONObject: payload) }
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            let message = (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["error"] as? String
            throw GitHubFailure(message ?? "账户操作未完成。")
        }
        return data
    }
}

private extension View {
    func trainerAccountCard() -> some View {
        padding(16).frame(maxWidth: .infinity, alignment: .leading)
            .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 14))
            .overlay(RoundedRectangle(cornerRadius: 14).stroke(.white.opacity(0.10)))
    }
}
