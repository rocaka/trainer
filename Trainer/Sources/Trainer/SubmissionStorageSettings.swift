import SwiftUI

private struct SubmissionStorageSummary: Decodable {
    let snapshotCount, snapshotBytes, protectedCount, feedbackCount: Int
    let automaticCleanup: Bool
}

private struct SubmissionCleanupResult: Decodable {
    let removedCount, removedBytes, protectedCount: Int
    let feedbackPreserved: Bool
}

private struct SubmissionStorageError: Decodable { let error: String }
private struct SubmissionStorageFailure: LocalizedError {
    let message: String
    var errorDescription: String? { message }
}

struct SubmissionStorageSettings: View {
    @Environment(\.dismiss) private var dismiss
    @State private var summary: SubmissionStorageSummary?
    @State private var isLoading = false
    @State private var error: String?
    @State private var result: String?
    @State private var confirmsCleanup = false

    var body: some View {
        VStack(alignment: .leading, spacing: 22) {
            HStack {
                Label("提交材料", systemImage: "externaldrive.badge.checkmark").font(.title2.bold())
                Spacer()
                Button("完成") { dismiss() }
            }
            Text("Trainer 将课程合同要求的已授权代码保存在本机私有目录。这里不展示或上传额外文件。")
                .font(.callout).foregroundStyle(.secondary)

            GroupBox {
                if let summary {
                    VStack(spacing: 14) {
                        metric("源码快照", "\(summary.snapshotCount) 份", "doc.on.doc")
                        Divider()
                        metric("本机占用", ByteCountFormatter.string(fromByteCount: Int64(summary.snapshotBytes), countStyle: .file), "internaldrive")
                        Divider()
                        metric("进行中保护", "\(summary.protectedCount) 份", "lock.shield")
                        Divider()
                        metric("历史反馈", "\(summary.feedbackCount) 条保留", "checkmark.message")
                    }
                } else if isLoading {
                    ProgressView("正在读取本机提交材料…").frame(maxWidth: .infinity, alignment: .leading)
                } else {
                    Text("尚未读取存储状态。") .foregroundStyle(.secondary)
                }
            }

            Label("不会自动清理。手动清理只删除已结束提交的源码快照；评分反馈、提交状态和进行中的材料都会保留。",
                  systemImage: "hand.raised")
                .font(.caption).foregroundStyle(.secondary)

            if let error { Text(error).font(.callout).foregroundStyle(.orange) }
            if let result { Text(result).font(.callout).foregroundStyle(.green) }

            HStack {
                Button { Task { await load() } } label: { Label("刷新占用", systemImage: "arrow.clockwise") }
                    .disabled(isLoading)
                Spacer()
                Button(role: .destructive) { confirmsCleanup = true } label: {
                    Label("清理已结束提交材料", systemImage: "trash")
                }
                .disabled(isLoading || summary.map { $0.snapshotCount <= $0.protectedCount } != false)
            }
            Spacer()
        }
        .padding(24).frame(width: 560, height: 510)
        .task { await load() }
        .confirmationDialog("清理已结束提交的源码快照？", isPresented: $confirmsCleanup, titleVisibility: .visible) {
            Button("清理材料，保留反馈", role: .destructive) { Task { await cleanup() } }
            Button("取消", role: .cancel) {}
        } message: {
            Text("正在排队或评判的材料不会删除；历史评分反馈与提交状态仍会保留。此操作不能撤销。")
        }
    }

    private func metric(_ title: String, _ value: String, _ icon: String) -> some View {
        HStack {
            Label(title, systemImage: icon).foregroundStyle(.secondary)
            Spacer()
            Text(value).fontWeight(.semibold)
        }
    }

    private func request(_ path: String, method: String = "GET", body: Data? = nil) async throws -> Data {
        var request = URLRequest(url: URL(string: "http://127.0.0.1:8787\(path)")!)
        request.httpMethod = method
        request.setValue(LocalGatewaySession.token, forHTTPHeaderField: "X-Trainer-Session")
        if let body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = body
        }
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            throw SubmissionStorageFailure(message: (try? JSONDecoder().decode(SubmissionStorageError.self, from: data).error) ?? "提交材料服务暂不可用。")
        }
        return data
    }

    @MainActor private func load() async {
        isLoading = true; error = nil
        defer { isLoading = false }
        do {
            summary = try JSONDecoder().decode(SubmissionStorageSummary.self,
                from: try await request("/v1/course-submissions/storage"))
        } catch { self.error = "无法读取提交材料：\(error.localizedDescription)" }
    }

    @MainActor private func cleanup() async {
        isLoading = true; error = nil; result = nil
        defer { isLoading = false }
        do {
            let body = try JSONSerialization.data(withJSONObject: ["confirm": true, "preserveFeedback": true])
            let cleaned = try JSONDecoder().decode(SubmissionCleanupResult.self,
                from: try await request("/v1/course-submissions/storage", method: "DELETE", body: body))
            result = "已清理 \(cleaned.removedCount) 份材料（\(ByteCountFormatter.string(fromByteCount: Int64(cleaned.removedBytes), countStyle: .file))）；历史反馈已保留。"
            await load()
        } catch { self.error = "清理失败：\(error.localizedDescription)" }
    }
}
