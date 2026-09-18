import SwiftUI
import AppKit

struct SourceConsent: View {
    let workspace: VSCodePairing.Workspace
    let onApproved: () -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var paths: [String] = []
    @State private var busy = false
    @State private var message = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack { Text("确认源码读取范围").font(.title2); Spacer(); Button("取消") { dismiss() }.disabled(busy) }
            Text(workspace.root).font(.caption.monospaced()).textSelection(.enabled)
            Text("首次批量选择，确认后保存为此项目的读取范围。不会自动读取内容、运行代码或发送给 AI；新增文件需要扩展授权。当前尚未启用自动提交。")
                .font(.callout).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            Button(paths.isEmpty ? "批量选择项目文件" : "重新选择范围") { chooseFiles() }.disabled(busy)
            Text("待授权 \(paths.count) / 100 个文件").font(.headline)
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(paths, id: \.self) { Text($0).font(.caption.monospaced()).textSelection(.enabled) }
                }.frame(maxWidth: .infinity, alignment: .leading)
            }.frame(height: 200)
            if !message.isEmpty { Text(message).font(.caption).foregroundStyle(.orange).fixedSize(horizontal: false, vertical: true) }
            HStack {
                Text("可在连接面板随时撤销。常见密钥文件不可授权。").font(.caption).foregroundStyle(.secondary)
                Spacer()
                Button(busy ? "正在保存…" : "确认仅授权本地读取") { Task { await approve() } }
                    .buttonStyle(.borderedProminent).disabled(paths.isEmpty || busy)
            }
        }.padding(24).frame(width: 620).interactiveDismissDisabled(busy)
    }

    @MainActor private func chooseFiles() {
        let panel = NSOpenPanel()
        panel.directoryURL = URL(fileURLWithPath: workspace.root)
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = true
        panel.message = "选择当前关联项目内的文件，可多选；不会读取或上传文件内容。"
        guard panel.runModal() == .OK else { return }
        let prefix = URL(fileURLWithPath: workspace.root).standardizedFileURL.path + "/"
        var selected: [String] = []
        for url in panel.urls {
            let path = url.standardizedFileURL.path
            guard path.hasPrefix(prefix), url.resolvingSymlinksInPath().path == path else {
                message = "只能选择当前项目内的普通文件，不能包含符号链接。原选择未改变。"
                return
            }
            selected.append(String(path.dropFirst(prefix.count)))
        }
        guard !selected.isEmpty, selected.count <= 100 else { message = "每次范围须为 1–100 个文件。"; return }
        paths = Array(Set(selected)).sorted()
        message = "请核对上方清单；点击确认后才保存许可。"
    }

    @MainActor private func approve() async {
        busy = true
        defer { busy = false }
        struct Payload: Encodable { let bindingId: String; let paths: [String] }
        do {
            var request = URLRequest(url: URL(string: "http://127.0.0.1:8787/v2/pairings/source-grants/approve")!)
            request.httpMethod = "POST"
            request.timeoutInterval = 10
            request.setValue(LocalGatewaySession.token, forHTTPHeaderField: "X-Trainer-Session")
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONEncoder().encode(Payload(bindingId: workspace.id, paths: paths))
            let (_, response) = try await URLSession.shared.data(for: request)
            guard (response as? HTTPURLResponse)?.statusCode == 201 else {
                message = "未批准：请排除密钥文件，并确认目录关联、课程仍有效。"
                return
            }
            onApproved()
            dismiss()
        } catch {
            message = "未能确认保存结果。请取消并刷新连接面板查看授权，再决定是否重试；不会自动重发。"
        }
    }
}
