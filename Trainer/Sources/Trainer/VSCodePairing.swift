import SwiftUI

struct VSCodePairing: View {
    struct Pending: Decodable, Identifiable { let id: String; let name: String; let expires: Double; let approved: Int }
    struct Workspace: Decodable, Identifiable { let id: String; let root: String; let plan_id: String; let valid: Bool? }
    @State private var workspaces: [Workspace] = []
    @State private var activeWorkspaces: [Workspace] = []
    struct SourceGrant: Decodable, Identifiable { let id: String; let bindingId: String; let paths: [String]; let valid: Bool }
    @State private var sourceGrants: [SourceGrant] = []
    @State private var sourceError = ""
    @State private var consentWorkspace: Workspace?
    @Environment(\.dismiss) private var dismiss
    @State private var pending: [Pending] = []
    @State private var codes: [String: String] = [:]
    @State private var message = ""
    @State private var busy = false
    @State private var confirmClear = false
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack { Text("连接 VS Code").font(.title2.bold()); Spacer(); Button("完成") { dismiss() } }
            ConnectionStatus()
            Text("先在 VS Code 执行“Trainer: 连接本地教学应用”，再将该窗口显示的六位配对码输入下方。只确认你刚发起的请求。")
                .foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            Text("本次只授予建立工作区绑定的权限，不读取项目、不外发源码、不执行命令。")
                .font(.caption).foregroundStyle(.secondary)
            Button("刷新连接与工作区") { Task { await load() } }.disabled(busy)
            Button("断开并清理全部配对…", role: .destructive) { confirmClear = true }.disabled(busy)
            ScrollView {
                VStack(spacing: 14) {
                    VStack(alignment: .leading, spacing: 10) {
                        Label("源码读取授权", systemImage: "doc.text.magnifyingglass").font(.headline)
                        Text("仅限明确文件范围；不含 AI 外发许可，不会自动执行代码。").font(.caption).foregroundStyle(.secondary)
                        if !sourceError.isEmpty { Text(sourceError).font(.caption).foregroundStyle(.orange) }
                        else if sourceGrants.isEmpty { Text("暂无源码授权。目录配对不会自动授权读取。").font(.caption).foregroundStyle(.secondary) }
                        ForEach(sourceGrants) { grant in
                            DisclosureGroup("\(grant.paths.count) 个文件 · \(grant.valid ? "授权有效" : "关联已失效")") {
                                VStack(alignment: .leading, spacing: 6) {
                                    Text("关联：\(grant.bindingId.prefix(12))").font(.caption).foregroundStyle(.secondary)
                                    ForEach(grant.paths, id: \.self) { Text($0).font(.caption.monospaced()).textSelection(.enabled) }
                                    Button("撤销源码读取", role: .destructive) { Task { await revokeSource(grant.id) } }.disabled(busy)
                                }.frame(maxWidth: .infinity, alignment: .leading)
                            }
                        }
                    }.frame(maxWidth: .infinity, alignment: .leading).padding().background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 12))
                    ForEach(activeWorkspaces) { item in
                        VStack(alignment: .leading, spacing: 8) {
                            Label(item.valid == true ? "已关联工作区" : "目录已失效，请重新关联", systemImage: item.valid == true ? "checkmark.folder" : "exclamationmark.triangle")
                                .font(.headline)
                            Text(item.root).textSelection(.enabled)
                            Text("课程：\(item.plan_id.prefix(12)) · 目录关联不等于源码授权").font(.caption).foregroundStyle(.secondary)
                            Button("设置源码读取范围…") { consentWorkspace = item }.disabled(busy || item.valid != true)
                            Button("撤销关联", role: .destructive) { Task { await workspaceAction(item.id, action: "revoke") } }.disabled(busy)
                        }.frame(maxWidth: .infinity, alignment: .leading).padding().background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 12))
                    }
                    ForEach(workspaces) { item in
                        VStack(alignment: .leading, spacing: 8) {
                            Text("工作区关联请求").font(.headline)
                            Text(item.root).textSelection(.enabled)
                            Text("课程 ID：\(item.plan_id)").font(.caption).textSelection(.enabled)
                            Text("仅关联目录与课程，不读取源码、不发送 AI、不执行命令。").font(.caption).foregroundStyle(.secondary)
                            HStack {
                                Button("确认关联") { Task { await workspaceAction(item.id, action: "approve") } }
                                Button("拒绝") { Task { await workspaceAction(item.id, action: "revoke") } }
                            }.disabled(busy)
                        }.padding().background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 12))
                    }
                    if pending.isEmpty && workspaces.isEmpty && activeWorkspaces.isEmpty { Text("暂无配对请求或已关联工作区").foregroundStyle(.secondary).padding() }
                    ForEach(pending) { item in
                        VStack(alignment: .leading, spacing: 8) {
                            Text(item.name).font(.headline)
                            Text("请求 \(item.id.prefix(8)) · \(Date(timeIntervalSince1970: item.expires).formatted(date: .omitted, time: .shortened)) 前有效")
                                .font(.caption).foregroundStyle(.secondary)
                            if item.approved == 1 {
                                Label("已确认，请返回 VS Code 领取连接", systemImage: "checkmark.circle")
                            } else {
                                HStack {
                                    TextField("VS Code 显示的六位码", text: Binding(get: { codes[item.id] ?? "" }, set: { codes[item.id] = $0 }))
                                    Button("确认配对") { Task { await approve(item.id) } }
                                        .disabled(busy || (codes[item.id] ?? "").range(of: "^[0-9]{6}$", options: .regularExpression) == nil)
                                }
                            }
                        }.padding().background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 12))
                    }
                }
            }.frame(maxHeight: 300)
            if busy { ProgressView("正在处理配对…") }
            Text(message).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
        }.padding(24).frame(width: 560).textFieldStyle(.roundedBorder).task { await load() }
        .sheet(item: $consentWorkspace) { workspace in
            SourceConsent(workspace: workspace) { Task { await load() } }
        }
        .confirmationDialog("断开并清理所有 VS Code 配对？", isPresented: $confirmClear) {
            Button("断开并清理", role: .destructive) { Task { await clearConnections() } }
            Button("取消", role: .cancel) { }
        } message: {
            Text("现有配对和待确认请求将失效，相关目录及源码授权也随之失效。课程、学习记录和项目文件保留；下次连接需要重新配对。")
        }
    }
    private func clearConnections() async {
        busy = true
        defer { busy = false }
        do {
            _ = try await call("/clear", payload: [:])
            await load()
            message = "已断开并清理配对，课程和项目文件未删除。状态指示将在下次轮询同步。"
        } catch { message = "清理结果未确认，请刷新查看；不会自动重试。" }
    }
    private func call(_ path: String, payload: [String: String]? = nil) async throws -> Data {
        var request = URLRequest(url: URL(string: "http://127.0.0.1:8787/v2/pairings" + path)!)
        request.timeoutInterval = 10
        request.setValue(LocalGatewaySession.token, forHTTPHeaderField: "X-Trainer-Session")
        if let payload {
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONEncoder().encode(payload)
        }
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let status = (response as? HTTPURLResponse)?.statusCode, (200...299).contains(status) else { throw URLError(.badServerResponse) }
        return data
    }
    private func revokeSource(_ id: String) async {
        busy = true
        defer { busy = false }
        do {
            _ = try await call("/source-grants/revoke", payload: ["id": id])
            await load()
            message = "源码读取授权已撤销。"
        } catch { message = "撤销未成功，请刷新并重试。" }
    }
    private func load() async {
        busy = true; defer { busy = false }
        do {
            struct Grants: Decodable { let grants: [SourceGrant] }
            sourceGrants = try JSONDecoder().decode(Grants.self, from: await call("/source-grants")).grants
            sourceError = ""
        } catch { sourceGrants = []; sourceError = "源码授权状态暂不可读取，请刷新重试。" }
        do {
            struct Envelope: Decodable { let pending: [Pending] }
            pending = try JSONDecoder().decode(Envelope.self, from: await call("")).pending
            struct Workspaces: Decodable { let pending: [Workspace]; let active: [Workspace] }
            let listing = try JSONDecoder().decode(Workspaces.self, from: await call("/workspaces"))
            workspaces = listing.pending
            activeWorkspaces = listing.active
            message = ""
        } catch { message = "无法读取配对请求，请确认新版 Gateway 已启动。" }
    }
    private func approve(_ id: String) async {
        busy = true
        do {
            _ = try await call("/approve", payload: ["id": id, "code": codes[id] ?? ""])
            codes[id] = nil
            await load()
            message = "已确认。请返回 VS Code 完成领取。"
        } catch { message = "配对未确认：请核对六位码和有效期，错误次数过多需重新发起。" }
        busy = false
    }
    private func workspaceAction(_ id: String, action: String) async {
        busy = true
        defer { busy = false }
        do {
            _ = try await call("/workspaces/" + action, payload: ["id": id])
            await load()
            message = action == "approve" ? "目录已关联，请返回 VS Code 检查状态。" : "已撤销此关联或请求。"
        } catch { message = "操作失败：请刷新并确认课程仍存在、目录未变化。" }
    }
}
