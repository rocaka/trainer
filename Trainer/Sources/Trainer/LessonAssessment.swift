import SwiftUI

struct LessonAssessment: View {
    @Environment(\.dismiss) private var dismiss
    let planID, lessonID: String
    @State var answer: String
    let evidenceType: String
    @State private var busy = false
    @State private var result: String?
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack { Text("本课能力评估").font(.title2.bold()); Spacer(); Button("完成") { dismiss() } }
            Text("将本课内容和下方凭据发送给已配置的 DeepSeek，返回原文依据、评估结果与下一项练习。结果是课堂评估，不代表语言整体认证。")
                .font(.callout).foregroundStyle(.secondary)
            LabeledContent("凭据类型", value: evidenceLabel)
            Text("类型由当前教练问题自动确定，不能手动切换。")
                .font(.caption).foregroundStyle(.secondary)
            TextEditor(text: $answer).font(.body).frame(minHeight: 150).padding(8).background(.thinMaterial)
            HStack {
                Button(busy ? "正在评估…" : "提交评估") { Task { await assess() } }.disabled(busy || answer.count < 6)
                if busy { ProgressView().controlSize(.small) }
            }
            if let result { ScrollView { Text(result).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading) }.frame(maxHeight: 160) }
        }.padding(24).frame(width: 650, height: 570)
    }
    private var evidenceLabel: String {
        ["reflection": "概念回讲", "reading": "代码阅读", "writing": "代码编写",
         "debugging": "调试验证", "transfer": "迁移应用"][evidenceType] ?? "概念回讲"
    }
    private func assess() async {
        busy = true; defer { busy = false }
        do {
            var request = URLRequest(url: URL(string: "http://127.0.0.1:8787/v1/assessments")!)
            request.httpMethod = "POST"; request.timeoutInterval = 100
            request.setValue(LocalGatewaySession.token, forHTTPHeaderField: "X-Trainer-Session")
            request.httpBody = try JSONEncoder().encode(["planId": planID, "lessonId": lessonID, "answer": answer, "evidenceType": evidenceType])
            let (data, response) = try await URLSession.shared.data(for: request)
            let value = (try JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
            guard (response as? HTTPURLResponse)?.statusCode == 200 else { result = value["error"] as? String ?? "评估失败"; return }
            result = "课堂评分：\(value["score"] ?? 0) / 4\n\n依据：\(value["quote"] ?? "")\n\n\(value["feedback"] ?? "")\n\n下一步：\(value["nextStep"] ?? "")"
        } catch { result = error.localizedDescription }
    }
}
