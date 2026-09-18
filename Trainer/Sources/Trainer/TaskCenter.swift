import SwiftUI

struct GenerationTask: Decodable, Identifiable {
    let id, status, kind: String
    let message, error: String?
    let completed, total: Int?
    let resumable, inFlight: Bool
    var label: String {
        ["plan": "课程展开", "candidate": "候选教学", "optimize-pending": "候选优化", "optimize-skill": "Skill 优化"][kind] ?? "历史任务"
    }
    var statusLabel: String {
        ["queued": "排队中", "running": "生成中", "completed": "已完成", "failed": "失败", "paused": "已暂停", "cancelled": "已取消"][status] ?? status
    }
}

struct TaskCenter: View {
    @Environment(\.dismiss) private var dismiss
    @State private var tasks: [GenerationTask] = []
    @State private var error: String?
    @State private var busy: String?
    @State private var showInbox = false
    @State private var loading = true
    @State private var archived = false
    @State private var confirmClear = false
    @State private var confirmDeleteAll = false
    @State private var pendingDelete: GenerationTask?
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text("生成任务").font(.title2.bold())
                Spacer()
                Button("查看待审批") { showInbox = true }
                Button("完成") { dismiss() }
            }
            if let error { Text(error).foregroundStyle(.orange) }
            HStack {
                Toggle("查看已清理", isOn: $archived).toggleStyle(.switch)
                Spacer()
                if archived {
                    Button("彻底清空…", role: .destructive) { confirmDeleteAll = true }
                        .disabled(busy != nil || tasks.isEmpty)
                } else {
                    Button("一键清理已结束任务") { confirmClear = true }
                        .disabled(busy != nil || tasks.isEmpty)
                }
            }
            if loading { ProgressView("读取任务状态…") }
            else if tasks.isEmpty && error == nil { ContentUnavailableView("暂无生成任务", systemImage: "tray") }
            List(tasks) { task in
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Text(task.label).font(.headline)
                        Text(task.statusLabel).foregroundStyle(.secondary)
                        if task.status == "running" { ProgressView().controlSize(.small) }
                        Spacer()
                        if !task.inFlight && ["completed", "failed", "paused", "cancelled"].contains(task.status) {
                            Button(archived ? "恢复" : "清理") { Task { await action(task, archived ? "restore" : "archive") } }.disabled(busy != nil)
                            if archived {
                                Button("彻底删除…", role: .destructive) { pendingDelete = task }.disabled(busy != nil)
                            }
                        }
                        if ["queued", "running", "paused"].contains(task.status) {
                            Button("取消") { Task { await action(task, "cancel") } }.disabled(busy != nil)
                        }
                        if task.resumable && ["failed", "paused", "cancelled"].contains(task.status) {
                            Button(task.inFlight ? "等待当前请求结束" : "继续") { Task { await action(task, "retry") } }
                                .disabled(busy != nil || task.inFlight)
                        }
                    }
                    Text(task.error ?? task.message ?? task.id).font(.caption).textSelection(.enabled)
                    if let total = task.total, total > 0 {
                        ProgressView(value: Double(task.completed ?? 0), total: Double(total))
                        Text("\(task.completed ?? 0) / \(total) 模块").font(.caption)
                    }
                }.padding(.vertical, 6)
            }
            Text("取消会停止后续步骤，当前网络请求可能需要等待返回。已生成课程和候选保留；继续任务可能产生 API 用量。")
                .font(.caption).foregroundStyle(.secondary)
        }.padding(24).frame(width: 720, height: 520)
            .confirmationDialog("清理已结束任务？", isPresented: $confirmClear) {
                Button("清理列表（可恢复）") { Task { await clearHistory() } }
            } message: { Text("只隐藏已完成、失败、暂停或取消的任务。正在运行的任务跳过；课程、候选、断点数据保留，可在“查看已清理”中恢复。") }
            .confirmationDialog("彻底清空已清理任务？", isPresented: $confirmDeleteAll, titleVisibility: .visible) {
                Button("永久删除任务记录", role: .destructive) { Task { await deletePermanently() } }
                Button("取消", role: .cancel) {}
            } message: { Text("删除后不能恢复。已经生成的课程与候选保留；正在运行的任务不会删除。") }
            .alert(item: $pendingDelete) { task in
                Alert(title: Text("彻底删除这条任务记录？"),
                      message: Text("删除后不能恢复；已生成课程或候选不会被删除。"),
                      primaryButton: .destructive(Text("永久删除")) { Task { await action(task, "delete") } },
                      secondaryButton: .cancel())
            }
            .onChange(of: archived) { _, _ in Task { await refresh() } }
            .sheet(isPresented: $showInbox) { PendingApprovalInbox() }
            .task {
                while !Task.isCancelled {
                    await refresh()
                    do { try await Task.sleep(for: .seconds(2)) } catch { return }
                }
            }
    }
    private func refresh() async {
        let requestedArchive = archived
        defer { loading = false }
        do {
            let (data, response) = try await URLSession.shared.data(from: URL(string: "http://127.0.0.1:8787/v1/jobs" + (requestedArchive ? "/archived" : ""))!)
            guard (response as? HTTPURLResponse)?.statusCode == 200 else { throw URLError(.badServerResponse) }
            struct Envelope: Decodable { let jobs: [GenerationTask] }
            guard requestedArchive == archived else { return }
            tasks = try JSONDecoder().decode(Envelope.self, from: data).jobs
            error = nil
        } catch { self.error = "任务状态读取失败：\(error.localizedDescription)" }
    }
    private func action(_ task: GenerationTask, _ action: String) async {
        busy = task.id; defer { busy = nil }
        do {
            var request = URLRequest(url: URL(string: "http://127.0.0.1:8787/v1/jobs/\(task.id)/\(action)")!)
            request.httpMethod = "POST"
            request.setValue(LocalGatewaySession.token, forHTTPHeaderField: "X-Trainer-Session")
            if action == "delete" {
                request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                request.httpBody = try JSONEncoder().encode(["confirmed": true])
            }
            let (data, response) = try await URLSession.shared.data(for: request)
            guard (response as? HTTPURLResponse)?.statusCode == 200 else {
                let value = try? JSONSerialization.jsonObject(with: data) as? [String: String]
                error = value?["error"] ?? "任务操作失败"; return
            }
            error = nil; await refresh()
        } catch { self.error = error.localizedDescription }
    }
    private func clearHistory() async {
        busy = "archive"; defer { busy = nil }
        do {
            var request = URLRequest(url: URL(string: "http://127.0.0.1:8787/v1/jobs/archive")!)
            request.httpMethod = "POST"
            request.setValue(LocalGatewaySession.token, forHTTPHeaderField: "X-Trainer-Session")
            let (_, response) = try await URLSession.shared.data(for: request)
            guard (response as? HTTPURLResponse)?.statusCode == 200 else { throw URLError(.badServerResponse) }
            await refresh()
        } catch { self.error = "清理失败，请重试：\(error.localizedDescription)" }
    }
    private func deletePermanently() async {
        busy = "delete"; defer { busy = nil }
        do {
            var request = URLRequest(url: URL(string: "http://127.0.0.1:8787/v1/jobs/delete")!)
            request.httpMethod = "POST"
            request.setValue(LocalGatewaySession.token, forHTTPHeaderField: "X-Trainer-Session")
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONEncoder().encode(["confirmed": true])
            let (data, response) = try await URLSession.shared.data(for: request)
            guard (response as? HTTPURLResponse)?.statusCode == 200 else {
                let value = try? JSONSerialization.jsonObject(with: data) as? [String: String]
                self.error = value?["error"] ?? "彻底删除失败"; return
            }
            self.error = nil
            await refresh()
        } catch { self.error = "彻底删除失败：\(error.localizedDescription)" }
    }
}
