import SwiftUI

struct TrainerSettings: View {
    @Environment(\.dismiss) private var dismiss
    @AppStorage("trainer.reading.size") private var size = 15.0
    @AppStorage("trainer.reading.style") private var style = "system"
    @AppStorage("trainer.code.size") private var codeSize = 14.0
    @AppStorage("trainer.glass.shade") private var shade = 0.28
    @AppStorage("trainer.motion.enabled") private var motion = true
    @State private var destination: String?
    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            HStack { Label("设置", systemImage: "gearshape").font(.title2); Spacer(); Button("完成") { dismiss() } }
            Form {
                Section("阅读与排版 · 即时保存到本机") {
                    Picker("正文字体", selection: $style) {
                        Text("系统黑体").tag("system")
                        Text("圆润字体").tag("rounded")
                        Text("衬线阅读").tag("serif")
                    }
                    HStack { Text("课程正文 \(Int(size)) pt"); Slider(value: $size, in: 13...22, step: 1) }
                    HStack { Text("代码字号 \(Int(codeSize)) pt"); Slider(value: $codeSize, in: 12...22, step: 1) }
                    Text("清晰的排版，让每一次理解更轻松。")
                        .font(.system(size: size, design: readingDesign(style))).padding(.vertical, 8)
                    Text("字体选项用于课程 Markdown 正文；代码保持等宽，导航保留系统字号。")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Section("外观与辅助功能") {
                    HStack { Text("玻璃遮罩 \(Int(shade * 100))%"); Slider(value: $shade, in: 0.15...0.8) }
                    Toggle("启用流水动效", isOn: $motion)
                    Text("系统开启“减少动态效果”或“减少透明度”时优先遵循系统设置。封面在档案页更换。")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Section("服务与工作流") {
                    Button("AI 服务 · 接口、模型、密钥与连接测试") { destination = "ai" }
                    Button("VS Code · 配对与项目授权") { destination = "vscode" }
                    Button("账户、云同步与 GitHub") { destination = "services" }
                    Button("生成任务 · 进度、继续与清理") { destination = "tasks" }
                    Button("提交材料 · 占用、保留与清理") { destination = "submissions" }
                    Text("资料编辑、封面以及本机数据备份入口保留在学习档案页。")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Button("恢复阅读与外观默认值") { size = 15; codeSize = 14; style = "system"; shade = 0.28; motion = true }
            }.formStyle(.grouped)
        }.padding(24).frame(width: 600, height: 650)
            .sheet(isPresented: Binding(get: { destination != nil }, set: { if !$0 { destination = nil } })) {
                switch destination {
                case "ai": AIServiceSettings()
                case "vscode": VSCodePairing()
                case "submissions": SubmissionStorageSettings()
                case "services": ConnectedServicesSettings()
                default: TaskCenter()
                }
            }
    }
}

func readingDesign(_ style: String) -> Font.Design {
    style == "serif" ? .serif : style == "rounded" ? .rounded : .default
}
