import SwiftUI
import Security
import CryptoKit

struct AIServiceSettings: View {
    @Environment(\.dismiss) private var dismiss
    @State private var endpoint = "https://api.deepseek.com/v1"
    @State private var model = "deepseek-chat"
    @State private var key = ""
    @State private var message = ""
    @State private var busy = false
    @State private var protocolName = "responses"
    @State private var authorized = false
    private var configURL: URL {
        FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/Trainer/ai-service.json")
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack { Text("Trainer AI 服务").font(.title2.bold()); Spacer(); Button("完成") { dismiss() } }
            Text("每位 macOS 用户配置自己的服务与密钥。兼容 OpenAI Responses / Chat Completions 的服务都可接入；设置仅影响这台设备上的 Trainer。")
                .font(.callout).foregroundStyle(.secondary)
            HStack {
                Text("快速填写").font(.caption).foregroundStyle(.secondary)
                Button("DeepSeek") {
                    endpoint = "https://api.deepseek.com/v1"
                    model = "deepseek-chat"; protocolName = "chat-completions"; authorized = false
                }
                Button("OpenAI / GPT") {
                    endpoint = "https://api.openai.com/v1"
                    model = "gpt-4.1"; protocolName = "responses"; authorized = false
                }
                Button("OpenCode Go · Luna") {
                    endpoint = "https://opencode.ai/zen/go/v1/responses"
                    model = "gpt-5.6-luna"; protocolName = "responses"; authorized = false
                }
                Button("OpenCode Go · Kimi") {
                    endpoint = "https://opencode.ai/zen/go/v1/chat/completions"
                    model = "kimi-k2.7-code"; protocolName = "chat-completions"; authorized = false
                }
            }.disabled(busy)
            Picker("接口协议", selection: $protocolName) {
                Text("Responses").tag("responses")
                Text("Chat Completions").tag("chat-completions")
            }.pickerStyle(.segmented)
            VStack(alignment: .leading, spacing: 6) {
                Text("API 地址（Base URL 或完整路径）").font(.caption)
                TextField("https://服务商/v1", text: $endpoint)
                Text("模型 ID").font(.caption)
                TextField("填写服务商模型列表中的精确名称", text: $model)
            }
            SecureField("新 API 密钥（保存在 macOS 钥匙串）", text: $key)
            Text("域名根地址默认补 /v1，再补协议路径；已填完整接口则原样保留。密钥按服务地址隔离，切换域名必须配置对应密钥。若账户没有预设模型，请填服务商控制台显示的精确模型 ID。")
                .font(.caption).foregroundStyle(.secondary)
            Text("连接测试依次检查普通回复与课程结构化输出，最多两次小请求。只有测试通过的模型才适合生成课程与评判。OpenCode Go 自动使用 Trainer 客户端标识与稳定会话。")
                .font(.caption).foregroundStyle(.secondary)
            Toggle("我允许 Trainer 将课程、回答及已授权项目材料发送到此服务", isOn: $authorized)
                .font(.caption)
            HStack {
                Button("保存并启用") { Task { await save(enabled: true) } }.buttonStyle(.borderedProminent).disabled(!authorized)
                Button("测试连接") { Task { await save(enabled: false, test: true) } }
                Button("恢复默认服务") { Task { await save(enabled: false) } }
                if busy { ProgressView().controlSize(.small) }
            }.disabled(busy)
            Text(message).font(.caption).fixedSize(horizontal: false, vertical: true)
        }.padding(24).frame(width: 620).textFieldStyle(.roundedBorder)
            .onChange(of: endpoint) { _, _ in authorized = false; message = "地址已修改，尚未测试或启用。" }
            .onChange(of: model) { _, _ in message = "模型已修改，尚未测试。" }
            .onChange(of: protocolName) { _, _ in message = "协议已修改，尚未测试。" }
            .task {
                if let data = try? Data(contentsOf: configURL), let value = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                    endpoint = value["endpoint"] as? String ?? endpoint
                    model = value["model"] as? String ?? model
                    protocolName = value["protocol"] as? String ?? "responses"
                    authorized = value["enabled"] as? Bool == true
                    message = authorized ? "此配置已启用；连通性尚未测试。" : "当前使用默认服务配置"
                }
            }
    }
    private func save(enabled: Bool, test: Bool = false) async {
        busy = true; defer { busy = false }
        do {
            let (data, _) = try await URLSession.shared.data(from: URL(string: "http://127.0.0.1:8787/v1/jobs")!)
            struct Jobs: Decodable { let jobs: [GenerationTask] }
            let jobs = try JSONDecoder().decode(Jobs.self, from: data).jobs
            guard !jobs.contains(where: { ["queued", "running"].contains($0.status) || $0.inFlight }) else {
                message = "请先等待或取消后台任务，再切换服务。"; return
            }
            if !enabled && !test {
                try FileManager.default.createDirectory(at: configURL.deletingLastPathComponent(), withIntermediateDirectories: true)
                try JSONSerialization.data(withJSONObject: ["enabled": false]).write(to: configURL, options: .atomic)
                message = "已恢复默认服务配置。"; return
            }
            guard let url = URL(string: endpoint.trimmingCharacters(in: .whitespaces)), let host = url.host?.lowercased(),
                  url.scheme == "https" || (url.scheme == "http" && ["localhost", "127.0.0.1", "[::1]", "::1"].contains(host)),
                  url.user == nil, url.password == nil, url.query == nil, url.fragment == nil,
                  !model.trimmingCharacters(in: .whitespaces).isEmpty else {
                message = "请填写 HTTPS API 地址与模型 ID。HTTP 仅限本机服务。"; return
            }
            let path = url.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
            if (path.hasSuffix("chat/completions") && protocolName == "responses") || (path.hasSuffix("responses") && protocolName == "chat-completions") {
                message = "完整接口路径与所选协议不一致，请同时修改。"; return
            }
            let cleanHost = host.replacingOccurrences(of: "[", with: "").replacingOccurrences(of: "]", with: "")
            let origin = "\(url.scheme!)://\(cleanHost):\(url.port ?? (url.scheme == "https" ? 443 : 80))"
            let digest = SHA256.hash(data: Data(origin.utf8)).map { String(format: "%02x", $0) }.joined()
            let service = url.scheme == "https" && host == "okai.la" && (url.port == nil || url.port == 443) ? "trainer-okai-api-key" : "trainer-ai-" + digest
            let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: "Trainer"]
            if enabled || test {
                if !key.isEmpty {
                    let secret = Data(key.utf8)
                    var status = SecItemUpdate(query as CFDictionary, [kSecValueData as String: secret] as CFDictionary)
                    if status == errSecItemNotFound {
                        var item = query; item[kSecValueData as String] = secret
                        status = SecItemAdd(item as CFDictionary, nil)
                    }
                    guard status == errSecSuccess else { message = "钥匙串保存失败（\(status)），尚未切换服务。"; return }
                } else {
                    guard SecItemCopyMatching(query as CFDictionary, nil) == errSecSuccess else { message = "请先在此处输入新密钥。"; return }
                }
            }
            let settings: [String: Any] = ["enabled": enabled, "endpoint": endpoint.trimmingCharacters(in: .whitespaces), "model": model.trimmingCharacters(in: .whitespaces), "protocol": protocolName]
            if test {
                message = "正在检查普通回复 → 结构化输出…只发送固定示例，最多约 50 秒，可能产生少量用量。"
                var request = URLRequest(url: URL(string: "http://127.0.0.1:8787/v1/ai/test")!)
                request.httpMethod = "POST"
                request.timeoutInterval = 65
                request.setValue(LocalGatewaySession.token, forHTTPHeaderField: "X-Trainer-Session")
                request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                request.httpBody = try JSONSerialization.data(withJSONObject: settings)
                let (result, _) = try await URLSession.shared.data(for: request)
                let value = try JSONSerialization.jsonObject(with: result) as? [String: Any]
                message = value?["message"] as? String ?? value?["error"] as? String ?? "测试没有返回有效结果。"
                key = ""; return
            }
            try FileManager.default.createDirectory(at: configURL.deletingLastPathComponent(), withIntermediateDirectories: true)
            try JSONSerialization.data(withJSONObject: settings).write(to: configURL, options: .atomic)
            key = ""
            message = "已为当前 macOS 用户启用 \(host) · \(protocolName)。下一次请求使用新配置；请测试连接确认可用。"
        } catch { message = "配置未完成：\(error.localizedDescription)" }
    }
}
