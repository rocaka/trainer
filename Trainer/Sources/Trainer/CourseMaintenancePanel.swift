import SwiftUI

struct CourseMaintenancePanel: View {
    @ObservedObject var model: WorkspaceModel
    let plan: ProjectPlan
    @State private var confirmUpgrade = false
    private var operation: String {
        ["open": "读取课程", "review": "检查课程", "supplement": "检查并补全", "upgrade": "升级课程"][model.planningMode] ?? "课程任务"
    }
    private var unresolved: Int {
        (plan.contentReviews ?? []).flatMap(\.findings).filter { $0.status != "covered" }.count
    }
    private func run(_ mode: String) {
        if let skill = model.activeTeachingSkill { Task { await model.loadProjectPlan(skill, mode: mode) } }
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: "books.vertical.fill").font(.title2).foregroundStyle(.tint)
                    .frame(width: 42, height: 42).background(Color.accentColor.opacity(0.12), in: RoundedRectangle(cornerRadius: 12))
                VStack(alignment: .leading, spacing: 4) {
                    Text("课程资料").font(.headline).foregroundStyle(.primary)
                    Text("\(plan.lessons.count) 课已保存 · \(plan.lessons.filter { model.recordedConcepts.contains($0.id) }.count) 课有学习凭据")
                        .font(.caption).fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 0)
                Menu {
                    Button("仅检查，不补课") { run("review") }
                    Button("按新规则升级…") { confirmUpgrade = true }
                } label: { Image(systemName: "ellipsis").accessibilityLabel("高级课程操作") }
                .fixedSize().disabled(model.isPlanning)
            }
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 14) { action; explanation }
                VStack(alignment: .leading, spacing: 10) { action; explanation }
            }
            if model.isPlanning {
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        ProgressView().controlSize(.small)
                        Text("\(operation)进行中").font(.subheadline.weight(.medium))
                        Spacer()
                        if model.planningTotal > 0 { Text("\(model.planningCompleted)/\(model.planningTotal) 模块").font(.caption).monospacedDigit() }
                    }
                    if model.planningTotal > 0 { ProgressView(value: Double(model.planningCompleted), total: Double(model.planningTotal)) }
                    Text(model.planningStatus).font(.caption).fixedSize(horizontal: false, vertical: true)
                    TimelineView(.periodic(from: .now, by: 1)) { time in
                        Text("当前阶段 \(max(0, Int(time.date.timeIntervalSince(model.planningStageStarted)))) 秒 · 已有课程可继续学习")
                            .font(.caption2).monospacedDigit()
                    }
                }
            } else if let error = model.planningError {
                VStack(alignment: .leading, spacing: 8) {
                    Label("\(operation)未完成，已保存内容不受影响", systemImage: "exclamationmark.circle").foregroundStyle(.orange)
                    Text(error).font(.caption).fixedSize(horizontal: false, vertical: true).textSelection(.enabled)
                    Button("继续本次任务") {
                        if let skill = model.activeTeachingSkill {
                            Task { await model.loadProjectPlan(skill, mode: model.planningMode, retryJobID: model.planningJobID) }
                        }
                    }
                }.padding(12).frame(maxWidth: .infinity, alignment: .leading)
                    .background(.orange.opacity(0.07), in: RoundedRectangle(cornerRadius: 10))
            } else {
                Label(plan.contentReviews?.isEmpty == false ? "检查报告已保存 · \(unresolved) 项待确认" : "课程已保存 · 尚待内容检查", systemImage: "internaldrive")
                    .font(.caption)
            }
            Divider()
        }
        .confirmationDialog("按当前规则生成升级版？", isPresented: $confirmUpgrade, titleVisibility: .visible) {
            Button("生成升级版") { run("upgrade") }
        } message: { Text("会调用已配置的 AI 并产生用量。旧课程保留，新版课程进度单独记录。") }
    }
    private var action: some View {
        Button { run("supplement") } label: { Label("检查并补全", systemImage: "checkmark.shield") }
            .buttonStyle(.borderedProminent).controlSize(.large).fixedSize().disabled(model.isPlanning)
    }
    private var explanation: some View {
        Text("先检查，再补缺项并复查。每步保存，不重写原课；调用 AI 会产生用量。")
            .font(.caption).fixedSize(horizontal: false, vertical: true)
    }
}
