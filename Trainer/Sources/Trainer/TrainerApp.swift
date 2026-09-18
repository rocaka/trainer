import SwiftUI
import AppKit
import Foundation

enum LocalGatewaySession {
    static var token = ""
}

@main
struct TrainerApp: App {
    var body: some Scene {
        WindowGroup("Trainer") {
            TrainerWorkspace()
                .progressViewStyle(FluidProgressStyle())
                .frame(minWidth: 1120, minHeight: 700)
        }
        .windowStyle(.hiddenTitleBar)
        Settings { TrainerSettings() }
    }
}

struct Concept: Identifiable, Hashable {
    let id: String
    let title: String
    let level: String
    let status: Status

    enum Status: String {
        case mastered = "已完成练习"
        case current = "正在学习"
        case next = "下一步"
    }
}

struct EditorContext: Decodable {
    let language: String
    let selection: String
    let relativePath: String
    let receivedAt: String
    let teachingJobId: String?
}

@MainActor
final class GatewayController: ObservableObject {
    @Published private(set) var isAvailable = false
    private var process: Process?

    func ensureRunning() async {
        LocalGatewaySession.token = UserDefaults.standard.string(forKey: "gatewaySession") ?? ""
        if await healthCheck() {
            isAvailable = true
            return
        }
        launchBundledGateway()
        // A first launch needs a short moment for Python to bind localhost.
        for _ in 0..<8 {
            try? await Task.sleep(for: .milliseconds(300))
            if await healthCheck() {
                isAvailable = true
                return
            }
        }
    }

    private func healthCheck() async -> Bool {
        guard let url = URL(string: "http://127.0.0.1:8787/health") else { return false }
        do {
            let (_, response) = try await URLSession.shared.data(from: url)
            return (response as? HTTPURLResponse).map { (200...299).contains($0.statusCode) } ?? false
        } catch { return false }
    }

    private func launchBundledGateway() {
        guard process == nil else { return }
        let bundled = Bundle.main.resourceURL?.appendingPathComponent("gateway", isDirectory: true)
        let development = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
            .deletingLastPathComponent().appendingPathComponent("gateway", isDirectory: true)
        let gatewayDirectory = (bundled?.appendingPathComponent("server.py").isFileURL == true && FileManager.default.fileExists(atPath: bundled!.appendingPathComponent("server.py").path)) ? bundled! : development
        guard FileManager.default.fileExists(atPath: gatewayDirectory.appendingPathComponent("server.py").path) else { return }
        let task = Process()
        let sessionToken = UUID().uuidString
        UserDefaults.standard.set(sessionToken, forKey: "gatewaySession")
        LocalGatewaySession.token = sessionToken
        task.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        task.arguments = ["python3", "server.py"]
        task.currentDirectoryURL = gatewayDirectory
        var environment = ProcessInfo.processInfo.environment
        environment["TRAINER_GATEWAY_SESSION_TOKEN"] = sessionToken
        let cloudEndpoint = UserDefaults.standard.string(forKey: "trainer.cloud.endpoint")?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if !cloudEndpoint.isEmpty { environment["TRAINER_CLOUD_ENDPOINT"] = cloudEndpoint }
        // The Gateway also serves the connection-status card.  Pass along the
        // build-time Device Flow client ID so the card and the Swift UI use one
        // consistent GitHub configuration.
        let githubClientID = (Bundle.main.object(forInfoDictionaryKey: "TrainerGitHubClientID") as? String ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        if !githubClientID.isEmpty { environment["TRAINER_GITHUB_CLIENT_ID"] = githubClientID }
        // The signed app bundle is immutable; runtime caches belong outside it.
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        task.environment = environment
        task.standardOutput = FileHandle.nullDevice
        task.standardError = FileHandle.nullDevice
        do {
            try task.run()
            process = task
        } catch { return }
    }
}

private struct EditorContextEnvelope: Decodable {
    let context: EditorContext?
}

private struct PythonLabRequest: Encodable {
    let code: String
}

struct PythonLabTrace: Decodable, Identifiable {
    let action: String
    let label: String?
    let value: String?
    var id: String { "\(action)-\(label ?? "")-\(value ?? "")" }
}

struct PythonLabResult: Decodable {
    let output: [String]
    let trace: [PythonLabTrace]
    let environment: [String: String]
}

enum FoundationLanguage: String, CaseIterable, Identifiable {
    case javaScript
    case python
    case solidity

    var id: String { rawValue }
    var title: String {
        switch self {
        case .javaScript: "JavaScript / TypeScript"
        case .python: "Python"
        case .solidity: "Solidity"
        }
    }
    var source: String {
        switch self {
        case .javaScript: "let name = \"小明\""
        case .python: "name = \"小明\""
        case .solidity: "string memory name = \"小明\";"
        }
    }
    var languageNote: String {
        switch self {
        case .javaScript: "let 表示：现在新建一个标签。"
        case .python: "Python 不需要写 let；把内容放到 name 这个标签上，就完成了。"
        case .solidity: "string memory 是 Solidity 对“文字”和“暂时放在哪里”的额外说明；先认识 name 与“小明”，这些词会在后续展开。"
        }
    }
}

struct Lesson {
    let title: String
    let objective: String
    let code: String
    let layers: [(String, String)]

    static func beginner(for language: FoundationLanguage, conceptID: String = "reading") -> Lesson {
        guard conceptID == "reading" else { return foundationStep(conceptID, language: language) }
        return Lesson(
            title: "第 1 课：代码在表达什么？",
            objective: "从你当前的 \(language.title) 语境开始，认识“值”和“名字”。",
            code: language.source,
            layers: [
                ("人话", "这句话的意思是：把“小明”这个文字记下来，并给它贴上 name 这个标签。"),
                ("拆开看", language.languageNote + " name：标签的名字。\"小明\"：要记住的文字。"),
                ("为什么要这样", "程序不能像人一样记住“那个人”。给信息一个名字，后面的代码才能再次找到它。")
            ]
        )
    }

    private static func foundationStep(_ id: String, language: FoundationLanguage) -> Lesson {
        let items: [String: (String, String, String, [(String, String)])] = [
            "values": ("第 2 课：值与变量", "在 \(language.title) 里区分“名字”与会变化的“值”。", language == .python ? "score = 18\nscore = score + 1" : "let score = 18;\nscore = score + 1;", [("人话", "先记住 18，再把它改成 19；名字 score 一直指向当前的值。"), ("拆开看", "= 是把右侧计算出的值交给左侧名字；+ 1 是在当前值上加一。"), ("为什么要这样", "程序需要用稳定的名字追踪会变化的信息，例如分数、余额或库存。")]),
            "conditions": ("第 3 课：条件判断", "让程序在不同情况做不同的事。", language == .python ? "if score >= 60:\n    print(\"通过\")" : "if (score >= 60) {\n  console.log(\"通过\");\n}", [("人话", "如果分数达到 60，就告诉你通过。"), ("拆开看", "if 后面是一个会得到“是/否”的判断；缩进或大括号包住满足条件时才执行的步骤。"), ("为什么要这样", "真实项目需要根据登录状态、库存和权限选择不同路径。")]),
            "functions": ("第 4 课：函数，把步骤命名", "把会重复的一组步骤取名，并在需要时调用。", language == .python ? "def greet(name):\n    print(\"你好\", name)\ngreet(\"小明\")" : "function greet(name) {\n  console.log(\"你好\", name);\n}\ngreet(\"小明\");", [("人话", "先把“打招呼”这件事命名，然后把小明交给它完成。"), ("拆开看", "函数名是可复用步骤的入口；括号里的 name 是这一次传入的信息。"), ("为什么要这样", "重复逻辑集中在一个地方，修改规则时不必到处改代码。")]),
            "types": ("第 5 课：类型，信息的种类", "认识文字、数字和真假，避免把不同种类的信息混在一起。", language == .python ? "name = \"小明\"\nage = 18\nis_member = True" : "const name = \"小明\";\nconst age = 18;\nconst isMember = true;", [("人话", "名字是文字，年龄是数字，会员资格只有是或否。"), ("拆开看", "引号通常表示文字；不带引号的 18 是数字；true/True 表示真假。"), ("为什么要这样", "类型让程序知道能对数据做什么，并更早发现错误。")]),
            "projects": ("第 6 课：读懂一个小项目", "按“入口、数据、规则、输出”的顺序建立项目地图。", language == .python ? "def main():\n    score = 18\n    print(score)\nmain()" : "function main() {\n  const score = 18;\n  console.log(score);\n}\nmain();", [("人话", "从 main 开始：准备数据，再执行规则，最后把结果展示出来。"), ("拆开看", "入口函数把项目流程串起来；局部变量保存这一次运行需要的数据。"), ("为什么要这样", "先建立地图，再深入每个文件，读项目不会被细节淹没。")])
        ]
        guard let value = items[id] else { return beginner(for: language) }
        return Lesson(title: value.0, objective: value.1, code: value.2, layers: value.3)
    }

    static let transfer = Lesson(
        title: "读懂一笔链上转账",
        objective: "解释余额检查、调用者身份与原子状态变更。",
        code: """
mapping(address => uint256) public balances;

function transfer(address to, uint256 amount) external {
    require(balances[msg.sender] >= amount, \"Insufficient balance\");
    balances[msg.sender] -= amount;
    balances[to] += amount;
}

""",
        layers: [
            ("业务", "从调用者余额转移 amount 给 to。"),
            ("语法", "mapping 将 address 映射到无符号整数余额；external 表示外部账户可调用。"),
            ("运行时", "msg.sender 是本次交易的直接调用者。require 不满足时，整个调用回滚。"),
            ("安全", "此例没有外部合约调用，因此没有由转账动作引出的重入窗口；真实合约仍需设计访问控制与事件。")
        ]
    )
}

struct ProjectLesson: Decodable, Identifiable {
    let id, title, objective, language, code, explanation, syntax, rationale, exercise, reflection, source: String
    let contentType: String?
    let practiceTask: CoursePracticeTask?
    var isProjectBrief: Bool {
        if let contentType { return contentType == "project-brief" }
        let sample = title + "\n" + objective + "\n" + explanation
        return sample.contains("最小可交付") || (sample.contains("安全边界") && sample.contains("学习者假设"))
    }
    var sectionTitle: String { isProjectBrief ? "项目启动说明" : "课程讲解" }
    var lesson: Lesson {
        let layers = isProjectBrief
            ? [("目标与边界", explanation), ("环境与语法", syntax), ("设计理由", rationale)]
            : [("人话", explanation), ("拆开看", syntax), ("为什么要这样", rationale)]
        return Lesson(title: title, objective: objective, code: code, layers: layers)
    }
}
struct CoursePracticeTask: Decodable {
    let prompt: String
    let requiredFiles, acceptance: [String]
}
private struct PreparedLessonTask: Decodable { let task: CoursePracticeTask }
private struct CourseTaskEnvelope: Decodable {
    struct Contract: Decodable {
        struct Criterion: Decodable { let description: String }
        let prompt: String
        let requiredFiles: [String]
        let rubric: [Criterion]
    }
    let contract: Contract
}

struct SubmissionDisclosure: Decodable, Identifiable {
    let provider, model, host, evaluatorKey, method, notice: String
    let executesCode: Bool
    var id: String { evaluatorKey }
}

private struct SubmissionWorkspace: Decodable {
    let id, root, plan_id: String
    let valid: Bool?
}
private struct SubmissionWorkspaces: Decodable { let active: [SubmissionWorkspace] }
private struct CourseSubmissionRequest: Encodable {
    let planId, lessonId, bindingId, requestKey, evaluatorKey, answer: String
    let consent: Bool
}
private struct CourseSubmissionResponse: Decodable {
    let id, status: String
    let assessment: CourseSubmissionAssessment?
}
private struct CourseSubmissionAssessment: Decodable {
    let feedback, nextStep, outcome, method: String
}

struct CoursePracticeTaskView: View {
    let task: CoursePracticeTask
    @ObservedObject var model: WorkspaceModel
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label(model.codeTaskTitle, systemImage: "hammer").font(.headline)
            RichMarkdownPreview(text: task.prompt)
            Text("任务文件").font(.subheadline.weight(.semibold))
            ForEach(Array(task.requiredFiles.enumerated()), id: \.offset) { _, path in
                Label(path, systemImage: "doc.text").font(.system(.caption, design: .monospaced))
                    .textSelection(.enabled)
            }
            Text("验收标准 · 逐项满足").font(.subheadline.weight(.semibold))
            ForEach(Array(task.acceptance.enumerated()), id: \.offset) { index, criterion in
                HStack(alignment: .top, spacing: 8) {
                    Text("\(index + 1).").foregroundStyle(.secondary)
                    Text(criterion).fixedSize(horizontal: false, vertical: true)
                }.font(.callout)
            }
            Text("在关联的 VS Code 工作区完成并保存文件。提交时自动检查保存状态、收集任务文件并去重，再按上方标准评审。")
                .font(.caption).foregroundStyle(.secondary)
            TextField("补充说明或运行输出（可选）", text: $model.courseAnswer, axis: .vertical)
                .lineLimit(2...6).textFieldStyle(.plain).glassInput()
            Button {
                Task { await model.prepareCourseSubmission() }
            } label: {
                Label(model.isSubmittingCourse ? "正在准备…" : "提交并检查", systemImage: "arrow.up.doc")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .disabled(model.isSubmittingCourse)
            if let status = model.courseSubmissionStatus {
                Text(status).font(.caption).foregroundStyle(model.courseSubmissionError == nil ? Color.secondary : Color.orange)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(.white.opacity(0.04), in: RoundedRectangle(cornerRadius: 12))
        .task(id: "\(model.projectPlan?.planId ?? "")|\(model.selectedConceptID)") {
            await model.restoreCourseSubmission()
        }
        .sheet(item: $model.submissionDisclosure) { disclosure in
            VStack(alignment: .leading, spacing: 16) {
                Text("确认提交\(model.codeTaskTitle)").font(.title2.bold())
                LabeledContent("评判服务", value: disclosure.provider)
                LabeledContent("模型", value: disclosure.model)
                LabeledContent("目标主机", value: disclosure.host)
                LabeledContent("材料范围", value: "本课已授权的 \(task.requiredFiles.count) 个文件")
                Label("仅进行静态评审，不执行代码或测试", systemImage: "doc.text.magnifyingglass")
                    .foregroundStyle(.secondary)
                Text(disclosure.notice).font(.callout).foregroundStyle(.secondary)
                HStack {
                    Button("取消") { model.submissionDisclosure = nil }
                    Spacer()
                    Button("确认并提交") { Task { await model.confirmCourseSubmission(disclosure) } }
                        .buttonStyle(.borderedProminent)
                }
            }
            .padding(24).frame(width: 480)
        }
    }
}
struct CoverageModule: Decodable { let title: String; let lessonCount: Int; let covered: Bool }
struct CoverageAudit: Decodable {
    let status: String
    let coveredModules, totalModules: Int
    let modules: [CoverageModule]
    let limitations: [String]
}
struct ContentFinding: Decodable { let requirement, status, lessonId, quote, recommendation: String }
struct ContentReview: Decodable { let module, status, method: String; let findings: [ContentFinding] }
struct CourseQualityFinding: Decodable { let lessonId, kind, status, detail: String }
struct CourseQualityAudit: Decodable {
    let version: Int
    let status: String
    let passed, total: Int
    let limitations: [String]
    let findings: [CourseQualityFinding]
}
struct PlanSubmissionPolicy: Decodable {
    let version: Int
    let mode, primaryRole: String
    var guidance: String {
        guard version == 1 else { return "提交来源版本尚不支持，请更新课程。" }
        switch (mode, primaryRole) {
        case ("project-practice", "course-task"), ("course", "course-task"):
            return "课程实践：提交本课代码教学要求完成的成果。教练追问单独记录，不替代课程实践。"
        case ("project-import", "coach-exercise"):
            return "项目练习：围绕教练明确布置的任务提交。原项目代码是参考材料，不能直接作为已完成成果。"
        default:
            return "提交来源尚未明确，请更新课程后再提交实践成果。"
        }
    }
}
struct ProjectPlan: Decodable {
    let planId: String
    let lessons: [ProjectLesson]
    let moduleCount: Int?
    let sourceFileCount: Int?
    let coverageStatus: String?
    let moduleTitles: [String]?
    let coverageAudit: CoverageAudit?
    let contentReviews: [ContentReview]?
    let qualityAudit: CourseQualityAudit?
    let submissionPolicy: PlanSubmissionPolicy?
}
struct ProjectPlanJob: Decodable { let id: String; let status: String; let result: ProjectPlan?; let partialResult: ProjectPlan?; let error: String?; let completed: Int?; let total: Int?; let message: String? }
struct LearningPosition: Decodable { let lessonId: String?; let recorded: [String]; let passed: [String] }

struct AICoachTurn: Decodable {
    let source: String
    let skillId: String
    let question: String
    let options: [String]
    let correctIndex: Int
    let feedback: String
    let reflectionPrompt: String
    let evidenceType: String?
}

private struct CoachAnswerAssessment: Decodable {
    let score: Int
    let quote, feedback, nextStep: String
}

private struct AICoachTurnRequest: Encodable {
    let skillId: String
    let lessonTitle: String
    let code: String
    let language: String
    let layer: String
    let focusTitle: String
    let focusContent: String
    let reflectionContext: String
}

@MainActor
final class WorkspaceModel: ObservableObject {
    enum Track { case foundations, solidity }

    @Published var track: Track = .foundations
    @Published var foundationLanguage: FoundationLanguage = .javaScript
    @Published var selectedConceptID = "reading"
    @Published var selectedLayer = "人话"
    @Published var prediction: Prediction?
    @Published var reflection = ""
    @Published var completedEvidence = false
    @Published var evidenceError: String?
    @Published var answerFeedback: String?
    @Published var editorContext: EditorContext?
    @Published var editorContextMessage: String?
    @Published var activeTeachingSkill: SkillSummary?
    @Published var showTeachingHub = false
    @Published var automaticCandidate: SkillGenerationResponse?
    @Published var showAutomaticCandidate = false
    @Published var automaticCandidateError: String?
    @Published var learnerQuestion = ""
    @Published var isDetectingTeachingNeed = false
    @Published var isImportingProject = false
    @Published var projectPlan: ProjectPlan?
    @Published var isPlanning = false
    @Published var planningStatus = "正在准备教学模块…"
    @Published var planningCompleted = 0
    @Published var planningTotal = 0
    @Published var planningStageStarted = Date()
    @Published var planningLastResponse = Date()
    @Published var planningError: String?
    @Published var planningMode = "open"
    @Published var planningJobID: String?
    @Published var submissionDisclosure: SubmissionDisclosure?
    @Published var isSubmittingCourse = false
    @Published var courseSubmissionStatus: String?
    @Published var courseSubmissionError: String?
    @Published var courseAnswer = ""
    @Published var preparedLessonTasks: [String: CoursePracticeTask] = [:]
    @Published var isPreparingLessonTask = false
    @Published var lessonTaskError: String?
    @Published var coachSection = "代码任务"
    var coachPending: Bool { isLoadingAICoach || (aiCoachTurn == nil && aiCoachError == nil && projectLesson != nil) }
    @Published var recordedConcepts: Set<String> = []
    @Published var passedCourseLessons: Set<String> = []
    private var planTask: Task<Void, Never>?
    var projectLesson: ProjectLesson? { projectPlan?.lessons.first { $0.id == selectedConceptID } }
    @Published var aiCoachTurn: AICoachTurn?
    @Published var aiCoachSelection: Int?
    @Published var isLoadingAICoach = false
    @Published var aiCoachStatus = ""
    @Published var aiCoachError: String?
    private var aiCoachCache: [String: AICoachTurn] = [:]
    @Published var importedProjectMessage: String?
    @Published var importedProject: ImportedProjectMetadata?
    @Published var showProjectImportProgress = false
    private var observedAutomaticJobs: Set<String> = []
    @Published var pythonExperimentCode = "name = \"小明\"\nprint(name)"
    @Published var pythonExperimentResult: PythonLabResult?
    @Published var pythonExperimentError: String?
    @Published var isRunningPythonExperiment = false
    @Published var showSkills = false
    @Published var showCourseBuilder = false
    @Published var showProjectPractice = false
    @Published var showLearnerProfile = false
    @Published var showAIService = false
    @Published var isRecordingEvidence = false

    enum Prediction: String, CaseIterable, Identifiable {
        case quotedText = "把“小明”改成“小红”"
        case label = "把 name 改成 other"
        case letWord = "把 let 改成 function"
        case keepsChanges = "前两次扣减仍会保留"
        case revertsAll = "整笔调用全部回滚"
        case onlyReceiver = "只撤销收款方余额"
        case scoreValue = "把 18 改成新的分数"
        case scoreLabel = "把 score 改成另一个名字"
        case conditionPasses = "分数达到 60 时才执行“通过”"
        case conditionAlways = "无论分数多少都会执行“通过”"
        case functionCall = "把“小明”交给 greet 这个步骤执行"
        case functionRename = "把 name 自动变成小红"
        case typeNumber = "age 是数字，可以参与计算"
        case typeText = "age 是文字，只能拼接"
        case projectEntry = "从 main 这个入口开始追踪流程"
        case projectOutput = "先找最后一行输出，不看入口"
        var id: String { rawValue }
    }

    let foundationConcepts = [
        Concept(id: "reading", title: "代码是什么", level: "第 1 步", status: .current),
        Concept(id: "values", title: "值与变量", level: "第 2 步", status: .next),
        Concept(id: "conditions", title: "条件判断", level: "第 3 步", status: .next),
        Concept(id: "functions", title: "函数：把步骤命名", level: "第 4 步", status: .next),
        Concept(id: "types", title: "类型：信息的种类", level: "第 5 步", status: .next),
        Concept(id: "projects", title: "读懂一个小项目", level: "第 6 步", status: .next)
    ]

    let solidityConcepts = [
        Concept(id: "functions", title: "函数与参数", level: "L2", status: .mastered),
        Concept(id: "evm.state", title: "链上状态", level: "L1", status: .current),
        Concept(id: "transactions", title: "交易与回滚", level: "L1", status: .current),
        Concept(id: "access", title: "权限控制", level: "L0", status: .next),
        Concept(id: "reentrancy", title: "重入风险", level: "L0", status: .next)
    ]

    var concepts: [Concept] {
        if activeTeachingSkill != nil {
            return (projectPlan?.lessons ?? []).enumerated().map { index, item in
                let requiresCode = projectPlan?.submissionPolicy?.primaryRole == "course-task" || projectPlan?.submissionPolicy?.primaryRole == "coach-exercise"
                let done = requiresCode ? passedCourseLessons.contains(item.id) : recordedConcepts.contains(item.id)
                return Concept(id: item.id, title: item.title, level: "第 \(index + 1) 课", status: done ? .mastered : (item.id == selectedConceptID ? .current : .next))
            }
        }
        let source = track == .foundations ? foundationConcepts : solidityConcepts
        guard let current = source.firstIndex(where: { $0.id == selectedConceptID }) else { return source }
        return source.enumerated().map { index, concept in
            Concept(id: concept.id, title: concept.title, level: concept.level, status: recordedConcepts.contains(concept.id) ? .mastered : (index == current ? .current : .next))
        }
    }
    var lesson: Lesson { projectLesson?.lesson ?? (track == .foundations ? .beginner(for: foundationLanguage, conceptID: selectedConceptID) : .transfer) }
    var currentConceptTitle: String { concepts.first(where: { $0.id == selectedConceptID })?.title ?? "当前课程" }
    var nextConceptTitle: String? {
        guard let index = concepts.firstIndex(where: { $0.id == selectedConceptID }), concepts.indices.contains(index + 1) else { return nil }
        return concepts[index + 1].title
    }
    var teachingTitle: String { activeTeachingSkill?.title ?? "选择一个教学方向" }
    var hasCourseCodeTask: Bool {
        guard let policy = projectPlan?.submissionPolicy else { return false }
        let supported = (policy.primaryRole == "course-task" && ["course", "project-practice"].contains(policy.mode)) ||
            (policy.primaryRole == "coach-exercise" && policy.mode == "project-import")
        return policy.version == 1 && supported
    }
    var codeTaskTitle: String {
        projectPlan?.submissionPolicy?.primaryRole == "coach-exercise" ? "教练代码任务" : "本课代码任务"
    }
    var courseTaskKey: String { "\(projectPlan?.planId ?? "")|\(selectedConceptID)" }
    var currentCourseTask: CoursePracticeTask? { projectLesson?.practiceTask ?? preparedLessonTasks[courseTaskKey] }
    var canAdvance: Bool {
        guard hasCourseCodeTask, projectPlan != nil else { return completedEvidence }
        return passedCourseLessons.contains(selectedConceptID)
    }
    var answerPrompt: String { aiCoachTurn?.reflectionPrompt ?? projectLesson?.reflection ?? coachReflectionPrompt }
    var activeLayer: String {
        lesson.layers.contains(where: { $0.0 == selectedLayer }) ? selectedLayer : (lesson.layers.first?.0 ?? selectedLayer)
    }
    var coachRefreshKey: String { "\(projectPlan?.planId ?? "local")|\(activeTeachingSkill?.id ?? "core.adaptive-teaching")|\(selectedConceptID)|\(foundationLanguage.title)|\(activeLayer)" }
    var coachFocusTitle: String { projectLesson == nil ? "课程讲解" : "观察与练习" }
    var coachFocusContent: String {
        let value = projectLesson?.exercise ?? selectedLayerText
        return String(value.prefix(6_000))
    }
    var coachReflectionContext: String {
        let value = projectLesson?.reflection ?? coachReflectionPrompt
        return String(value.prefix(2_400))
    }
    var currentEvidenceType: String {
        let supported = ["reflection", "reading", "transfer"]
        guard let generated = aiCoachTurn?.evidenceType, supported.contains(generated) else { return "reflection" }
        return generated
    }
    var currentEvidenceTypeLabel: String {
        ["reflection": "概念回讲", "reading": "代码阅读", "writing": "代码编写",
         "debugging": "调试验证", "transfer": "迁移应用"][currentEvidenceType] ?? "概念回讲"
    }

    var coachQuestion: String {
        guard track == .foundations else { return "如果 `require` 失败，调用前已发生的状态修改会怎样？" }
        switch selectedConceptID {
        case "values": return "如果想让分数从 18 变成 19，最直接应该改哪一部分？"
        case "conditions": return "这段条件判断在什么情况下会打印“通过”？"
        case "functions": return "调用 `greet(\"小明\")` 时，“小明”被交给了什么？"
        case "types": return "代码里的 `age = 18` 中，18 最适合被当作什么？"
        case "projects": return "第一次读这个小项目，应该从哪里开始建立流程地图？"
        default: return "如果要把登记的“小明”换成“小红”，你觉得应该改哪一部分？"
        }
    }
    var coachReflectionPrompt: String {
        guard track == .foundations else { return "为什么余额检查失败时要让整笔调用回滚？" }
        switch selectedConceptID {
        case "values": return "请说说 score 这个名字和 18 这个值分别扮演什么角色？"
        case "conditions": return "请用自己的话解释：条件为真和为假时，程序分别会怎样走？"
        case "functions": return "请解释函数名、参数和一次调用之间的关系。"
        case "types": return "请说明文字、数字和真假为什么不能随便混用。"
        case "projects": return "请按入口、数据、规则、输出说出这个小项目的流程。"
        default: return "请试着解释：name 和“小明”分别是什么？"
        }
    }
    var coachOptions: [Prediction] {
        guard track == .foundations else { return [.keepsChanges, .revertsAll, .onlyReceiver] }
        switch selectedConceptID {
        case "values": return [.scoreValue, .scoreLabel, .letWord]
        case "conditions": return [.conditionPasses, .conditionAlways, .scoreLabel]
        case "functions": return [.functionCall, .functionRename, .scoreLabel]
        case "types": return [.typeNumber, .typeText, .letWord]
        case "projects": return [.projectEntry, .projectOutput, .functionRename]
        default: return [.quotedText, .label, .letWord]
        }
    }

    var selectedLayerText: String {
        lesson.layers.first(where: { $0.0 == activeLayer })?.1 ?? lesson.layers.first?.1 ?? ""
    }

    var predictionFeedback: String? {
        guard let prediction else { return nil }
        if track == .foundations && prediction == .quotedText {
            return "对了！name 是一个标签；要登记另一位同学，就改标签右侧引号里的文字。"
        }
        if track == .foundations {
            let correct: [String: Prediction] = [
                "reading": .quotedText, "values": .scoreValue, "conditions": .conditionPasses,
                "functions": .functionCall, "types": .typeNumber, "projects": .projectEntry
            ]
            if prediction == correct[selectedConceptID] {
                return "判断正确。\(lesson.layers.first?.1 ?? "")"
            }
            return "再对照这一课的代码：先找“被处理的信息”，再找决定它如何流动的规则。"
        }
        if prediction == .revertsAll {
            return "正确。require 失败会 revert：本次调用已经完成的状态变更、日志与后续行为都会撤销。"
        }
        return "接近了，但 EVM 的 revert 是原子性的：失败不会只撤销一部分状态。再看看 require 的运行时语义。"
    }

    func recordReflection() async {
        guard !isRecordingEvidence else { return }
        let submittedConcept = selectedConceptID
        let submittedPlan = projectPlan?.planId
        let submittedSkill = activeTeachingSkill?.id
        let answer = reflection.trimmingCharacters(in: .whitespacesAndNewlines)
        // A concise but meaningful explanation such as “name 是变量，小明是值”
        // must count as evidence; character count alone is not understanding.
        guard (6...16000).contains(answer.count) else {
            evidenceError = "请针对上方问题写出具体回答与依据（6–16000 字）。"
            return
        }
        isRecordingEvidence = true
        evidenceError = nil
        answerFeedback = nil
        let submittedQuestion = answerPrompt
        let submittedKind = currentEvidenceType
        defer { isRecordingEvidence = false }
        do {
            if let planID = submittedPlan {
                var evaluation = URLRequest(url: URL(string: "http://127.0.0.1:8787/v1/assessments")!)
                evaluation.httpMethod = "POST"
                evaluation.timeoutInterval = 100
                evaluation.setValue("application/json", forHTTPHeaderField: "Content-Type")
                evaluation.setValue(LocalGatewaySession.token, forHTTPHeaderField: "X-Trainer-Session")
                evaluation.httpBody = try JSONEncoder().encode([
                    "planId": planID, "lessonId": submittedConcept, "answer": answer,
                    "evidenceType": submittedKind, "question": submittedQuestion, "activity": "coach-text"])
                let (data, response) = try await URLSession.shared.data(for: evaluation)
                guard (response as? HTTPURLResponse)?.statusCode == 200 else {
                    throw GatewayFailure(message: (try? JSONDecoder().decode(GatewayError.self, from: data).error) ?? "评判暂未完成，请保留回答后重试。")
                }
                let result = try JSONDecoder().decode(CoachAnswerAssessment.self, from: data)
                guard submittedConcept == selectedConceptID, submittedPlan == projectPlan?.planId else { return }
                answerFeedback = "\(result.score >= 2 ? "回答通过" : "需要补充") · \(result.score)/4\n\(result.feedback)\n依据：\(result.quote)\n下一步：\(result.nextStep)"
                guard result.score >= 2 else { completedEvidence = false; return }
            }
            let conceptID = "\(submittedSkill ?? "programming"):\(submittedPlan ?? "local"):\(submittedConcept)"
            let evidenceLanguage = projectLesson?.language ?? (foundationLanguage == .javaScript ? "JavaScript" : foundationLanguage.title)
            let requestBody = EvidenceRequest(conceptId: conceptID, level: 1, evidenceType: submittedKind, note: answer, language: evidenceLanguage)
            var request = URLRequest(url: URL(string: "http://127.0.0.1:8787/v1/evidence")!)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONEncoder().encode(requestBody)
            let (_, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else { throw GatewayFailure(message: "学习证据未保存。") }
            if let planID = submittedPlan {
                var saved = Set(UserDefaults.standard.stringArray(forKey: "evidence." + planID) ?? [])
                saved.insert(submittedConcept)
                UserDefaults.standard.set(Array(saved), forKey: "evidence." + planID)
            }
            guard submittedPlan == projectPlan?.planId, submittedSkill == activeTeachingSkill?.id else { return }
            recordedConcepts.insert(submittedConcept)
            guard submittedConcept == selectedConceptID else { return }
            evidenceError = nil
            completedEvidence = true
            recordedConcepts.insert(selectedConceptID)
            if let plan = projectPlan { UserDefaults.standard.set(Array(recordedConcepts), forKey: "evidence." + plan.planId) }
        } catch {
            guard submittedConcept == selectedConceptID, submittedPlan == projectPlan?.planId, submittedSkill == activeTeachingSkill?.id else { return }
            evidenceError = error.localizedDescription
        }
    }

    func refreshAICoach() async {
        guard activeTeachingSkill == nil || projectLesson != nil else { return }
        let cacheKey = coachRefreshKey
        if let cached = aiCoachCache[cacheKey] {
            aiCoachTurn = cached
            aiCoachSelection = nil
            aiCoachStatus = ""
            aiCoachError = nil
            return
        }
        isLoadingAICoach = true
        aiCoachTurn = nil
        aiCoachSelection = nil
        aiCoachStatus = "正在读取当前 Skill 的教学约束…"
        aiCoachError = nil
        defer { if cacheKey == coachRefreshKey { isLoadingAICoach = false; aiCoachStatus = "" } }
        // The panel and bundled gateway start concurrently. Retry only startup
        // failures, so a first paint never leaves the learner stuck on fallback.
        var lastFailure = "本地 Gateway 没有返回可用的 AI 教练结果。"
        for attempt in 0..<4 {
            var shouldRetry = true
            do {
                guard !LocalGatewaySession.token.isEmpty else { throw GatewayFailure(message: "Gateway is starting") }
                let lesson = lesson
                try Task.checkCancellation()
                let requestBody = AICoachTurnRequest(
                    skillId: activeTeachingSkill?.id ?? "core.adaptive-teaching",
                    lessonTitle: lesson.title,
                    code: lesson.code,
                    language: projectLesson?.language ?? foundationLanguage.title,
                    layer: activeLayer,
                    focusTitle: coachFocusTitle,
                    focusContent: coachFocusContent,
                    reflectionContext: coachReflectionContext
                )
                var request = URLRequest(url: URL(string: "http://127.0.0.1:8787/v1/coach/turn")!)
                request.httpMethod = "POST"
                request.timeoutInterval = 40
                request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                request.setValue(LocalGatewaySession.token, forHTTPHeaderField: "X-Trainer-Session")
                request.httpBody = try JSONEncoder().encode(requestBody)
                aiCoachStatus = "AI 正在根据本课内容设计问题与反馈…"
                let (data, response) = try await URLSession.shared.data(for: request)
                guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
                    if let status = (response as? HTTPURLResponse)?.statusCode,
                       [400, 401, 403, 404, 429].contains(status) { shouldRetry = false }
                    let detail = (try? JSONDecoder().decode(GatewayError.self, from: data).error)
                    if detail?.contains("余额或可用额度不足") == true { shouldRetry = false }
                    if let detail, [400, 401, 403, 404, 429].contains(where: { detail.hasPrefix("HTTP \($0)") }) {
                        shouldRetry = false
                    }
                    throw GatewayFailure(message: detail ?? "AI 教练请求失败（HTTP \((response as? HTTPURLResponse)?.statusCode ?? 0)）。")
                }
                guard !Task.isCancelled, cacheKey == coachRefreshKey else { return }
                aiCoachTurn = try JSONDecoder().decode(AICoachTurn.self, from: data)
                aiCoachSelection = nil
                if let aiCoachTurn { aiCoachCache[cacheKey] = aiCoachTurn }
                return
            } catch {
                if Task.isCancelled || cacheKey != coachRefreshKey { return }
                lastFailure = error.localizedDescription
                if !shouldRetry { break }
                if attempt < 3 { try? await Task.sleep(for: .seconds(1)) }
            }
        }
        aiCoachTurn = nil
        aiCoachError = "AI 教练暂不可用：\(lastFailure)\n已切换为本地课程引导；可检查 AI 服务设置后重试。"
    }

    func advanceToNextConcept() {
        guard canAdvance else { evidenceError = hasCourseCodeTask ? "请先提交本课代码任务并通过评审。" : "请先完成本课回答。"; return }
        let source = concepts
        guard let index = source.firstIndex(where: { $0.id == selectedConceptID }), source.indices.contains(index + 1) else {
            showTeachingHub = true
            return
        }
        selectConcept(source[index + 1].id)
        selectedLayer = track == .foundations ? "人话" : "业务"
        prediction = nil
        aiCoachTurn = nil
        aiCoachSelection = nil
        reflection = ""
        evidenceError = nil
    }

    func openSolidityTrack() {
        track = .solidity
        selectedConceptID = "evm.state"
        selectedLayer = "业务"
        prediction = nil
        aiCoachTurn = nil
        aiCoachSelection = nil
        reflection = ""
        completedEvidence = false
    }

    func startTeaching(_ skill: SkillSummary) {
        planTask?.cancel()
        projectPlan = nil
        planningError = nil
        isPlanning = true
        recordedConcepts = []
        passedCourseLessons = []
        activeTeachingSkill = skill
        let declared = skill.languages.first ?? ""
        switch declared.lowercased() {
        case "python": foundationLanguage = .python
        case "solidity":
            foundationLanguage = .solidity
            track = .solidity
            selectedConceptID = "evm.state"
            selectedLayer = "业务"
        case "javascript", "typescript", "javascript / typescript":
            foundationLanguage = .javaScript
            track = .foundations
            selectedConceptID = "reading"
            selectedLayer = "人话"
        default:
            // A cross-language Skill keeps the last editor-derived language;
            // it never asks the learner to choose a syntax spelling first.
            track = skill.id.contains("solidity") ? .solidity : .foundations
        }
        prediction = nil
        aiCoachTurn = nil
        aiCoachSelection = nil
        reflection = ""
        completedEvidence = false
        planTask = Task { await loadProjectPlan(skill) }
    }

    func loadProjectPlan(_ skill: SkillSummary, mode: String = "open", retryJobID: String? = nil) async {
        isPlanning = true
        planningError = nil
        planningMode = mode
        planningJobID = retryJobID
        planningCompleted = 0
        planningTotal = 0
        planningStageStarted = Date()
        planningStatus = mode == "open" ? "正在读取本地课程…" : "正在准备本次任务…"
        defer { if activeTeachingSkill?.id == skill.id { isPlanning = false } }
        do {
            let endpoint = retryJobID.map { "http://127.0.0.1:8787/v1/jobs/\($0)/retry" } ?? "http://127.0.0.1:8787/v1/learning/plan/jobs"
            var request = URLRequest(url: URL(string: endpoint)!)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.setValue(LocalGatewaySession.token, forHTTPHeaderField: "X-Trainer-Session")
            request.httpBody = try JSONEncoder().encode(["skillId": skill.id, "mode": mode, "planId": projectPlan?.planId ?? ""])
            let (data, response) = try await URLSession.shared.data(for: request)
            guard [200, 202].contains((response as? HTTPURLResponse)?.statusCode ?? 0) else {
                struct Failure: Decodable { let error: String }
                throw GatewayFailure(message: (try? JSONDecoder().decode(Failure.self, from: data).error) ?? "课程服务不可用，请重试。")
            }
            var job = try JSONDecoder().decode(ProjectPlanJob.self, from: data)
            planningJobID = job.id
            for _ in 0..<86400 {
                try Task.checkCancellation()
                let status = job.message ?? (mode == "open" ? "读取已保存课程" : "任务已提交，等待处理…")
                if status != planningStatus { planningStageStarted = Date() }
                planningStatus = status
                planningLastResponse = Date()
                planningCompleted = job.completed ?? 0
                planningTotal = job.total ?? 0
                if let plan = job.result ?? job.partialResult {
                    guard activeTeachingSkill?.id == skill.id else { return }
                    let initial = projectPlan?.planId != plan.planId
                    projectPlan = plan
                    if initial {
                        let saved = try? await URLSession.shared.data(from: URL(string: "http://127.0.0.1:8787/v1/progress/\(plan.planId)")!)
                        let position = saved.flatMap { try? JSONDecoder().decode(LearningPosition.self, from: $0.0) }
                        guard activeTeachingSkill?.id == skill.id, projectPlan?.planId == plan.planId else { return }
                        recordedConcepts = Set(position?.recorded ?? UserDefaults.standard.stringArray(forKey: "evidence." + plan.planId) ?? [])
                        passedCourseLessons = Set(position?.passed ?? [])
                        let previous = position?.lessonId ?? UserDefaults.standard.string(forKey: "lesson." + plan.planId)
                        selectedConceptID = plan.lessons.first(where: { $0.id == previous })?.id ?? plan.lessons.first?.id ?? "reading"
                        completedEvidence = recordedConcepts.contains(selectedConceptID)
                        selectedLayer = projectLesson?.lesson.layers.first?.0 ?? "人话"
                    }
                    if job.status == "completed" { return }
                }
                if ["failed", "paused", "cancelled"].contains(job.status) { throw GatewayFailure(message: job.error ?? "生成已暂停或取消，可在任务中心继续。") }
                try await Task.sleep(for: .seconds(1))
                let (next, _) = try await URLSession.shared.data(from: URL(string: "http://127.0.0.1:8787/v1/jobs/\(job.id)")!)
                job = try JSONDecoder().decode(ProjectPlanJob.self, from: next)
            }
            throw GatewayFailure(message: "课程生成超时，请重试。")
        } catch is CancellationError { } catch {
            if activeTeachingSkill?.id == skill.id { planningError = error.localizedDescription }
        }
    }

    func selectConcept(_ id: String) {
        selectedConceptID = id
        selectedLayer = projectLesson?.lesson.layers.first?.0 ?? (track == .foundations ? "人话" : "业务")
        if let plan = projectPlan {
            UserDefaults.standard.set(id, forKey: "lesson." + plan.planId)
            Task {
                var request = URLRequest(url: URL(string: "http://127.0.0.1:8787/v1/progress/\(plan.planId)")!)
                request.httpMethod = "POST"
                request.setValue(LocalGatewaySession.token, forHTTPHeaderField: "X-Trainer-Session")
                request.httpBody = try? JSONEncoder().encode(["lessonId": id])
                _ = try? await URLSession.shared.data(for: request)
            }
        }
        reflection = ""
        prediction = nil
        aiCoachTurn = nil
        aiCoachSelection = nil
        evidenceError = nil
        completedEvidence = recordedConcepts.contains(id)
        answerFeedback = nil
        courseSubmissionStatus = nil
        courseSubmissionError = nil
        submissionDisclosure = nil
        courseAnswer = ""
    }

    func refreshEditorContext() async {
        do {
            let (data, response) = try await URLSession.shared.data(from: URL(string: "http://127.0.0.1:8787/v1/editor/context")!)
            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else { throw GatewayFailure(message: "无法读取编辑器上下文。") }
            let context = try JSONDecoder().decode(EditorContextEnvelope.self, from: data).context
            guard let context else {
                editorContextMessage = "还没有来自 VS Code 的选中代码。"
                return
            }
            editorContext = context
            editorContextMessage = "已连接：\(context.relativePath)"
            if activeTeachingSkill == nil {
                switch context.language.lowercased() {
                case "python": foundationLanguage = .python
                case "solidity": foundationLanguage = .solidity
                case "javascript", "typescript", "javascriptreact", "typescriptreact": foundationLanguage = .javaScript
                default: break
                }
            }
            if let jobID = context.teachingJobId, !observedAutomaticJobs.contains(jobID) {
                observedAutomaticJobs.insert(jobID)
                await receiveAutomaticCandidate(jobID: jobID)
            }
        } catch {
            editorContextMessage = "无法连接 VS Code Bridge。"
        }
    }

    func runPythonExperiment() async {
        isRunningPythonExperiment = true
        pythonExperimentError = nil
        defer { isRunningPythonExperiment = false }
        do {
            var request = URLRequest(url: URL(string: "http://127.0.0.1:8787/v1/labs/python/run")!)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONEncoder().encode(PythonLabRequest(code: pythonExperimentCode))
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse else { throw GatewayFailure(message: "实验服务没有响应。") }
            guard (200...299).contains(http.statusCode) else {
                let message = (try? JSONSerialization.jsonObject(with: data) as? [String: String])?["error"] ?? "实验无法运行。"
                throw GatewayFailure(message: message)
            }
            pythonExperimentResult = try JSONDecoder().decode(PythonLabResult.self, from: data)
        } catch let failure as GatewayFailure {
            pythonExperimentError = failure.message
        } catch {
            pythonExperimentError = "无法连接安全实验服务。请确认 Python Gateway 正在运行。"
        }
    }

    func submitLearnerQuestion() async {
        let question = learnerQuestion.trimmingCharacters(in: .whitespacesAndNewlines)
        guard question.count >= 20 else {
            automaticCandidateError = "请用至少一句完整的话描述你卡住的问题。"
            return
        }
        isDetectingTeachingNeed = true
        automaticCandidateError = nil
        defer { isDetectingTeachingNeed = false }
        do {
            let signal = TeachingSignalRequest(text: question, language: activeTeachingSkill?.languages.first ?? foundationLanguage.title, projectContext: editorContext?.relativePath ?? "")
            var request = URLRequest(url: URL(string: "http://127.0.0.1:8787/v1/teaching/signals")!)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONEncoder().encode(signal)
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else { throw GatewayFailure(message: "无法创建自动教学任务。") }
            let job = try JSONDecoder().decode(SkillGenerationJob.self, from: data)
            observedAutomaticJobs.insert(job.id)
            await receiveAutomaticCandidate(jobID: job.id)
        } catch {
            automaticCandidateError = "无法识别教学需要。请确认本机 Gateway 正在运行。"
        }
    }

    /// Importing a folder is an explicit learner action. The Python gateway
    /// receives only this selected path and creates a bounded project brief.
    func chooseProjectForTeaching() {
        let panel = NSOpenPanel()
        panel.title = "导入项目并生成教学 Skill"
        panel.message = "Trainer 会分析受限的项目结构和少量代表性源码；会自动排除依赖目录、构建产物与常见密钥文件。"
        panel.prompt = "导入项目"
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        guard panel.runModal() == .OK, let url = panel.url else { return }
        showProjectImportProgress = true
        Task { await importProjectForTeaching(url: url) }
    }

    func importProjectForTeaching(url: URL) async {
        isImportingProject = true
        importedProject = nil
        automaticCandidate = nil
        importedProjectMessage = "正在分析 \(url.lastPathComponent) 的项目结构与技术栈…"
        automaticCandidateError = nil
        defer { isImportingProject = false }
        do {
            var request = URLRequest(url: URL(string: "http://127.0.0.1:8787/v1/projects/import/jobs")!)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONEncoder().encode(ProjectImportRequest(path: url.path))
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
                let message = (try? JSONDecoder().decode(GatewayError.self, from: data).error) ?? "无法创建项目教学任务。"
                throw GatewayFailure(message: message)
            }
            let job = try JSONDecoder().decode(ProjectImportJob.self, from: data)
            importedProject = job.project
            observedAutomaticJobs.insert(job.id)
            importedProjectMessage = "已识别项目结构，AI 正在依据技术栈规划教学路径…"
            await receiveAutomaticCandidate(jobID: job.id, presentsCandidate: false)
            importedProjectMessage = "已生成候选教学 Skill，等待人工审批。"
        } catch {
            importedProjectMessage = nil
            automaticCandidateError = "无法分析导入项目：\(error.localizedDescription)"
        }
    }

    private func receiveAutomaticCandidate(jobID: String, presentsCandidate: Bool = true) async {
        do {
            while true {
                try await Task.sleep(for: .seconds(1))
                let (data, response) = try await URLSession.shared.data(from: URL(string: "http://127.0.0.1:8787/v1/jobs/\(jobID)")!)
                guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else { throw GatewayFailure(message: "无法读取自动教学任务。") }
                let job = try JSONDecoder().decode(SkillGenerationJob.self, from: data)
                if job.status == "completed", let result = job.result {
                    automaticCandidate = result
                    showAutomaticCandidate = presentsCandidate
                    return
                }
                if ["failed", "paused", "cancelled"].contains(job.status) { throw GatewayFailure(message: job.error ?? "任务已停止，可在任务中心继续。") }
            }
        } catch {
            automaticCandidateError = "自动候选未完成：\(error.localizedDescription)"
        }
    }

    func prepareCourseSubmission() async {
        guard !isSubmittingCourse else { return }
        let context = coachRefreshKey
        guard hasCourseCodeTask, currentCourseTask != nil else {
            courseSubmissionError = "当前课程没有可提交的代码任务。"
            courseSubmissionStatus = courseSubmissionError
            return
        }
        isSubmittingCourse = true
        courseSubmissionError = nil
        courseSubmissionStatus = "正在读取评判服务配置…"
        defer { isSubmittingCourse = false }
        do {
            var request = URLRequest(url: URL(string: "http://127.0.0.1:8787/v1/course-submissions/config")!)
            request.setValue(LocalGatewaySession.token, forHTTPHeaderField: "X-Trainer-Session")
            let (data, response) = try await URLSession.shared.data(for: request)
            guard context == coachRefreshKey else { return }
            guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
                throw GatewayFailure(message: (try? JSONDecoder().decode(GatewayError.self, from: data).error) ?? "自动提交服务尚未准备好。")
            }
            submissionDisclosure = try JSONDecoder().decode(SubmissionDisclosure.self, from: data)
            courseSubmissionStatus = "请确认本次材料与评判服务。"
        } catch {
            guard context == coachRefreshKey else { return }
            courseSubmissionError = error.localizedDescription
            courseSubmissionStatus = "无法准备提交：\(error.localizedDescription)"
        }
    }

    func loadCourseTask(prepare: Bool = false) async {
        guard hasCourseCodeTask, let plan = projectPlan, let lesson = projectLesson else { return }
        let key = courseTaskKey
        if currentCourseTask != nil { return }
        if prepare && isPreparingLessonTask { return }
        if prepare { isPreparingLessonTask = true }
        lessonTaskError = nil
        defer { if prepare { isPreparingLessonTask = false } }
        do {
            let encodedID = lesson.id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed.subtracting(CharacterSet(charactersIn: "/?#%"))) ?? lesson.id
            let path = prepare ? "/v1/lesson-task/prepare" : "/v1/course-task/\(plan.planId)/\(encodedID)"
            var request = URLRequest(url: URL(string: "http://127.0.0.1:8787" + path)!)
            request.timeoutInterval = 120
            request.setValue(LocalGatewaySession.token, forHTTPHeaderField: "X-Trainer-Session")
            if prepare {
                request.httpMethod = "POST"
                request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                request.httpBody = try JSONEncoder().encode(["planId": plan.planId, "lessonId": lesson.id])
            }
            let (data, response) = try await URLSession.shared.data(for: request)
            guard (response as? HTTPURLResponse)?.statusCode == 200 else {
                if !prepare { return }
                throw GatewayFailure(message: (try? JSONDecoder().decode(GatewayError.self, from: data).error) ?? "任务准备失败，请重试。")
            }
            if prepare {
                preparedLessonTasks[key] = try JSONDecoder().decode(PreparedLessonTask.self, from: data).task
            } else {
                let contract = try JSONDecoder().decode(CourseTaskEnvelope.self, from: data).contract
                preparedLessonTasks[key] = CoursePracticeTask(prompt: contract.prompt, requiredFiles: contract.requiredFiles, acceptance: contract.rubric.map(\.description))
            }
        } catch {
            if prepare && key == courseTaskKey { lessonTaskError = error.localizedDescription }
        }
    }

    func confirmCourseSubmission(_ disclosure: SubmissionDisclosure) async {
        guard let plan = projectPlan, let lesson = projectLesson else { return }
        let submittedAnswer = courseAnswer
        submissionDisclosure = nil
        isSubmittingCourse = true
        courseSubmissionError = nil
        courseSubmissionStatus = "正在自动检查工作区与相关文件…"
        defer { isSubmittingCourse = false }
        do {
            var workspaceRequest = URLRequest(url: URL(string: "http://127.0.0.1:8787/v2/pairings/workspaces")!)
            workspaceRequest.setValue(LocalGatewaySession.token, forHTTPHeaderField: "X-Trainer-Session")
            let (workspaceData, workspaceResponse) = try await URLSession.shared.data(for: workspaceRequest)
            guard projectPlan?.planId == plan.planId, selectedConceptID == lesson.id else { return }
            guard let workspaceHTTP = workspaceResponse as? HTTPURLResponse, workspaceHTTP.statusCode == 200 else {
                throw GatewayFailure(message: "无法读取课程关联工作区，请刷新连接。")
            }
            let workspaces = try JSONDecoder().decode(SubmissionWorkspaces.self, from: workspaceData)
            let matches = workspaces.active.filter { $0.valid == true && $0.plan_id == plan.planId }
            guard matches.count == 1, let binding = matches.first else {
                if matches.isEmpty, let other = workspaces.active.first(where: { $0.valid == true }) {
                    throw GatewayFailure(message: "当前工作区关联的是另一套课程（编号 \(other.plan_id.prefix(8))），本课编号为 \(plan.planId.prefix(8))。请在 VS Code 的 Trainer 侧栏选择“关联工作区与课程”，改绑到本课程。")
                }
                throw GatewayFailure(message: matches.isEmpty ? "当前课程尚未关联有效工作区。请在 VS Code 的 Trainer 侧栏关联整套课程。" : "当前课程关联了多个工作区，请先清理重复关联。")
            }
            var request = URLRequest(url: URL(string: "http://127.0.0.1:8787/v1/course-submissions")!)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.setValue(LocalGatewaySession.token, forHTTPHeaderField: "X-Trainer-Session")
            request.httpBody = try JSONEncoder().encode(CourseSubmissionRequest(
                planId: plan.planId, lessonId: lesson.id, bindingId: binding.id,
                requestKey: UUID().uuidString, evaluatorKey: disclosure.evaluatorKey,
                answer: submittedAnswer, consent: true))
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, http.statusCode == 202 else {
                throw GatewayFailure(message: (try? JSONDecoder().decode(GatewayError.self, from: data).error) ?? "提交未通过检查。")
            }
            let submission = try JSONDecoder().decode(CourseSubmissionResponse.self, from: data)
            UserDefaults.standard.set(submission.id, forKey: "courseSubmission.\(plan.planId).\(lesson.id)")
            guard projectPlan?.planId == plan.planId, selectedConceptID == lesson.id else { return }
            courseSubmissionStatus = "已提交，正在进行静态评审…"
            await pollCourseSubmission(submission.id, planID: plan.planId, lessonID: lesson.id)
        } catch {
            guard projectPlan?.planId == plan.planId, selectedConceptID == lesson.id else { return }
            courseSubmissionError = error.localizedDescription
            courseSubmissionStatus = "提交失败：\(error.localizedDescription)"
        }
    }

    func restoreCourseSubmission() async {
        guard let plan = projectPlan, let lesson = projectLesson,
              let id = UserDefaults.standard.string(forKey: "courseSubmission.\(plan.planId).\(lesson.id)") else { return }
        isSubmittingCourse = true
        defer { isSubmittingCourse = false }
        await pollCourseSubmission(id, planID: plan.planId, lessonID: lesson.id)
    }

    private func pollCourseSubmission(_ id: String, planID: String, lessonID: String) async {
        for _ in 0..<90 {
            do {
                guard !Task.isCancelled, projectPlan?.planId == planID, selectedConceptID == lessonID else { return }
                try await Task.sleep(for: .seconds(1))
                var request = URLRequest(url: URL(string: "http://127.0.0.1:8787/v1/course-submissions/\(id)")!)
                request.setValue(LocalGatewaySession.token, forHTTPHeaderField: "X-Trainer-Session")
                let (data, response) = try await URLSession.shared.data(for: request)
                guard let http = response as? HTTPURLResponse, http.statusCode == 200 else { continue }
                let submission = try JSONDecoder().decode(CourseSubmissionResponse.self, from: data)
                guard projectPlan?.planId == planID, selectedConceptID == lessonID else { return }
                if submission.status == "completed", let result = submission.assessment {
                    if result.outcome == "passed" { passedCourseLessons.insert(lessonID) }
                    courseSubmissionStatus = (result.outcome == "passed" ? "静态评审通过：" : "需要修改：") + result.feedback + " 下一步：" + result.nextStep
                    return
                }
                if ["failed", "cancelled"].contains(submission.status) {
                    throw GatewayFailure(message: "评判未完成，可稍后重新提交检查。")
                }
            } catch {
                guard !Task.isCancelled, projectPlan?.planId == planID, selectedConceptID == lessonID else { return }
                courseSubmissionError = error.localizedDescription
                courseSubmissionStatus = "评判失败：\(error.localizedDescription)"
                return
            }
        }
        courseSubmissionStatus = "评判仍在进行，可稍后返回查看。"
    }
}

struct TrainerWorkspace: View {
    @StateObject private var model = WorkspaceModel()
    @StateObject private var gateway = GatewayController()
    @AppStorage("trainer.sidebar.collapsed") private var sidebarCollapsed = false
    @AppStorage("trainer.glass.shade") private var glassShade = 0.28
    @Environment(\.accessibilityReduceMotion) private var systemReduceMotion
    @AppStorage("trainer.motion.enabled") private var motionEnabled = true
    private var reduceMotion: Bool { systemReduceMotion || !motionEnabled }
    @State private var userProfile = LearnerProfile(id: "local", name: "学习者", bio: "", avatar: "🧑‍💻")
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency

    var body: some View {
        ZStack {
            WindowVibrancy().ignoresSafeArea()
            Color(red: 0.035, green: 0.045, blue: 0.085).opacity(reduceTransparency ? 1 : glassShade).ignoresSafeArea()
            HSplitView {
                if sidebarCollapsed {
                    VStack(spacing: 22) {
                        Button { toggleSidebar() } label: { Image(systemName: "sidebar.left") }.help("展开侧边栏")
                        Button { model.showLearnerProfile = false } label: { Image(systemName: "book") }.help("课程")
                        Button { model.showCourseBuilder = true } label: { Image(systemName: "plus") }.help("创建课程")
                        Button { model.showProjectPractice = true } label: { Image(systemName: "hammer") }.help("项目实战")
                        Button { model.showSkills = true } label: { Image(systemName: "books.vertical") }.help("知识库")
                        Spacer()
                        Button { model.showLearnerProfile.toggle() } label: { ProfileAvatar(value: userProfile.avatar, size: 34) }.help(userProfile.name + " · 学习档案")
                    }.buttonStyle(.plain).font(.title3).padding(.vertical, 22).frame(width: 62)
                } else {
                VStack(spacing: 0) {
                    LearningSidebar(model: model, collapse: toggleSidebar)
                    Divider()
                    Button { model.showLearnerProfile.toggle() } label: {
                        HStack(spacing: 12) {
                            ProfileAvatar(value: userProfile.avatar)
                            VStack(alignment: .leading) {
                                Text(userProfile.name).font(.headline).lineLimit(1)
                                Text("能力 · 活动 · 成就").font(.caption).foregroundStyle(.secondary)
                            }
                            Spacer()
                            Image(systemName: "chevron.right")
                        }.padding(18).frame(maxWidth: .infinity)
                    }.buttonStyle(.plain)
                }
                    .frame(minWidth: 220, idealWidth: 250, maxWidth: 300)
                }
                if model.showLearnerProfile {
                    LearnerDashboard(onBack: { model.showLearnerProfile = false }, onRecord: {
                        model.showLearnerProfile = false
                    })
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                ScrollView {
                    if model.activeTeachingSkill != nil && model.projectPlan == nil {
                        VStack(alignment: .leading, spacing: 18) {
                            Text("项目专属教学").font(.title2)
                            Text(model.teachingTitle)
                            if model.isPlanning { ProgressView(model.planningStatus) }
                            if let error = model.planningError {
                                Text(error).foregroundStyle(.orange)
                                Button("生成/升级课程（调用 AI）") { if let skill = model.activeTeachingSkill { Task { await model.loadProjectPlan(skill, mode: "upgrade") } } }
                            }
                        }.padding(24).frame(maxWidth: .infinity, alignment: .leading)
                    } else { LessonCanvas(model: model) }
                }
                    .frame(minWidth: 500, idealWidth: 650)
                VStack(spacing: 0) {
                    if model.hasCourseCodeTask {
                        HStack(spacing: 12) {
                            Label("本课操作", systemImage: "slider.horizontal.3")
                                .font(.subheadline.weight(.semibold))
                            Spacer(minLength: 8)
                            Picker("", selection: $model.coachSection) {
                                Text("代码任务").tag("代码任务")
                                Text("AI 教练 · 答题").tag("答题")
                            }
                            .labelsHidden()
                            .pickerStyle(.segmented)
                            .frame(maxWidth: 300)
                            .accessibilityLabel("本课操作区域")
                        }
                        .padding(.horizontal, 16).padding(.vertical, 12)
                        .background(.regularMaterial)
                        Divider()
                    }
                    ScrollViewReader { coachScroll in
                        ScrollView {
                            if model.activeTeachingSkill != nil && model.projectPlan == nil {
                                VStack(alignment: .leading, spacing: 12) {
                                    Label("AI 教练", systemImage: "sparkles").font(.title3)
                                    Text("课程就绪后，教练会依据当前课生成提问与回讲提示。")
                                }.padding(20)
                            } else { CoachPanel(model: model).id("coach-top") }
                        }
                        .onChange(of: model.coachSection) { _, _ in
                            coachScroll.scrollTo("coach-top", anchor: .top)
                        }
                    }
                }.frame(minWidth: 285, idealWidth: 340, maxWidth: 420)
                }
            }
        }
        .tint(.indigo)
        .preferredColorScheme(.dark)
        .background(.clear)
        .background(WindowTransparencyConfigurator())
        .sheet(isPresented: $model.showSkills) { SkillsLibrary() }
        .sheet(isPresented: $model.showCourseBuilder) { SkillBuilder() }
        .sheet(isPresented: $model.showProjectPractice) { SkillBuilder(practice: true) }
        .sheet(isPresented: $model.showAIService) { AIServiceSettings() }
        .sheet(isPresented: $model.showTeachingHub) { TeachingHub(model: model) }
        .sheet(isPresented: $model.showAutomaticCandidate) {
            if let candidate = model.automaticCandidate { CandidateReview(result: candidate) }
        }
        .sheet(isPresented: $model.showProjectImportProgress) {
            ProjectImportProgress(model: model)
        }
        .task {
            await gateway.ensureRunning()
            if let (data, _) = try? await URLSession.shared.data(from: URL(string: "http://127.0.0.1:8787/v1/me")!),
               let value = try? JSONDecoder().decode(LearnerSummary.self, from: data) { userProfile = value.profile }
        }
        .onReceive(NotificationCenter.default.publisher(for: .trainerProfileChanged)) { notification in
            if let profile = notification.object as? LearnerProfile { userProfile = profile }
        }
        .animation(reduceMotion ? nil : .easeInOut(duration: 0.22), value: model.showLearnerProfile)
    }
    private func toggleSidebar() {
        withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.22)) { sidebarCollapsed.toggle() }
    }
}

struct WindowVibrancy: NSViewRepresentable {
    func makeNSView(context: Context) -> NSVisualEffectView {
        let view = NSVisualEffectView()
        view.material = .underWindowBackground
        view.blendingMode = .behindWindow
        view.state = .active
        return view
    }

    func updateNSView(_ nsView: NSVisualEffectView, context: Context) { }
}

struct WindowTransparencyConfigurator: NSViewRepresentable {
    func makeNSView(context: Context) -> NSView {
        let view = NSView()
        DispatchQueue.main.async {
            guard let window = view.window else { return }
            window.isOpaque = false
            window.backgroundColor = .clear
            window.titlebarAppearsTransparent = true
        }
        return view
    }

    func updateNSView(_ nsView: NSView, context: Context) { }
}

private struct GlassCard: ViewModifier {
    var prominence: Double = 0.18

    func body(content: Content) -> some View {
        content
            .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .stroke(.white.opacity(prominence), lineWidth: 1)
            }
    }
}

private extension View {
    func glassCard(prominence: Double = 0.18) -> some View {
        modifier(GlassCard(prominence: prominence))
    }
}

private extension View {
    func glassInput() -> some View {
        self
            .padding(10)
            .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .stroke(.white.opacity(0.20), lineWidth: 1)
            }
    }
}

struct ProjectImportProgress: View {
    @Environment(\.dismiss) private var dismiss
    @ObservedObject var model: WorkspaceModel

    private var isComplete: Bool {
        model.automaticCandidate != nil && !model.isImportingProject
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 22) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 6) {
                    Text(isComplete ? "项目教学 Skill 已就绪" : "正在构建项目教学路径")
                        .font(.title2.weight(.semibold))
                    Text("只处理你明确选择的项目；候选内容仍需人工审批后才能进入知识库。")
                        .font(.callout).foregroundStyle(.secondary)
                }
                Spacer()
                Button("完成") { dismiss() }
            }

            if let project = model.importedProject {
                HStack(spacing: 12) {
                    Image(systemName: "folder.badge.gearshape")
                        .font(.title2).foregroundStyle(.blue)
                    VStack(alignment: .leading, spacing: 3) {
                        Text(project.name).font(.headline)
                        Text("已建立 \(project.fileCount) 个安全可读文件的结构摘要")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                }
                .padding(16)
                .glassCard()
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 7) {
                        ForEach(project.stack, id: \.self) { technology in
                            Text(technology).font(.caption.weight(.medium))
                                .padding(.horizontal, 10).padding(.vertical, 6)
                                .background(.blue.opacity(0.14), in: Capsule())
                        }
                    }
                }
            }

            VStack(alignment: .leading, spacing: 0) {
                ImportProgressRow(number: "1", title: "建立安全项目摘要", detail: "排除依赖目录、构建产物与常见密钥文件", complete: model.importedProject != nil)
                ImportProgressRow(number: "2", title: "识别完整技术栈与代码结构", detail: "保留语言、框架、运行时与数据层的关系", complete: model.importedProject != nil)
                ImportProgressRow(number: "3", title: "AI 设计从基础到项目的教学路径", detail: "语法、函数、运行时与当前项目职责会被分层讲解", complete: isComplete)
                ImportProgressRow(number: "4", title: "结构验证与人工审批", detail: "候选 Skill 不会自动写入可信知识库", complete: isComplete, isLast: true)
            }
            .glassCard()

            if model.isImportingProject {
                HStack(spacing: 10) {
                    ProgressView().controlSize(.small)
                    Text(model.importedProjectMessage ?? "准备导入…")
                        .font(.callout).foregroundStyle(.secondary)
                }
            } else if isComplete {
                Button {
                    dismiss()
                    DispatchQueue.main.async { model.showAutomaticCandidate = true }
                } label: {
                    Label("查看候选 Skill 并审批", systemImage: "checkmark.shield")
                }
                .buttonStyle(.borderedProminent)
            } else if let error = model.automaticCandidateError {
                Label(error, systemImage: "exclamationmark.triangle")
                    .font(.callout).foregroundStyle(.orange)
            }
            Spacer(minLength: 0)
        }
        .padding(28)
        .frame(width: 640, height: 590, alignment: .topLeading)
    }
}

struct ImportProgressRow: View {
    let number: String
    let title: String
    let detail: String
    let complete: Bool
    var isLast = false

    var body: some View {
        HStack(alignment: .top, spacing: 14) {
            ZStack {
                Circle().fill(complete ? Color.green.opacity(0.22) : Color.white.opacity(0.10))
                Image(systemName: complete ? "checkmark" : number)
                    .font(.caption.weight(.bold)).foregroundStyle(complete ? .green : .secondary)
            }
            .frame(width: 28, height: 28)
            VStack(alignment: .leading, spacing: 3) {
                Text(title).font(.subheadline.weight(.semibold))
                Text(detail).font(.caption).foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
        }
        .padding(16)
        .overlay(alignment: .bottom) {
            if !isLast { Divider().padding(.leading, 58) }
        }
    }
}

struct ProjectTeachingEntry: View {
    @ObservedObject var model: WorkspaceModel
    let selectionLabel: String

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 9) {
                Image(systemName: "graduationcap.circle.fill")
                    .font(.title3).foregroundStyle(.blue)
                VStack(alignment: .leading, spacing: 2) {
                    Text("项目教学").font(.subheadline.weight(.semibold))
                    Text(model.teachingTitle).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                }
            }
            Text("从项目生成课程，在实践中补齐基础。")
                .font(.caption).foregroundStyle(.secondary)
            Button { model.chooseProjectForTeaching() } label: {
                HStack(spacing: 8) {
                    Image(systemName: model.isImportingProject ? "arrow.triangle.2.circlepath" : "folder.badge.plus")
                    Text(model.isImportingProject ? "正在构建课程…" : "导入项目")
                    Spacer()
                    Image(systemName: "arrow.right")
                }
                .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .disabled(model.isImportingProject)
            HStack(spacing: 10) {
                Button { model.showTeachingHub = true } label: {
                    Label(selectionLabel, systemImage: "rectangle.stack.badge.play")
                }
                .buttonStyle(.borderless)
                .font(.caption)
                Spacer()
                Label("需授权", systemImage: "lock")
                    .font(.caption2).foregroundStyle(.secondary)
            }
        }
        .padding(14)
        .background(Color.white.opacity(0.035), in: RoundedRectangle(cornerRadius: 12))
    }
}

struct LearningSidebar: View {
    @ObservedObject var model: WorkspaceModel
    var collapse: () -> Void
    @State private var showConnection = false

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text("Trainer").font(.system(size: 24, weight: .bold))
                    Spacer()
                    Button(action: collapse) { Image(systemName: "sidebar.left") }.buttonStyle(.plain).help("收起侧边栏")
                }
                Text("你的 AI 技术导师").foregroundStyle(.secondary)
            }
            Divider()
            VStack(alignment: .leading, spacing: 12) {
                Text("开始学习").font(.caption.weight(.medium)).foregroundStyle(.secondary)
                ProjectTeachingEntry(model: model, selectionLabel: activeSelectionLabel)
                HStack(spacing: 10) {
                Button { model.showCourseBuilder = true } label: {
                    Label("创建课程", systemImage: "plus").frame(maxWidth: .infinity)
                }
                Button { model.showProjectPractice = true } label: {
                    Label("项目实战", systemImage: "hammer").frame(maxWidth: .infinity)
                }
                }.buttonStyle(.bordered).controlSize(.regular)
            }
            HStack(spacing: 6) {
                Button { showConnection = true } label: { ConnectionStatus(compact: true) }.buttonStyle(.plain)
                Spacer(minLength: 0)
                Menu {
                    Button("管理连接") { showConnection = true }
                    Button("读取已同步选区（旧入口）") { Task { await model.refreshEditorContext() } }
                } label: { Image(systemName: "ellipsis").frame(width: 24, height: 24) }.menuStyle(.borderlessButton).fixedSize()
            }
            .sheet(isPresented: $showConnection) { VSCodePairing() }
            Divider()
            Text("学习路线").font(.caption.weight(.medium)).foregroundStyle(.secondary)
            ScrollView {
            LazyVStack(alignment: .leading, spacing: 8) {
                ForEach(model.concepts) { concept in
                    Button { model.showLearnerProfile = false; model.selectConcept(concept.id) } label: {
                        HStack(spacing: 9) {
                            Image(systemName: concept.status == .mastered ? "checkmark.circle.fill" : (concept.status == .current ? "circle.inset.filled" : "circle"))
                                .foregroundStyle(color(for: concept.status)).frame(width: 16)
                                .accessibilityLabel(concept.status == .mastered ? "练习已完成，凭据已保存" : concept.status.rawValue)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(concept.title)
                                Text("\(concept.level) · \(concept.status.rawValue)")
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                            Spacer()
                        }
                        .padding(9)
                        .frame(maxWidth: .infinity, minHeight: 48, alignment: .leading)
                        .background(model.selectedConceptID == concept.id ? Color.indigo.opacity(0.18) : Color.clear, in: RoundedRectangle(cornerRadius: 8))
                        .overlay(alignment: .trailing) {
                            if model.selectedConceptID == concept.id { Capsule().fill(.indigo).frame(width: 3) }
                        }
                    }
                    .buttonStyle(.plain)
                }
            }
            }.frame(maxHeight: .infinity)
            Button { model.showSkills = true } label: {
                Label("浏览 Skill 知识库", systemImage: "books.vertical")
            }
            .buttonStyle(.bordered)
        }
        .padding(18)
        .background(.thinMaterial)
    }

    private func color(for status: Concept.Status) -> Color {
        switch status { case .mastered: .green; case .current: .blue; case .next: .gray }
    }

    private var activeSelectionLabel: String {
        model.activeTeachingSkill == nil ? "打开教学入口" : "切换教学方向"
    }
}

struct LessonCanvas: View {
    @ObservedObject var model: WorkspaceModel
    @State private var activePracticePage: PracticePage = .trace
    @State private var richLesson = true
    @State private var showAssessment = false

    private enum PracticePage: Int, CaseIterable, Identifiable {
        case trace
        case experiment
        case next

        var id: Int { rawValue }
    }

    private var practicePages: [PracticePage] {
        model.projectLesson == nil && model.track == .foundations && model.foundationLanguage == .python
            ? [.trace, .experiment, .next]
            : [.trace, .next]
    }

    var body: some View {
        let lesson = model.lesson
        VStack(alignment: .leading, spacing: 16) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 5) {
                    Text("当前任务").font(.caption).foregroundStyle(.secondary)
                    Text(lesson.title).font(.title2.weight(.semibold))
                    Text(lesson.objective).foregroundStyle(.secondary)
                }
                Spacer()
                Label(model.projectLesson?.language ?? model.foundationLanguage.title, systemImage: "text.book.closed")
                    .font(.caption).padding(8).background(.blue.opacity(0.20), in: Capsule())
            }
            if let context = model.editorContext {
                EditorContextCard(context: context)
            }
            if let plan = model.projectPlan, let item = model.projectLesson {
                Button("本课能力评估") { showAssessment = true }
                    .sheet(isPresented: $showAssessment) {
                        LessonAssessment(planID: plan.planId, lessonID: item.id, answer: model.reflection, evidenceType: model.currentEvidenceType)
                    }
            }
            if let plan = model.projectPlan {
                VStack(alignment: .leading, spacing: 8) {
                    CourseMaintenancePanel(model: model, plan: plan)
                    DisclosureGroup("课程目录与检查报告") {
                    if plan.coverageStatus == "outline-generated" {
                        DisclosureGroup("完整目录 · 各模块已生成，内容质量仍需验证") {
                            ForEach(plan.moduleTitles ?? [], id: \.self) { Text("• " + $0).frame(maxWidth: .infinity, alignment: .leading) }
                        }
                    } else if plan.coverageStatus != "generating" {
                        Text("这是已保存的旧版课程。升级请使用高级菜单，重新打开不会生成新课。")
                    }
                    if let audit = plan.coverageAudit {
                        DisclosureGroup("目录结构核验：\(audit.coveredModules) / \(audit.totalModules) 模块覆盖") {
                            ForEach(Array(audit.modules.enumerated()), id: \.offset) { _, module in
                                Label("\(module.title) · \(module.lessonCount) 课", systemImage: module.covered ? "checkmark.circle" : "clock")
                                    .foregroundStyle(module.covered ? .green : .secondary)
                            }
                            ForEach(audit.limitations, id: \.self) { Text($0).font(.caption) }
                        }
                    }
                    if let reviews = plan.contentReviews, !reviews.isEmpty {
                        DisclosureGroup("内容核验报告 · \(reviews.count) 个模块") {
                            ForEach(Array(reviews.enumerated()), id: \.offset) { _, review in
                                DisclosureGroup(review.module) {
                                    Text(review.method).font(.caption).foregroundStyle(.secondary)
                                    ForEach(Array(review.findings.enumerated()), id: \.offset) { _, finding in
                                        VStack(alignment: .leading, spacing: 5) {
                                            Label(finding.requirement, systemImage: finding.status == "covered" ? "checkmark.circle" : "exclamationmark.circle")
                                            if !finding.quote.isEmpty { Text("依据：\(finding.quote)").font(.caption).textSelection(.enabled) }
                                            if !finding.recommendation.isEmpty { Text(finding.recommendation).font(.caption).foregroundStyle(.secondary) }
                                        }.padding(.vertical, 5)
                                    }
                                }
                            }
                        }
                    }
                    if let quality = plan.qualityAudit {
                        DisclosureGroup("语言与练习一致性：\(quality.passed) / \(quality.total) 项") {
                            ForEach(Array(quality.findings.enumerated()), id: \.offset) { _, finding in
                                Label("\(finding.lessonId) · \(finding.detail)",
                                      systemImage: finding.status == "passed" ? "checkmark.circle" : "exclamationmark.triangle")
                                    .foregroundStyle(finding.status == "passed" ? .green : .orange)
                            }
                            ForEach(quality.limitations, id: \.self) { Text($0).font(.caption) }
                        }
                    }
                    if let modules = plan.moduleCount { Text("计划材料模块：\(modules)；源码文件：\(plan.sourceFileCount ?? 0)。模块数量不是知识点覆盖率。") }
                    if plan.sourceFileCount == 0 { Text("这份课程依据 Skill 教学资料生成，未包含可核对的项目源码快照。") }
                    }
                }
                .font(.callout).foregroundStyle(.secondary)
                .padding(14).frame(maxWidth: .infinity, alignment: .leading).glassCard()
            }
            if model.projectLesson == nil && model.track == .foundations && model.selectedConceptID == "reading" {
                BeginnerCodeCard(language: model.foundationLanguage)
            } else {
                TeachingCodeBlock(code: lesson.code, language: model.projectLesson?.language ?? model.foundationLanguage.title)
            }

            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Label(model.projectLesson?.sectionTitle ?? "课程讲解", systemImage: "text.book.closed").font(.headline)
                    Spacer()
                    Menu {
                        Picker("阅读格式", selection: $richLesson) {
                            Text("排版阅读").tag(true)
                            Text("原始文本").tag(false)
                        }
                    } label: {
                        Label(richLesson ? "排版阅读" : "原始文本", systemImage: "textformat")
                            .font(.caption)
                    }.fixedSize()
                }
                Picker("讲解深度", selection: Binding(
                    get: { model.activeLayer },
                    set: { model.selectedLayer = $0 }
                )) {
                    ForEach(lesson.layers.map(\.0), id: \.self) { Text($0) }
                }.labelsHidden().pickerStyle(.segmented)
            }.padding(.top, 8)
            Group {
                if richLesson { RichMarkdownPreview(text: model.selectedLayerText) }
                else { Text(model.selectedLayerText).textSelection(.enabled) }
            }
                .fixedSize(horizontal: false, vertical: true)
                .layoutPriority(1)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(14)
                .glassCard()

            PracticeCarousel(selection: $activePracticePage, pages: practicePages) { page in
                switch page {
                case .trace:
                    Group {
                        if let item = model.projectLesson {
                            VStack(alignment: .leading, spacing: 16) {
                                Text("观察与练习").font(.headline)
                                RichMarkdownPreview(text: item.exercise).fixedSize(horizontal: false, vertical: true)
                                if model.hasCourseCodeTask {
                                    Button { model.coachSection = "代码任务" } label: {
                                        Label("打开代码任务 · 查看要求并提交", systemImage: "arrow.right.circle")
                                    }.buttonStyle(.bordered).font(.callout)
                                }
                                Divider()
                                Text("用自己的话解释").font(.headline)
                                RichMarkdownPreview(text: item.reflection).fixedSize(horizontal: false, vertical: true)
                                Text("来源：\(item.source)").font(.caption).foregroundStyle(.secondary)
                            }.padding(20).frame(maxWidth: .infinity, alignment: .leading).glassCard()
                        } else if model.track == .foundations {
                            BeginnerTrace(language: model.foundationLanguage)
                        } else {
                            RuntimeTrace()
                        }
                    }
                case .experiment:
                    PythonExperimentCard(model: model)
                case .next:
                    LessonPracticeStage(model: model)
                }
            }
            .onChange(of: practicePages) { _, pages in
                if !pages.contains(activePracticePage) {
                    activePracticePage = pages.first ?? .trace
                }
            }
            .frame(maxWidth: .infinity, minHeight: 360)
        }
        .padding(24)
    }
}

struct PracticeCarousel<Page: Identifiable & Hashable, Content: View>: View {
    @Binding var selection: Page
    let pages: [Page]
    @ViewBuilder let content: (Page) -> Content
    @State private var dragOffset: CGFloat = 0

    private var selectedIndex: Int {
        pages.firstIndex(of: selection) ?? 0
    }

    var body: some View {
        VStack(spacing: 12) {
            GeometryReader { proxy in
                HStack(spacing: 0) {
                    ForEach(pages) { page in
                        ScrollView { content(page).fixedSize(horizontal: false, vertical: true) }
                            .frame(width: proxy.size.width, height: proxy.size.height, alignment: .top)
                    }
                }
                .offset(x: -CGFloat(selectedIndex) * proxy.size.width + dragOffset)
                .animation(.spring(response: 0.32, dampingFraction: 0.86), value: selection)
                .gesture(
                    DragGesture(minimumDistance: 12)
                        .onChanged { value in
                            dragOffset = value.translation.width * 0.72
                        }
                        .onEnded { value in
                            let threshold = proxy.size.width * 0.16
                            let predicted = value.predictedEndTranslation.width
                            let shouldAdvance = value.translation.width < -threshold || predicted < -threshold
                            let shouldReturn = value.translation.width > threshold || predicted > threshold
                            let nextIndex: Int
                            if shouldAdvance {
                                nextIndex = min(selectedIndex + 1, pages.count - 1)
                            } else if shouldReturn {
                                nextIndex = max(selectedIndex - 1, 0)
                            } else {
                                nextIndex = selectedIndex
                            }
                            if pages.indices.contains(nextIndex) {
                                selection = pages[nextIndex]
                            }
                            withAnimation(.spring(response: 0.32, dampingFraction: 0.86)) {
                                dragOffset = 0
                            }
                        }
                )
            }
            .clipped()

            HStack(spacing: 8) {
                ForEach(pages) { page in
                    Circle()
                        .fill(page == selection ? Color.accentColor : .secondary.opacity(0.32))
                        .frame(width: page == selection ? 9 : 7, height: page == selection ? 9 : 7)
                        .animation(.easeInOut(duration: 0.18), value: selection)
                        .accessibilityLabel(page == selection ? "当前页" : "切换到此页")
                        .onTapGesture { selection = page }
                }
            }
            .padding(.bottom, 2)
            .accessibilityElement(children: .contain)
        }
    }
}

struct LessonPracticeStage: View {
    @ObservedObject var model: WorkspaceModel
    @State private var showSummary = false
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Label("把理解带到下一步", systemImage: "arrow.up.right.circle")
                    .font(.headline)
                Spacer()
                Text("迁移练习")
                    .font(.caption.weight(.medium))
                    .foregroundStyle(.secondary)
            }
            Text(model.track == .foundations ? "完成回讲后，Trainer 会把你的理解证据映射到下一项能力，并继续用当前 Skill 的技术语境举例。" : "完成回讲后，Trainer 会把这笔交易的运行时理解带到权限控制与安全设计。")
                .font(.callout).foregroundStyle(.secondary)
            Divider()
            Text("学习路径")
                .font(.caption.weight(.semibold)).foregroundStyle(.secondary)
            HStack(spacing: 10) {
                StageMetric(title: "当前", value: model.currentConceptTitle)
                StageMetric(title: "下一项", value: model.nextConceptTitle ?? (model.isPlanning ? "后续课程生成中" : "本批课程末尾"))
                StageMetric(title: "语境", value: model.projectLesson?.language ?? model.foundationLanguage.title)
            }
            Spacer(minLength: 12)
            VStack(alignment: .leading, spacing: 6) {
                Label("完成这一页后", systemImage: "checkmark.circle")
                    .font(.subheadline.weight(.semibold))
                Text(model.canAdvance ? "本课要求已完成，可以进入下一课。" : (model.hasCourseCodeTask ? "请在右侧提交本课代码任务，通过评审后进入下一课。" : "请在右侧完成本课回答。"))
                    .font(.callout).foregroundStyle(.secondary)
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(.blue.opacity(0.12), in: RoundedRectangle(cornerRadius: 12))
            Button(model.nextConceptTitle.map { "进入「\($0)」" } ?? (model.isPlanning ? "等待后续模块…" : "结束本批学习")) {
                if model.nextConceptTitle == nil { showSummary = true }
                else { model.advanceToNextConcept() }
            }
            .buttonStyle(.borderedProminent)
            .disabled((model.nextConceptTitle != nil && !model.canAdvance) || (model.nextConceptTitle == nil && model.isPlanning))
        }
        .padding(22)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .glassCard()
        .sheet(isPresented: $showSummary) {
            VStack(alignment: .leading, spacing: 18) {
                Text("本次学习总结").font(.title2.bold())
                Text("已记录凭据：\(model.concepts.filter { model.recordedConcepts.contains($0.id) }.count) / \(model.concepts.count) 课")
                Text("到达末课不等于已完成全部练习。学习记录已保留；可以回到未完成的课程继续学习。项目整体掌握仍需实践验收。")
                HStack {
                    Button("返回课程") { showSummary = false }
                    Button("选择其他课程") { showSummary = false; model.showTeachingHub = true }
                }
            }.padding(28).frame(width: 460)
        }
    }
}

struct StageMetric: View {
    let title: String
    let value: String
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.caption).foregroundStyle(.secondary)
            Text(value).font(.callout.weight(.semibold)).lineLimit(2)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .background(.white.opacity(0.08), in: RoundedRectangle(cornerRadius: 9))
    }
}

struct PythonExperimentCard: View {
    @ObservedObject var model: WorkspaceModel

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("安全实验：亲手观察", systemImage: "play.circle")
                .font(.headline)
            Text("这里只运行教学用的极小 Python 子集：值、标签、列表、基础运算与 print；不会执行导入、文件、网络或项目代码。")
                .font(.caption).foregroundStyle(.secondary)
            TextEditor(text: $model.pythonExperimentCode)
                .font(.system(.body, design: .monospaced))
                .frame(minHeight: 72, maxHeight: 100)
                .padding(5)
                .overlay(RoundedRectangle(cornerRadius: 8).stroke(.quaternary))
            Button(model.isRunningPythonExperiment ? "正在观察…" : "运行并查看每一步") {
                Task { await model.runPythonExperiment() }
            }
            .disabled(model.isRunningPythonExperiment)
            .buttonStyle(.borderedProminent)
            if let result = model.pythonExperimentResult {
                VStack(alignment: .leading, spacing: 5) {
                    Text("输出：\(result.output.isEmpty ? "（没有 print 输出）" : result.output.joined(separator: " · "))")
                    ForEach(result.trace) { step in
                        Text(step.action == "assign" ? "把 \(step.value ?? "") 记到标签 \(step.label ?? "")" : "打印 \(step.value ?? "")")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                .padding(10)
                .background(.green.opacity(0.12), in: RoundedRectangle(cornerRadius: 8))
            }
            if let error = model.pythonExperimentError {
                Text(error).font(.caption).foregroundStyle(.orange)
            }
            Spacer(minLength: 12)
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: "eye")
                    .foregroundStyle(.blue)
                VStack(alignment: .leading, spacing: 3) {
                    Text("观察什么？").font(.subheadline.weight(.semibold))
                    Text("运行后先看输出，再看每一步如何把内容放进标签。这里不会接触项目文件或网络。")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            .padding(13)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(.blue.opacity(0.12), in: RoundedRectangle(cornerRadius: 10))
        }
        .padding(20)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .glassCard()
    }
}

struct EditorContextCard: View {
    let context: EditorContext
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("来自 VS Code 的当前选择", systemImage: "link")
                .font(.headline)
            Text("\(context.relativePath) · \(context.language)")
                .font(.caption).foregroundStyle(.secondary)
            Text(context.selection)
                .font(.system(.caption, design: .monospaced))
                .textSelection(.enabled)
                .lineLimit(6)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(13)
        .glassCard()
    }
}

struct BeginnerCodeCard: View {
    let language: FoundationLanguage
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Label("先用一句人话说清目标", systemImage: "text.bubble")
                .font(.headline)
            Text("“请帮我记住：这位同学叫小明。”")
                .font(.title3.weight(.medium))
            Divider()
            Text(language.source)
                .font(.system(.title3, design: .monospaced).weight(.medium))
                .padding(.vertical, 4)
            HStack(spacing: 10) {
                if language == .javaScript {
                    BeginnerToken(title: "let", detail: "新建一个标签")
                } else if language == .solidity {
                    BeginnerToken(title: "string memory", detail: "先标记：文字与位置")
                }
                BeginnerToken(title: "name", detail: "标签的名字")
                BeginnerToken(title: "\"小明\"", detail: "要记住的内容")
            }
            Text(language.languageNote + " 现在不用背它；先认识代码如何把人话里的信息拆开。")
                .font(.callout).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(18)
        .glassCard(prominence: 0.24)
    }
}

struct BeginnerToken: View {
    let title: String
    let detail: String
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.system(.body, design: .monospaced).weight(.semibold))
            Text(detail).font(.caption).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10).background(.blue.opacity(0.13), in: RoundedRectangle(cornerRadius: 8))
    }
}

struct BeginnerTrace: View {
    let language: FoundationLanguage
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Label("它在做的事", systemImage: "arrow.triangle.turn.up.right.diamond")
                    .font(.headline)
                Spacer()
                Text("运行追踪")
                    .font(.caption.weight(.medium)).foregroundStyle(.secondary)
            }
            Text("先不必记语法。只要跟着这一条信息，观察它怎样从人话变成程序能记住的东西。")
                .font(.callout).foregroundStyle(.secondary)
            Divider()
            Text("信息怎样流动")
                .font(.caption.weight(.semibold)).foregroundStyle(.secondary)
            HStack(spacing: 12) {
                TraceStep(label: "人话", detail: "记住小明")
                Image(systemName: "arrow.right").foregroundStyle(.secondary)
                TraceStep(label: "\(language.title) 标签", detail: "name")
                Image(systemName: "arrow.right").foregroundStyle(.secondary)
                TraceStep(label: "内容", detail: "小明")
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            VStack(alignment: .leading, spacing: 5) {
                Label("此刻只需看懂", systemImage: "eye")
                    .font(.subheadline.weight(.semibold))
                Text("name 是给这份信息起的名字；“小明”才是程序要保存的具体内容。")
                    .font(.callout).foregroundStyle(.secondary)
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(.blue.opacity(0.12), in: RoundedRectangle(cornerRadius: 12))
        }
        .padding(22)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .glassCard()
    }
}

struct RuntimeTrace: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Label("运行时追踪", systemImage: "point.3.connected.trianglepath.dotted")
                    .font(.headline)
                Spacer()
                Text("一笔交易的顺序").font(.caption.weight(.medium)).foregroundStyle(.secondary)
            }
            Text("从调用到状态写入，按顺序观察每一步。先知道发生什么，再学习安全规则。")
                .font(.callout).foregroundStyle(.secondary)
            Divider()
            Text("交易执行路径").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
            HStack(spacing: 12) {
                TraceStep(label: "交易调用", detail: "msg.sender")
                Image(systemName: "arrow.right").foregroundStyle(.secondary)
                TraceStep(label: "余额检查", detail: "require")
                Image(systemName: "arrow.right").foregroundStyle(.secondary)
                TraceStep(label: "原子更新", detail: "storage")
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            VStack(alignment: .leading, spacing: 5) {
                Label("观察重点", systemImage: "eye")
                    .font(.subheadline.weight(.semibold))
                Text("任何一步失败，整笔调用都会回到开始前；这就是“原子性”在这里的意义。")
                    .font(.callout).foregroundStyle(.secondary)
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(.blue.opacity(0.12), in: RoundedRectangle(cornerRadius: 12))
        }
        .padding(22)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .glassCard()
    }
}

struct TraceStep: View {
    let label: String
    let detail: String
    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).font(.caption.weight(.medium))
            Text(detail).font(.caption2).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .background(.white.opacity(0.10), in: RoundedRectangle(cornerRadius: 10))
    }
}

struct CoachPanel: View {
    @ObservedObject var model: WorkspaceModel

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
                if model.hasCourseCodeTask && model.coachSection == "代码任务" {
                    if let task = model.currentCourseTask {
                        CoursePracticeTaskView(task: task, model: model)
                    } else {
                        VStack(alignment: .leading, spacing: 10) {
                            Label(model.codeTaskTitle, systemImage: "hammer").font(.headline)
                            Text(model.projectPlan?.submissionPolicy?.primaryRole == "coach-exercise"
                                 ? "AI 会把本课观察与练习整理为独立的项目代码任务；原项目源码只作为上下文，不会直接算作完成成果。"
                                 : "这门已有课程尚未整理提交文件和验收标准。根据本课练习准备一次，之后可以直接提交工作区成果。")
                                .font(.callout).foregroundStyle(.secondary)
                            Button(model.isPreparingLessonTask ? "正在准备任务…" : "准备\(model.codeTaskTitle)") {
                                Task { await model.loadCourseTask(prepare: true) }
                            }.disabled(model.isPreparingLessonTask).buttonStyle(.borderedProminent)
                            Text("使用已配置的 AI 整理本课要求，会产生一次生成用量。")
                                .font(.caption).foregroundStyle(.secondary)
                            if let error = model.lessonTaskError { Text(error).font(.caption).foregroundStyle(.orange) }
                        }.padding(16).glassCard()
                    }
                }
                if !model.hasCourseCodeTask || model.coachSection == "答题" {
                Label("AI 教练", systemImage: "sparkles")
                    .font(.title3.weight(.semibold))
                Text(model.projectLesson != nil
                     ? "跟随中栏「观察与练习」完成一个具体判断，再用自己的话说明依据。"
                     : (model.track == .foundations ? "围绕「\(model.currentConceptTitle)」做一个小判断，再一起观察代码。" : "先预测，再观察。这能让我判断你是否真正理解了交易回滚。"))
                    .foregroundStyle(.secondary)
                if model.track == .foundations {
                    Text("当前课程语言：\(model.projectLesson?.language ?? model.foundationLanguage.title)。")
                        .font(.caption).foregroundStyle(.secondary)
                }

                HStack(spacing: 8) {
                    Image(systemName: "arrow.triangle.2.circlepath")
                    VStack(alignment: .leading, spacing: 2) {
                        Text("已同步 · \(model.coachFocusTitle)")
                            .font(.caption.weight(.semibold))
                        Text(model.projectLesson == nil
                             ? "问题随当前讲解层级更新。"
                             : "问题和回讲会直接取自中栏本课练习；示例代码只作为参考。")
                            .font(.caption2).foregroundStyle(.secondary)
                    }
                }
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(.blue.opacity(0.10), in: RoundedRectangle(cornerRadius: 9))

                if let turn = model.aiCoachTurn {
                    Label("由当前 Skill 约束生成", systemImage: "sparkles")
                        .font(.caption).foregroundStyle(.secondary)
                    Text(turn.question).font(.headline)
                    ForEach(Array(turn.options.enumerated()), id: \.offset) { index, option in
                        Button { model.aiCoachSelection = index } label: {
                            HStack {
                                Image(systemName: model.aiCoachSelection == index ? "largecircle.fill.circle" : "circle")
                                Text(option).multilineTextAlignment(.leading)
                                Spacer()
                            }
                        }
                        .buttonStyle(.plain).padding(10)
                        .background(model.aiCoachSelection == index ? Color.blue.opacity(0.30) : Color.white.opacity(0.10), in: RoundedRectangle(cornerRadius: 9))
                    }
                    if model.aiCoachSelection != nil {
                        Text((model.aiCoachSelection == turn.correctIndex ? "判断正确。" : "再看一下代码。") + turn.feedback).font(.callout).padding(11).background((model.aiCoachSelection == turn.correctIndex ? Color.green : Color.orange).opacity(0.18), in: RoundedRectangle(cornerRadius: 9))
                    }
                } else if model.coachPending {
                    CoachLoadingCard(status: model.aiCoachStatus)
                } else if let item = model.projectLesson {
                    Text("本课回讲").font(.headline)
                    RichMarkdownPreview(text: item.reflection).fixedSize(horizontal: false, vertical: true)
                    HStack {
                        Button("重试 AI 教练") { Task { await model.refreshAICoach() } }
                        Button("检查 AI 服务") { model.showAIService = true }
                    }
                } else {
                    Text(model.coachQuestion).font(.headline)
                    ForEach(options) { option in
                        Button { model.prediction = option } label: {
                            HStack { Image(systemName: model.prediction == option ? "largecircle.fill.circle" : "circle"); Text(option.rawValue).multilineTextAlignment(.leading); Spacer() }
                        }
                        .buttonStyle(.plain).padding(10)
                        .background(model.prediction == option ? Color.blue.opacity(0.30) : Color.white.opacity(0.10), in: RoundedRectangle(cornerRadius: 9))
                    }
                    if let feedback = model.predictionFeedback { Text(feedback).font(.callout).padding(11).background(.green.opacity(0.18), in: RoundedRectangle(cornerRadius: 9)) }
                }
                if let error = model.aiCoachError {
                    VStack(alignment: .leading, spacing: 6) {
                        Label("AI 教练已降级为本地课程引导", systemImage: "exclamationmark.triangle")
                            .font(.caption.weight(.semibold)).foregroundStyle(.orange)
                        Text(error).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                        HStack(spacing: 8) {
                            Button("重试 AI 教练") { Task { await model.refreshAICoach() } }
                            Button("检查 AI 服务") { model.showAIService = true }
                        }
                        .controlSize(.small)
                    }
                    .padding(10).frame(maxWidth: .infinity, alignment: .leading)
                    .background(.orange.opacity(0.10), in: RoundedRectangle(cornerRadius: 9))
                }
                Divider()
                Text(model.hasCourseCodeTask ? "练习思路 · 文字回答" : "回答本课问题").font(.headline)
                if model.coachPending {
                    CoachLoadingCard(status: "正在准备问题与答题区…", answerSkeleton: true)
                } else {
                if let plan = model.projectPlan, plan.submissionPolicy == nil {
                    VStack(alignment: .leading, spacing: 6) {
                        if let policy = plan.submissionPolicy {
                            Label("提交来源", systemImage: "signpost.right").font(.subheadline.weight(.semibold))
                            Text(policy.guidance)
                            Text("教练回讲与课程实践分别记录；代码提交只使用课程合同要求的已授权文件。")
                                .foregroundStyle(.secondary)
                        } else {
                            Label("旧课程格式", systemImage: "exclamationmark.triangle").font(.subheadline.weight(.semibold))
                            Text("这门课程未保存任务来源，无法安全启用工作区代码提交。文字回讲仍可正常记录。")
                            Text("升级会生成独立新版并保留旧课程；只有你点击后才会调用 AI。")
                                .foregroundStyle(.secondary)
                            Button(model.isPlanning ? "正在升级…" : "升级本课程") {
                                if let skill = model.activeTeachingSkill {
                                    Task { await model.loadProjectPlan(skill, mode: "upgrade") }
                                }
                            }
                            .buttonStyle(.bordered)
                            .disabled(model.isPlanning || model.activeTeachingSkill == nil)
                            if model.isPlanning {
                                VStack(alignment: .leading, spacing: 6) {
                                    HStack {
                                        ProgressView().controlSize(.small)
                                        Text(model.planningMode == "upgrade" ? "正在生成升级版" : "课程任务进行中")
                                        Spacer()
                                        if model.planningTotal > 0 {
                                            Text("\(model.planningCompleted)/\(model.planningTotal)").monospacedDigit()
                                        }
                                    }
                                    if model.planningTotal > 0 {
                                        ProgressView(value: Double(model.planningCompleted), total: Double(model.planningTotal))
                                    }
                                    Text(model.planningStatus).foregroundStyle(.secondary)
                                }
                                .padding(.top, 6)
                            }
                        }
                    }
                    .font(.caption)
                    .padding(12)
                    .background(.white.opacity(0.04), in: RoundedRectangle(cornerRadius: 10))
                }
                LabeledContent("本题练习", value: model.currentEvidenceTypeLabel)
                    .font(.callout.weight(.medium))
                Text(model.aiCoachTurn == nil
                     ? "当前是本地或旧课程引导，安全归类为概念回讲；不会自动读取 IDE。保存不等于验证通过。"
                     : "根据下方问题提交文字回答，AI 将给出依据与改进建议。")
                    .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                RichMarkdownPreview(text: model.answerPrompt)
                    .font(.callout).foregroundStyle(.secondary)
                TextField("写下你的回答和判断依据…", text: $model.reflection, axis: .vertical)
                    .lineLimit(4...10)
                    .textFieldStyle(.plain)
                    .glassInput()
                Button(model.isRecordingEvidence ? "正在评判…" : (model.projectPlan == nil ? "保存练习记录" : "提交回答并评判")) { Task { await model.recordReflection() } }
                    .buttonStyle(.borderedProminent)
                    .disabled(model.isRecordingEvidence || model.isLoadingAICoach)
                if let feedback = model.answerFeedback {
                    Text(feedback).font(.callout).textSelection(.enabled)
                }
                if let error = model.evidenceError {
                    Text(error).font(.caption).foregroundStyle(.orange)
                }
                if model.completedEvidence {
                    Label(model.hasCourseCodeTask ? "文字回答已记录；课程进度以代码任务评审为准。" : "本课回答已记录。", systemImage: "checkmark.seal.fill")
                        .font(.callout).foregroundStyle(.green)
                }
                }
                Divider()
                Text("遇到别的问题？").font(.headline)
                Text("直接用自然语言描述。Trainer 会自动识别要补的基础和项目技能，并生成一份候选教学 Skill。")
                    .font(.caption).foregroundStyle(.secondary)
                TextField("例如：为什么这个函数要先检查余额？", text: $model.learnerQuestion, axis: .vertical)
                    .lineLimit(2...5)
                    .textFieldStyle(.plain)
                    .glassInput()
                Button(model.isDetectingTeachingNeed ? "正在识别教学需要…" : "自动生成候选教学") {
                    Task { await model.submitLearnerQuestion() }
                }
                .disabled(model.isDetectingTeachingNeed)
                .buttonStyle(.bordered)
                if let error = model.automaticCandidateError {
                    Text(error).font(.caption).foregroundStyle(.orange)
                }
                Divider()
                Label(model.projectPlan == nil ? "本地教学示例" : "AI 生成课程 · 尚需内容验证", systemImage: "checkmark.shield")
                    .font(.caption).foregroundStyle(.secondary)
                CoachWorkspaceCard(model: model)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
        .frame(maxHeight: .infinity, alignment: .top)
        .padding(20)
        .background(.thinMaterial)
        .task(id: model.courseTaskKey) { await model.loadCourseTask() }
        .task(id: model.coachRefreshKey) {
            // Gateway startup and the panel appear concurrently on first launch.
            do { try await Task.sleep(for: .milliseconds(900)) } catch { return }
            await model.refreshAICoach()
        }
    }

    private var options: [WorkspaceModel.Prediction] { model.coachOptions }
}

struct CoachLoadingCard: View {
    let status: String
    var answerSkeleton = false
    @Environment(\.accessibilityReduceMotion) private var systemReduceMotion
    @AppStorage("trainer.motion.enabled") private var motionEnabled = true
    private var reduceMotion: Bool { systemReduceMotion || !motionEnabled }
    @State private var pulse = false
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 9) {
                ProgressView().controlSize(.small)
                Text(status.isEmpty ? "AI 教练正在准备本课引导…" : status)
                    .font(.callout.weight(.medium))
            }
            ForEach([0.88, 0.68, 0.78], id: \.self) { width in
                RoundedRectangle(cornerRadius: 7)
                    .fill(.white.opacity(pulse ? 0.18 : 0.08))
                    .frame(width: 280 * width, height: 15)
            }
            if answerSkeleton {
                RoundedRectangle(cornerRadius: 12)
                    .fill(.white.opacity(pulse ? 0.12 : 0.06))
                    .frame(height: 120)
                RoundedRectangle(cornerRadius: 7)
                    .fill(.indigo.opacity(pulse ? 0.30 : 0.15))
                    .frame(width: 150, height: 32)
            } else {
                Text("生成内容受当前 Skill、课程目标和安全边界约束。")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
        .padding(13)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.blue.opacity(0.10), in: RoundedRectangle(cornerRadius: 10))
        .onAppear { if !reduceMotion { withAnimation(.easeInOut(duration: 0.85).repeatForever(autoreverses: true)) { pulse = true } } }
        .accessibilityLabel("AI 教练正在生成本课引导")
    }
}

struct CoachWorkspaceCard: View {
    @ObservedObject var model: WorkspaceModel
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("学习状态", systemImage: "chart.line.uptrend.xyaxis")
                .font(.headline)
            Text(model.completedEvidence ? "已获得一条理解证据。接下来继续用新的例子检验迁移能力。" : "先完成预测或回讲。这里会持续显示你的理解证据与下一步建议。")
                .font(.caption).foregroundStyle(.secondary)
            Spacer(minLength: 8)
            HStack {
                Label(model.activeTeachingSkill == nil ? "等待选择 Skill" : "已绑定教学 Skill", systemImage: "books.vertical")
                Spacer()
                Image(systemName: model.completedEvidence ? "checkmark.seal.fill" : "circle.dashed")
                    .foregroundStyle(model.completedEvidence ? .green : .secondary)
            }
            .font(.caption)
        }
        .padding(14)
        .glassCard()
    }
}

struct SkillsLibrary: View {
    @Environment(\.dismiss) private var dismiss
    @State private var showBuilder = false
    @StateObject private var model = SkillLibraryModel()
    @State private var selectedSkill: SkillSummary?
    @State private var showPending = false
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text("Skill 知识库").font(.title2.weight(.semibold))
                Spacer()
                Button("待审批") { showPending = true }
                    .buttonStyle(.bordered)
                Button("生成候选 Skill") { showBuilder = true }
                    .buttonStyle(.borderedProminent)
                Button("完成") { dismiss() }
            }
            Text("Skill 是可审计的教学协议。生成内容必须经过验证才能成为可信课程。")
                .foregroundStyle(.secondary)
            if let error = model.error {
                Text(error).font(.caption).foregroundStyle(.orange)
            }
            List {
              ForEach(["project-practice", "course", "core"], id: \.self) { category in
                if model.skills.contains(where: { $0.categoryKey == category }) {
                  Section(SkillSummary.categoryTitle(category)) {
                    ForEach(model.skills.filter { $0.categoryKey == category }) { skill in
                Button { selectedSkill = skill } label: {
                    VStack(alignment: .leading, spacing: 4) {
                        HStack { Text(skill.title).font(.headline); Spacer(); Text(skill.status).font(.caption).foregroundStyle(.secondary) }
                        Text(skill.id).font(.caption).foregroundStyle(.secondary)
                    }.padding(.vertical, 4)
                }
                .buttonStyle(.plain)
                    }
                  }
                }
              }
            }
        }
        .padding(24)
        .frame(width: 620, height: 430)
        .sheet(isPresented: $showBuilder) { SkillBuilder() }
        .sheet(isPresented: $showPending) { PendingApprovalInbox() }
        .sheet(item: $selectedSkill) { SkillDetail(skill: $0) }
        .task { await model.load() }
    }
}

struct TeachingHub: View {
    @Environment(\.dismiss) private var dismiss
    @ObservedObject var model: WorkspaceModel
    @StateObject private var library = SkillLibraryModel()

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("选择教学方向").font(.title2.weight(.semibold))
                    Text("从任意 Skill 开始。Trainer 会读取它的教学上下文，自动衔接必要基础。")
                        .font(.callout).foregroundStyle(.secondary)
                }
                Spacer()
                Button("完成") { dismiss() }
            }
            if let error = library.error { Text(error).font(.caption).foregroundStyle(.orange) }
            List {
              ForEach(["project-practice", "course"], id: \.self) { category in
                if library.skills.contains(where: { $0.categoryKey == category }) {
                  Section(SkillSummary.categoryTitle(category)) {
                    ForEach(library.skills.filter { $0.categoryKey == category }) { skill in
                Button {
                    model.startTeaching(skill)
                    dismiss()
                } label: {
                    HStack(alignment: .center, spacing: 12) {
                        Image(systemName: icon(for: skill))
                            .foregroundStyle(skill.status == "verified" ? .green : .orange)
                        VStack(alignment: .leading, spacing: 4) {
                            Text(skill.title).font(.headline)
                            Text(languageDescription(skill))
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        Spacer()
                        Text(skill.status).font(.caption).foregroundStyle(.secondary)
                    }
                    .padding(.vertical, 5)
                }
                .buttonStyle(.plain)
                    }
                  }
                }
              }
            }
        }
        .padding(24)
        .frame(width: 680, height: 520)
        .task { await library.load() }
    }

    private func languageDescription(_ skill: SkillSummary) -> String {
        skill.languages.isEmpty ? "通用能力桥接 · 语言将在连接项目后识别" : "自动语言语境：\(skill.languages.joined(separator: " · "))"
    }

    private func icon(for skill: SkillSummary) -> String {
        skill.id.contains("solidity") ? "cube.transparent" : skill.id.contains("python") ? "chevron.left.forwardslash.chevron.right" : "book.closed"
    }
}

struct SkillSummary: Decodable, Identifiable {
    let id: String
    let title: String
    let status: String
    let path: String
    let version: String
    let languages: [String]
    var category: String? = nil
    var categoryKey: String { status == "core" ? "core" : (category ?? "course") }
    static func categoryTitle(_ category: String) -> String {
        category == "project-practice" ? "项目实战" : category == "core" ? "核心教学规则" : "课程教学"
    }
}

private struct SkillIndex: Decodable { let skills: [SkillSummary] }

@MainActor
final class SkillLibraryModel: ObservableObject {
    @Published var skills: [SkillSummary] = []
    @Published var error: String?

    func load() async {
        do {
            let (data, response) = try await URLSession.shared.data(from: URL(string: "http://127.0.0.1:8787/v1/skills")!)
            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else { throw GatewayFailure(message: "无法加载本地 Skill 知识库。") }
            skills = try JSONDecoder().decode(SkillIndex.self, from: data).skills
        } catch {
            self.error = "本地知识库暂不可用。请启动 Python Gateway。"
        }
    }
}

private struct SkillDocuments: Decodable { let documents: [String: String]; let ruleStatus: SkillRuleStatus? }
struct SkillRuleStatus: Decodable { let status: String; let message: String }

@MainActor
final class SkillDetailModel: ObservableObject {
    @Published var ruleStatus: SkillRuleStatus?
    @Published var documents: [String: String] = [:]
    @Published var error: String?

    func load(id: String) async {
        do {
            let encoded = id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? id
            let (data, response) = try await URLSession.shared.data(from: URL(string: "http://127.0.0.1:8787/v1/skills/\(encoded)")!)
            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else { throw GatewayFailure(message: "无法加载 Skill 内容。") }
            let detail = try JSONDecoder().decode(SkillDocuments.self, from: data)
            documents = detail.documents
            ruleStatus = detail.ruleStatus
        } catch {
            self.error = "无法读取此 Skill 的教学资产。"
        }
    }
}

struct SkillVersion: Decodable, Identifiable {
    let id: String
    let parentId: String?
    let state: String
    let createdAt: String
}
struct SkillVersionHistory: Decodable { let familyId: String; let activeId: String; let versions: [SkillVersion] }

@MainActor
final class SkillVersionModel: ObservableObject {
    @Published var history: SkillVersionHistory?
    @Published var error: String?
    func load(_ id: String) async {
        do {
            let encoded = id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? id
            let (data, response) = try await URLSession.shared.data(from: URL(string: "http://127.0.0.1:8787/v1/skills/\(encoded)/versions")!)
            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else { throw GatewayFailure(message: "无法读取版本历史。") }
            history = try JSONDecoder().decode(SkillVersionHistory.self, from: data)
        } catch { self.error = "版本历史暂不可用。" }
    }
    func change(_ skillID: String, targetID: String, action: String) async {
        do {
            let encoded = skillID.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? skillID
            var request = URLRequest(url: URL(string: "http://127.0.0.1:8787/v1/skills/\(encoded)/versions/\(action)")!)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONEncoder().encode(["targetId": targetID])
            request.setValue(LocalGatewaySession.token, forHTTPHeaderField: "X-Trainer-Session")
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else { throw GatewayFailure(message: "版本操作失败。") }
            history = try JSONDecoder().decode(SkillVersionHistory.self, from: data)
            error = nil
        } catch { self.error = error.localizedDescription }
    }
}

struct SkillVersionSheet: View {
    @Environment(\.dismiss) private var dismiss
    let skill: SkillSummary
    @StateObject private var model = SkillVersionModel()
    @State private var parentID = ""
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack { VStack(alignment: .leading) { Text("版本与回退").font(.title2.weight(.semibold)); Text("不会覆盖原版；当前教学版本由你明确选择。").font(.caption).foregroundStyle(.secondary) }; Spacer(); Button("完成") { dismiss() } }
            if let error = model.error { Text(error).foregroundStyle(.orange) }
            if let history = model.history {
                Text("版本家族：\(history.familyId)").font(.caption).foregroundStyle(.secondary)
                List(history.versions) { version in
                    HStack(spacing: 10) {
                        Image(systemName: version.id == history.activeId ? "checkmark.circle.fill" : "circle")
                            .foregroundStyle(version.id == history.activeId ? .green : .secondary)
                        VStack(alignment: .leading, spacing: 3) {
                            Text(version.id).font(.callout.weight(.semibold))
                            Text(version.state == "not-installed" ? "未安装的来源候选" : version.id == history.activeId ? "当前教学版本" : (version.state == "trashed" ? "已移入本地回收区" : "可用历史版本"))
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        Spacer()
                        if version.state == "trashed" {
                            Button("恢复") { Task { await model.change(skill.id, targetID: version.id, action: "restore") } }.buttonStyle(.bordered)
                        }
                        if version.state != "trashed" && version.state != "not-installed" && version.id != history.activeId {
                            Button("设为当前") { Task { await model.change(skill.id, targetID: version.id, action: "activate") } }.buttonStyle(.bordered)
                            if version.id != history.familyId {
                                Button("清理", role: .destructive) { Task { await model.change(skill.id, targetID: version.id, action: "trash") } }.buttonStyle(.bordered)
                            }
                        }
                    }
                }
            } else { ProgressView("正在读取版本历史…") }
            DisclosureGroup("关联早期版本") {
                Text("仅在你确认两份 Skill 属于同一课程时填写原版 ID。系统会保留关联前的版本记录。")
                    .font(.caption).foregroundStyle(.secondary)
                HStack {
                    TextField("原版 Skill ID", text: $parentID)
                    Button("关联到原版") { Task { await model.change(skill.id, targetID: parentID, action: "link") } }
                        .disabled(parentID.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            }
            Text("“清理”仅作用于非当前的 AI 生成版本，并移入本地回收区；基础、Core 和已验证资产受保护。选择任一可用旧版即可回退。")
                .font(.caption).foregroundStyle(.secondary)
        }
        .padding(24).frame(width: 760, height: 520)
        .task { await model.load(skill.id) }
    }
}

struct SkillDetail: View {
    @Environment(\.dismiss) private var dismiss
    let skill: SkillSummary
    @StateObject private var model = SkillDetailModel()
    @State private var richPreview = true
    @State private var showOptimization = false
    @State private var showVersions = false

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                VStack(alignment: .leading) {
                    Text(skill.title).font(.title2.weight(.semibold))
                    Text("\(skill.id) · \(skill.status)").font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Button(skill.status == "core" ? "提出 Core 优化提案" : "继续优化") { showOptimization = true }
                    .buttonStyle(.bordered)
                Button("版本与回退") { showVersions = true }
                    .buttonStyle(.bordered)
                Button("完成") { dismiss() }
            }
            if let rules = model.ruleStatus {
                Label(rules.message, systemImage: rules.status == "current" ? "checkmark.circle" : "info.circle")
                    .font(.caption).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let error = model.error {
                Text(error).foregroundStyle(.orange)
            }
            Picker("预览模式", selection: $richPreview) {
                Text("富文本预览").tag(true)
                Text("原始 Markdown").tag(false)
            }
            .pickerStyle(.segmented)
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    ForEach(model.documents.keys.sorted(), id: \.self) { path in
                        DraftPreview(title: path, text: model.documents[path] ?? "", rendered: richPreview)
                    }
                }
            }
        }
        .padding(24)
        .frame(width: 800, height: 700)
        .task { await model.load(id: skill.id) }
        .sheet(isPresented: $showOptimization) {
            SkillOptimizationSheet(target: .skill(id: skill.id, title: skill.title))
        }
        .sheet(isPresented: $showVersions) { SkillVersionSheet(skill: skill) }
    }
}

struct PendingSummary: Decodable, Identifiable {
    let pendingId: String
    let source: String
    let createdAt: String
    let title: String
    let skillId: String
    let valid: Bool
    var id: String { pendingId }
}

private struct PendingIndex: Decodable { let candidates: [PendingSummary] }
private struct PendingRecord: Decodable { let pendingId: String; let source: String; let createdAt: String; let result: SkillGenerationResponse }

@MainActor
final class PendingApprovalModel: ObservableObject {
    @Published var candidates: [PendingSummary] = []
    @Published var error: String?
    func load() async {
        do {
            let (data, response) = try await URLSession.shared.data(from: URL(string: "http://127.0.0.1:8787/v1/pending")!)
            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else { throw GatewayFailure(message: "无法读取待审批候选。") }
            candidates = try JSONDecoder().decode(PendingIndex.self, from: data).candidates
        } catch { self.error = "待审批收件箱暂不可用。" }
    }
}

struct PendingApprovalInbox: View {
    @Environment(\.dismiss) private var dismiss
    @StateObject private var model = PendingApprovalModel()
    @State private var selected: PendingSummary?
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                VStack(alignment: .leading, spacing: 3) {
                    Text("待人工审批").font(.title2.weight(.semibold))
                    Text("手动生成、对话识别与 VS Code 识别的候选都会集中在这里；审批前不会进入课程库。")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Button("完成") { dismiss() }
            }
            if let error = model.error { Text(error).foregroundStyle(.orange) }
            if model.candidates.isEmpty {
                ContentUnavailableView("没有待审批候选", systemImage: "checkmark.circle", description: Text("新的 AI 候选会自动进入这里。"))
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List(model.candidates) { item in
                    Button { selected = item } label: {
                        HStack {
                            Image(systemName: item.valid ? "checkmark.shield" : "exclamationmark.triangle")
                                .foregroundStyle(item.valid ? .green : .orange)
                            VStack(alignment: .leading) {
                                Text(item.title).font(.headline)
                                Text("\(sourceLabel(item.source)) · \(item.skillId)").font(.caption).foregroundStyle(.secondary)
                            }
                            Spacer()
                        }
                    }.buttonStyle(.plain)
                }
            }
        }
        .padding(24)
        .frame(width: 720, height: 560)
        .task { await model.load() }
        .sheet(item: $selected, onDismiss: { Task { await model.load() } }) { item in PendingApprovalReview(item: item) }
    }
    private func sourceLabel(_ source: String) -> String {
        switch source { case "editor": "VS Code 自动识别"; case "conversation": "对话自动识别"; default: "手动生成" }
    }
}

struct PendingApprovalReview: View {
    @Environment(\.dismiss) private var dismiss
    let item: PendingSummary
    @State private var record: PendingRecord?
    @State private var rich = true
    @State private var message: String?
    @State private var showDiscardConfirmation = false
    @State private var showOptimization = false
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack { Text("审阅候选").font(.title2.weight(.semibold)); Spacer(); Button("完成") { dismiss() } }
            if let record {
                Label(record.result.validation.valid ? "结构验证通过：provisional" : "结构验证未通过", systemImage: record.result.validation.valid ? "checkmark.shield.fill" : "exclamationmark.triangle.fill")
                    .foregroundStyle(record.result.validation.valid ? .green : .orange)
                Text(record.result.draft.title).font(.headline)
                Picker("预览模式", selection: $rich) { Text("富文本预览").tag(true); Text("原始 Markdown").tag(false) }.pickerStyle(.segmented)
                ScrollView { DraftPreview(title: "SKILL.md", text: record.result.draft.skillMarkdown, rendered: rich) }
                if let message { Text(message).font(.caption).foregroundStyle(.green) }
                HStack {
                    if record.result.validation.valid {
                        Button("确认保存到本地候选知识库") { Task { await approve() } }.buttonStyle(.borderedProminent)
                    }
                    Button("驳回并优化") { showOptimization = true }
                        .buttonStyle(.bordered)
                    Button("丢弃候选", role: .destructive) { showDiscardConfirmation = true }
                        .buttonStyle(.bordered)
                }
            } else { ProgressView("正在读取候选…") }
        }
        .padding(24).frame(width: 780, height: 680)
        .task { await load() }
        .confirmationDialog("丢弃这个候选 Skill？", isPresented: $showDiscardConfirmation, titleVisibility: .visible) {
            Button("确认丢弃", role: .destructive) { Task { await discard() } }
        } message: {
            Text("候选会从待审批收件箱移除，无法恢复；已进入知识库的 Skill 不受影响。")
        }
        .sheet(isPresented: $showOptimization) {
            SkillOptimizationSheet(target: .pending(id: item.pendingId, title: item.title))
        }
    }
    private func load() async {
        do {
            let (data, _) = try await URLSession.shared.data(from: URL(string: "http://127.0.0.1:8787/v1/pending/\(item.pendingId)")!)
            record = try JSONDecoder().decode(PendingRecord.self, from: data)
        } catch { message = "无法读取候选详情。" }
    }
    private func approve() async {
        do {
            var request = URLRequest(url: URL(string: "http://127.0.0.1:8787/v1/pending/\(item.pendingId)/approve")!)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            let (_, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else { throw GatewayFailure(message: "审批保存失败。") }
            message = "已保存，并从待审批收件箱移除。"
        } catch { message = error.localizedDescription }
    }
    private func discard() async {
        do {
            var request = URLRequest(url: URL(string: "http://127.0.0.1:8787/v1/pending/\(item.pendingId)")!)
            request.httpMethod = "DELETE"
            let (_, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else { throw GatewayFailure(message: "丢弃候选失败。") }
            message = "候选已丢弃并从待审批收件箱移除。"
        } catch { message = error.localizedDescription }
    }
}

enum SkillOptimizationTarget {
    case pending(id: String, title: String)
    case skill(id: String, title: String)

    var id: String {
        switch self { case let .pending(id, _), let .skill(id, _): id }
    }

    var title: String {
        switch self { case let .pending(_, title), let .skill(_, title): title }
    }

    var targetType: String {
        switch self { case .pending: "pending"; case .skill: "skill" }
    }

    var actionLabel: String {
        switch self { case .pending: "驳回并生成优化候选"; case .skill: "生成优化候选" }
    }

    var isCore: Bool { id.hasPrefix("core.") }
}

private struct OptimizationAuthorizationRequest: Encodable {
    let targetType: String
    let targetId: String
}

private struct OptimizationAuthorizationResponse: Decodable {
    let authorizationToken: String
}

private struct OptimizationRequest: Encodable {
    let feedback: String
    let authorizationToken: String
}

struct SkillOptimizationSheet: View {
    @Environment(\.dismiss) private var dismiss
    let target: SkillOptimizationTarget
    @State private var feedback = ""
    @State private var isOptimizing = false
    @State private var result: SkillGenerationResponse?
    @State private var error: String?
    @State private var richPreview = true

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text(target.isCore ? "提出 Core 优化提案" : (target.targetType == "pending" ? "驳回并优化候选" : "继续优化教学 Skill"))
                        .font(.title2.weight(.semibold))
                    Text(target.title).font(.callout).foregroundStyle(.secondary)
                }
                Spacer()
                Button("完成") { dismiss() }
            }
            Text(target.isCore ? "Core 提案会遵循专门的治理规范：保留原版、生成新候选、附带影响分析与回退要求；不会直接修改当前 Core。" : "将所选 Skill 完整内容发送给已配置的 DeepSeek，仅用于生成新的 provisional 候选；原版本不会被覆盖。")
                .font(.caption).foregroundStyle(.secondary)
                .padding(11)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(.orange.opacity(0.10), in: RoundedRectangle(cornerRadius: 10))
            Text("补充优化要求（可选）").font(.headline)
            Text("不填写也会严格按《教学 Skill 优化规范》执行；这里的内容只补充你的偏好，不能覆盖规范。")
                .font(.caption).foregroundStyle(.secondary)
            TextEditor(text: $feedback)
                .font(.body)
                .frame(minHeight: 90, maxHeight: 130)
                .glassInput()
                .overlay(alignment: .topLeading) {
                    if feedback.isEmpty {
                        Text("例如：加强并发细节、增加可预测练习，或解释某个项目模块…")
                            .font(.body).foregroundStyle(.secondary.opacity(0.75))
                            .padding(.horizontal, 15).padding(.vertical, 14)
                            .allowsHitTesting(false)
                    }
                }

            if let error {
                Label(error, systemImage: "exclamationmark.triangle").font(.caption).foregroundStyle(.red)
            }
            if let result {
                Divider()
                Label(result.validation.valid ? "优化候选已通过结构验证" : "优化候选需要修正", systemImage: result.validation.valid ? "checkmark.shield.fill" : "exclamationmark.triangle.fill")
                    .foregroundStyle(result.validation.valid ? .green : .orange)
                Text(result.draft.title).font(.headline)
                Text(result.draft.summary).font(.callout).foregroundStyle(.secondary)
                Text("新候选已进入“待审批”，请在那里审阅并确认保存。")
                    .font(.caption).foregroundStyle(.secondary)
                Picker("预览模式", selection: $richPreview) {
                    Text("富文本预览").tag(true)
                    Text("原始 Markdown").tag(false)
                }.pickerStyle(.segmented)
                ScrollView { DraftPreview(title: "SKILL.md", text: result.draft.skillMarkdown, rendered: richPreview) }
                    .frame(maxHeight: .infinity)
            } else {
                Button {
                    Task { await optimize() }
                } label: {
                    Label(isOptimizing ? "正在按教学规范优化…" : target.actionLabel, systemImage: "wand.and.stars")
                }
                .buttonStyle(.borderedProminent)
                .disabled(isOptimizing)
                Spacer(minLength: 0)
            }
        }
        .padding(24)
        .frame(width: 760, height: 680)
    }

    private func sessionRequest(_ url: URL, method: String) -> URLRequest {
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(LocalGatewaySession.token, forHTTPHeaderField: "X-Trainer-Session")
        return request
    }

    private func optimize() async {
        isOptimizing = true
        error = nil
        defer { isOptimizing = false }
        do {
            var authorization = sessionRequest(URL(string: "http://127.0.0.1:8787/v1/optimization/authorizations")!, method: "POST")
            authorization.httpBody = try JSONEncoder().encode(OptimizationAuthorizationRequest(targetType: target.targetType, targetId: target.id))
            let (authorizationData, authorizationResponse) = try await URLSession.shared.data(for: authorization)
            guard let authorizationHTTP = authorizationResponse as? HTTPURLResponse, (200...299).contains(authorizationHTTP.statusCode) else {
                throw GatewayFailure(message: (try? JSONDecoder().decode(GatewayError.self, from: authorizationData).error) ?? "无法确认优化授权。")
            }
            let token = try JSONDecoder().decode(OptimizationAuthorizationResponse.self, from: authorizationData).authorizationToken
            let encodedID = target.id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? target.id
            let path = target.targetType == "pending" ? "/v1/pending/\(encodedID)/optimize/jobs" : "/v1/skills/\(encodedID)/optimize/jobs"
            var request = sessionRequest(URL(string: "http://127.0.0.1:8787\(path)")!, method: "POST")
            request.httpBody = try JSONEncoder().encode(OptimizationRequest(feedback: feedback, authorizationToken: token))
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
                throw GatewayFailure(message: (try? JSONDecoder().decode(GatewayError.self, from: data).error) ?? "无法开始 AI 优化。")
            }
            let job = try JSONDecoder().decode(SkillGenerationJob.self, from: data)
            try await poll(jobID: job.id)
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func poll(jobID: String) async throws {
        while true {
            try await Task.sleep(for: .seconds(1))
            let (data, response) = try await URLSession.shared.data(from: URL(string: "http://127.0.0.1:8787/v1/jobs/\(jobID)")!)
            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else { throw GatewayFailure(message: "无法读取优化任务状态。") }
            let job = try JSONDecoder().decode(SkillGenerationJob.self, from: data)
            if job.status == "completed", let result = job.result { self.result = result; return }
            if ["failed", "paused", "cancelled"].contains(job.status) { throw GatewayFailure(message: job.error ?? "优化任务已停止，可在任务中心继续。") }
        }
    }
}

struct SkillGenerationRequest: Encodable {
    let seed: String
    let language: String
    let projectContext: String
    let generationMode: String
}

struct EvidenceRequest: Encodable {
    let conceptId: String
    let level: Int
    let evidenceType: String
    let note: String
    let language: String
}

struct TeachingSignalRequest: Encodable {
    let text: String
    let language: String
    let projectContext: String
}

struct ProjectImportRequest: Encodable {
    let path: String
}

struct ImportedProjectMetadata: Decodable {
    let name: String
    let stack: [String]
    let fileCount: Int
}

struct ProjectImportJob: Decodable {
    let id: String
    let status: String
    let error: String?
    let project: ImportedProjectMetadata?
}

struct SkillGenerationResponse: Decodable {
    let draft: GeneratedSkillDraft
    let validation: DraftValidation
    let model: String?
    let pending: PendingReference?
}
struct PendingReference: Decodable { let pendingId: String }

struct GeneratedSkillDraft: Codable {
    var ruleProvenance: RuleProvenance? = nil
    let id: String
    let title: String
    let summary: String
    let skillMarkdown: String
    let curriculumYaml: String
    let conceptMarkdown: String
    let exerciseMarkdown: String
    let validationChecklist: String
}

struct DraftValidation: Codable {
    let valid: Bool
    let errors: [String]
}

struct RuleProvenance: Codable {
    let fingerprint: String
    let generationMode: String
    let builderVersion: String
    let sources: [String: String]
    let verification: String
}

struct SkillGenerationJob: Decodable {
    let id: String
    let status: String
    let result: SkillGenerationResponse?
    let error: String?
}

struct DraftApproval: Encodable {
    let draft: GeneratedSkillDraft
}

@MainActor
final class SkillBuilderModel: ObservableObject {
    var practice = false
    @Published var seed = ""
    @Published var projectContext = ""
    @Published var isGenerating = false
    @Published var draft: GeneratedSkillDraft?
    @Published var validation: DraftValidation?
    @Published var error: String?
    @Published var isSaving = false
    @Published var savedPath: String?
    private var pendingID: String?

    var detectedTechnologies: [String] {
        let source = "\(seed) \(projectContext)".lowercased()
        var technologies: [String] = []
        func add(_ name: String, when condition: Bool) { if condition && !technologies.contains(name) { technologies.append(name) } }
        add("Solidity", when: source.contains("solidity") || source.contains("evm"))
        add("Python", when: source.contains("python") || source.contains("pandas"))
        add("Rust", when: source.contains("rust"))
        add("Go", when: source.contains("golang") || source.contains("go "))
        add("TypeScript", when: source.contains("typescript") || source.contains(".tsx") || source.contains("next.js") || source.contains("nextjs"))
        add("JavaScript", when: source.contains("javascript") && !technologies.contains("TypeScript"))
        add("Next.js", when: source.contains("next.js") || source.contains("nextjs"))
        add("PostgreSQL", when: source.contains("postgresql") || source.contains("postgres"))
        add("SQL", when: source.contains("sql") && !technologies.contains("PostgreSQL"))
        add("Java", when: source.contains("java") && !source.contains("javascript"))
        return technologies
    }

    var detectedTechnologyContext: String {
        detectedTechnologies.isEmpty ? "由模型从来源 Skill 识别" : detectedTechnologies.joined(separator: " · ")
    }

    func generate() async {
        isGenerating = true
        error = nil
        draft = nil
        validation = nil
        savedPath = nil
        do {
            let request = SkillGenerationRequest(seed: seed, language: detectedTechnologyContext, projectContext: projectContext, generationMode: practice ? "project-practice" : "course")
            var urlRequest = URLRequest(url: URL(string: "http://127.0.0.1:8787/v1/skills/generate/jobs")!)
            urlRequest.httpMethod = "POST"
            urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
            urlRequest.httpBody = try JSONEncoder().encode(request)
            let (data, response) = try await URLSession.shared.data(for: urlRequest)
            guard let http = response as? HTTPURLResponse else { throw URLError(.badServerResponse) }
            guard (200...299).contains(http.statusCode) else {
                let message = (try? JSONDecoder().decode(GatewayError.self, from: data).error) ?? "Gateway returned HTTP \(http.statusCode)."
                throw GatewayFailure(message: message)
            }
            let job = try JSONDecoder().decode(SkillGenerationJob.self, from: data)
            try await poll(jobID: job.id)
        } catch {
            self.error = "无法生成候选 Skill：\(error.localizedDescription)"
        }
        isGenerating = false
    }

    func saveApprovedDraft() async {
        guard let draft, validation?.valid == true else { return }
        isSaving = true
        error = nil
        defer { isSaving = false }
        do {
            let endpoint = pendingID.map { "http://127.0.0.1:8787/v1/pending/\($0)/approve" } ?? "http://127.0.0.1:8787/v1/skills/\(draft.id)/approve"
            var request = URLRequest(url: URL(string: endpoint)!)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONEncoder().encode(DraftApproval(draft: draft))
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
                let message = (try? JSONDecoder().decode(GatewayError.self, from: data).error) ?? "保存失败。"
                throw GatewayFailure(message: message)
            }
            let saved = try JSONDecoder().decode(SavedSkill.self, from: data)
            savedPath = saved.path
        } catch {
            self.error = "无法保存候选 Skill：\(error.localizedDescription)"
        }
    }

    private func poll(jobID: String) async throws {
        while true {
            try await Task.sleep(for: .seconds(1))
            let (data, response) = try await URLSession.shared.data(from: URL(string: "http://127.0.0.1:8787/v1/jobs/\(jobID)")!)
            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
                throw GatewayFailure(message: "无法读取 AI 生成任务状态。")
            }
            let job = try JSONDecoder().decode(SkillGenerationJob.self, from: data)
            switch job.status {
            case "completed":
                guard let result = job.result else { throw GatewayFailure(message: "任务完成但没有草案。") }
                draft = result.draft
                pendingID = result.pending?.pendingId
                validation = result.validation
                return
            case "failed", "paused", "cancelled":
                throw GatewayFailure(message: job.error ?? "AI 生成任务失败。")
            default:
                continue
            }
        }
    }
}

private struct SavedSkill: Decodable {
    let path: String
}

private struct GatewayError: Decodable { let error: String }
private struct GatewayFailure: LocalizedError {
    let message: String
    var errorDescription: String? { message }
}

struct SkillBuilder: View {
    @Environment(\.dismiss) private var dismiss
    @StateObject private var model: SkillBuilderModel
    let practice: Bool
    @State private var previewIsRich = true
    init(practice: Bool = false) {
        self.practice = practice
        let builder = SkillBuilderModel()
        builder.practice = practice
        _model = StateObject(wrappedValue: builder)
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
            HStack {
                VStack(alignment: .leading, spacing: 3) {
                    Text(practice ? "项目实战 · 从目标到可运行项目" : "创建课程 Skill").font(.title2.weight(.semibold))
                    Text("输出始终是候选草案；通过验证和人工审阅前不会写入知识库。")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Button("完成") { dismiss() }
            }
            GroupBox("详细的来源 Skill / Markdown / 教学需求") {
                TextField("描述想学的技术、现有基础、目标作品和学习要求；也可粘贴 Skill / Markdown…", text: $model.seed, axis: .vertical)
                    .lineLimit(4...9)
                    .textFieldStyle(.plain)
                    .glassInput()
            }
            if practice {
                Text("请描述想做的项目、现有基础、操作系统和 IDE。AI 将生成环境搭建、模块实现、测试验收与迁移步骤；你在自己的 IDE 编写代码。审批后从教学入口选择该 Skill 开始。")
                    .font(.callout).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
            HStack {
                Label("自动识别技术栈：\(model.detectedTechnologyContext)", systemImage: "wand.and.stars")
                    .font(.caption).foregroundStyle(.secondary)
                Spacer()
                TextField("项目语境（可选补充）", text: $model.projectContext)
                    .textFieldStyle(.plain)
                    .glassInput()
                    .frame(maxWidth: 360)
            }
            Button {
                Task { await model.generate() }
            } label: {
                Label(model.isGenerating ? "正在生成…" : "生成并验证候选 Skill", systemImage: "sparkles")
            }
            .buttonStyle(.borderedProminent)
            .disabled(model.isGenerating || model.seed.trimmingCharacters(in: .whitespacesAndNewlines).count < 40)
            Text("请至少填写 40 个字符。不需要导入项目；无源码时使用明确标注的教学示例，与项目课程遵循相同的深度、练习和审批规范。")
                .font(.caption).foregroundStyle(.secondary)
            if model.isGenerating { ProgressView("正在生成并验证课程候选，完成后进入待审批…") }

            if let error = model.error {
                Text(error).font(.callout).foregroundStyle(.red)
            }
            if let draft = model.draft, let validation = model.validation {
                Divider()
                HStack {
                    Label(validation.valid ? "结构验证通过：provisional" : "结构验证未通过", systemImage: validation.valid ? "checkmark.shield.fill" : "exclamationmark.triangle.fill")
                        .foregroundStyle(validation.valid ? .green : .orange)
                    Spacer()
                    Text(draft.id).font(.caption).foregroundStyle(.secondary)
                }
                Text(draft.title).font(.headline)
                Text(draft.summary).font(.callout).foregroundStyle(.secondary)
                if let rules = draft.ruleProvenance {
                    Text("规则版本 \(rules.fingerprint.prefix(12)) · \(rules.generationMode) · 不代表内容已验证")
                        .font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                }
                if validation.valid {
                    Button {
                        Task { await model.saveApprovedDraft() }
                    } label: {
                        Label(model.isSaving ? "正在保存…" : "确认保存到本地候选知识库", systemImage: "checkmark.circle")
                    }
                    .buttonStyle(.bordered)
                    .disabled(model.isSaving || model.savedPath != nil)
                }
                if let path = model.savedPath {
                    Label("已保存：\(path)", systemImage: "checkmark.seal.fill")
                        .font(.caption).foregroundStyle(.green)
                }
                Picker("预览模式", selection: $previewIsRich) {
                    Text("富文本预览").tag(true)
                    Text("原始 Markdown").tag(false)
                }
                .pickerStyle(.segmented)
                ScrollView {
                    VStack(alignment: .leading, spacing: 10) {
                        DraftPreview(title: "SKILL.md", text: draft.skillMarkdown, rendered: previewIsRich)
                        DraftPreview(title: "curriculum.yaml", text: draft.curriculumYaml, rendered: previewIsRich)
                        DraftPreview(title: "概念课", text: draft.conceptMarkdown, rendered: previewIsRich)
                        DraftPreview(title: "练习", text: draft.exerciseMarkdown, rendered: previewIsRich)
                        if !validation.errors.isEmpty { DraftPreview(title: "验证问题", text: validation.errors.joined(separator: "\n")) }
                    }
                }
                .frame(maxHeight: 280)
            } else {
                GenerationStage(technologies: model.detectedTechnologies)
                    .frame(maxWidth: .infinity)
            }
            }
            .padding(28)
            .frame(maxWidth: .infinity, alignment: .topLeading)
        }
        .frame(width: 820, height: 650)
    }
}

struct GenerationStage: View {
    let technologies: [String]
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Label("生成前的教学设计", systemImage: "point.3.connected.trianglepath.dotted")
                .font(.headline)
            Text("Trainer 会先把技术栈拆为基础能力、项目语境和可验证练习；生成结果始终只是一份可审阅候选。")
                .foregroundStyle(.secondary)
            HStack(spacing: 12) {
                GenerationStep(number: "1", title: "识别技术栈", detail: technologies.isEmpty ? "从来源内容提取" : technologies.joined(separator: " · "))
                GenerationStep(number: "2", title: "补齐基础", detail: "语法、函数、运行时与数据模型")
                GenerationStep(number: "3", title: "候选审阅", detail: "结构校验后由你确认入库")
            }
            Label("不会扫描工作区，也不会把候选自动提升为 verified。", systemImage: "lock.shield")
                .font(.caption).foregroundStyle(.secondary)
        }
        .padding(22)
        .glassCard()
    }
}

struct GenerationStep: View {
    let number: String
    let title: String
    let detail: String
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(number).font(.title3.weight(.bold)).foregroundStyle(.blue)
            Text(title).font(.headline)
            Text(detail).font(.caption).foregroundStyle(.secondary).lineLimit(4)
        }
        .frame(maxWidth: .infinity, minHeight: 110, alignment: .topLeading)
        .padding(14)
        .background(.white.opacity(0.07), in: RoundedRectangle(cornerRadius: 10))
    }
}

struct CandidateReview: View {
    @Environment(\.dismiss) private var dismiss
    let result: SkillGenerationResponse
    @State private var isSaving = false
    @State private var savedPath: String?
    @State private var error: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("自动识别的候选教学").font(.title2.weight(.semibold))
                    Text("模型已生成草案，但它尚未进入课程库。请先审阅，再决定是否保存。")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Button("稍后处理") { dismiss() }
            }
            Label(result.validation.valid ? "结构验证通过：provisional" : "结构验证未通过", systemImage: result.validation.valid ? "checkmark.shield.fill" : "exclamationmark.triangle.fill")
                .foregroundStyle(result.validation.valid ? .green : .orange)
            Text(result.draft.title).font(.headline)
            Text(result.draft.summary).foregroundStyle(.secondary)
            if let error { Text(error).font(.caption).foregroundStyle(.red) }
            if let savedPath {
                Label("已保存到候选知识库：\(savedPath)", systemImage: "checkmark.seal.fill")
                    .foregroundStyle(.green)
            } else if result.validation.valid {
                Button(isSaving ? "正在确认…" : "审阅后确认保存") { Task { await approve() } }
                    .disabled(isSaving)
                    .buttonStyle(.borderedProminent)
            }
            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    DraftPreview(title: "SKILL.md", text: result.draft.skillMarkdown)
                    DraftPreview(title: "curriculum.yaml", text: result.draft.curriculumYaml)
                    DraftPreview(title: "概念课", text: result.draft.conceptMarkdown)
                    DraftPreview(title: "练习", text: result.draft.exerciseMarkdown)
                    if !result.validation.errors.isEmpty { DraftPreview(title: "验证问题", text: result.validation.errors.joined(separator: "\n")) }
                }
            }
        }
        .padding(24)
        .frame(width: 780, height: 720)
    }

    private func approve() async {
        isSaving = true
        defer { isSaving = false }
        do {
            let endpoint = result.pending.map { "http://127.0.0.1:8787/v1/pending/\($0.pendingId)/approve" } ?? "http://127.0.0.1:8787/v1/skills/\(result.draft.id)/approve"
            var request = URLRequest(url: URL(string: endpoint)!)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONEncoder().encode(DraftApproval(draft: result.draft))
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
                throw GatewayFailure(message: (try? JSONDecoder().decode(GatewayError.self, from: data).error) ?? "保存失败。")
            }
            savedPath = try JSONDecoder().decode(SavedSkill.self, from: data).path
        } catch {
            self.error = error.localizedDescription
        }
    }
}

struct DraftPreview: View {
    let title: String
    let text: String
    var rendered = false
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.caption.weight(.semibold)).foregroundStyle(.secondary)
            Group {
                if rendered, title.lowercased().hasSuffix(".md") {
                    RichMarkdownPreview(text: text)
                } else {
                    Text(text).font(.system(.caption, design: .monospaced))
                }
            }
            .textSelection(.enabled)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(9).background(.white.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
        }
    }
}

private enum MarkdownPreviewBlock {
    case metadata([(String, String)])
    case heading(Int, String)
    case paragraph(String)
    case bullet(String)
    case ordered(String)
    case quote(String)
    case code(String, String)
    case divider
    case table([[String]])
}

private struct RichMarkdownPreview: View {
    let text: String
    @AppStorage("trainer.reading.size") private var readingSize = 15.0
    @AppStorage("trainer.reading.style") private var readingStyle = "system"

    private var blocks: [MarkdownPreviewBlock] { MarkdownPreviewParser.parse(text) }

    var body: some View {
        VStack(alignment: .leading, spacing: 11) {
            ForEach(Array(blocks.enumerated()), id: \.offset) { _, block in
                switch block {
                case let .metadata(values):
                    VStack(alignment: .leading, spacing: 5) {
                        Text("Skill 元数据").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                        ForEach(values, id: \.0) { key, value in
                            HStack(alignment: .firstTextBaseline, spacing: 8) {
                                Text(key).font(.system(.caption, design: .monospaced)).foregroundStyle(.secondary)
                                Text(value).font(.caption)
                            }
                        }
                    }
                    .padding(10)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(.blue.opacity(0.10), in: RoundedRectangle(cornerRadius: 8))
                case let .heading(level, value):
                    Text(markdownText(value))
                        .font(.system(size: readingSize + (level == 1 ? 6 : 3), weight: .semibold, design: readingDesign(readingStyle)))
                        .padding(.top, 14).padding(.bottom, 4)
                case let .paragraph(value):
                    Text(markdownText(value)).font(.system(size: readingSize, design: readingDesign(readingStyle))).fixedSize(horizontal: false, vertical: true)
                case let .bullet(value):
                    HStack(alignment: .top, spacing: 8) {
                        Text("•").foregroundStyle(.blue)
                        Text(markdownText(value)).font(.system(size: readingSize, design: readingDesign(readingStyle))).fixedSize(horizontal: false, vertical: true)
                    }
                case let .ordered(value):
                    HStack(alignment: .top, spacing: 8) {
                        Text(markdownText(value)).font(.system(size: readingSize, design: readingDesign(readingStyle))).fixedSize(horizontal: false, vertical: true)
                    }
                case let .quote(value):
                    Text(markdownText(value)).font(.system(size: readingSize, design: readingDesign(readingStyle)).italic()).foregroundStyle(.secondary)
                        .padding(.leading, 11)
                        .overlay(alignment: .leading) { Capsule().fill(.blue.opacity(0.6)).frame(width: 3) }
                case let .code(value, language):
                    TeachingCodeBlock(code: value, language: language)
                case let .table(rows):
                    ScrollView(.horizontal) {
                        Grid(alignment: .topLeading, horizontalSpacing: 0, verticalSpacing: 0) {
                            ForEach(Array(rows.enumerated()), id: \.offset) { rowIndex, cells in
                                GridRow {
                                    ForEach(Array(cells.enumerated()), id: \.offset) { _, cell in
                                        Text(markdownText(cell))
                                            .font(.system(size: readingSize, design: readingDesign(readingStyle))).fontWeight(rowIndex == 0 ? .semibold : .regular)
                                            .fixedSize(horizontal: false, vertical: true)
                                            .frame(width: 210, alignment: .leading).padding(10)
                                            .background(rowIndex == 0 ? Color.blue.opacity(0.14) : Color.white.opacity(0.03))
                                            .overlay(Rectangle().stroke(.secondary.opacity(0.2), lineWidth: 0.5))
                                    }
                                }
                            }
                        }
                    }
                case .divider:
                    Divider()
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func markdownText(_ value: String) -> AttributedString {
        (try? AttributedString(markdown: value, options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace))) ?? AttributedString(value)
    }
}

private enum MarkdownPreviewParser {
    static func parse(_ source: String) -> [MarkdownPreviewBlock] {
        var lines = source.components(separatedBy: .newlines)
        var blocks: [MarkdownPreviewBlock] = []
        var paragraph: [String] = []
        var tableLines: [String] = []
        func flushTable() {
            guard !tableLines.isEmpty else { return }
            let rows = tableLines.map { line in
                line.trimmingCharacters(in: CharacterSet(charactersIn: "|"))
                    .components(separatedBy: "|").map { $0.trimmingCharacters(in: .whitespaces) }
            }
            if rows.count >= 2 && rows[1].allSatisfy({ $0.range(of: "^:?-{3,}:?$", options: .regularExpression) != nil }) {
                blocks.append(.table([rows[0]] + Array(rows.dropFirst(2))))
            } else { blocks.append(.paragraph(tableLines.joined(separator: "\n"))) }
            tableLines.removeAll()
        }

        func flushParagraph() {
            guard !paragraph.isEmpty else { return }
            blocks.append(.paragraph(paragraph.joined(separator: " ")))
            paragraph.removeAll()
        }

        if lines.first == "---", let closing = lines.dropFirst().firstIndex(of: "---") {
            let metadata = lines[1..<closing].compactMap { line -> (String, String)? in
                guard let separator = line.firstIndex(of: ":"), !line.hasPrefix((" ")) else { return nil }
                return (String(line[..<separator]), String(line[line.index(after: separator)...]).trimmingCharacters(in: .whitespaces))
            }
            if !metadata.isEmpty { blocks.append(.metadata(metadata)) }
            lines = Array(lines[(closing + 1)...])
        }

        var isCode = false
        var codeLanguage = "code"
        var code: [String] = []
        for raw in lines {
            let line = raw.trimmingCharacters(in: .whitespaces)
            if !isCode && line.hasPrefix("|") && line.hasSuffix("|") {
                flushParagraph(); tableLines.append(line); continue
            }
            flushTable()
            if line.hasPrefix("```") {
                flushParagraph()
                if isCode { blocks.append(.code(code.joined(separator: "\n"), codeLanguage)); code.removeAll() }
                else { codeLanguage = String(line.dropFirst(3)).isEmpty ? "code" : String(line.dropFirst(3)) }
                isCode.toggle()
                continue
            }
            if isCode { code.append(raw); continue }
            // Legacy line-by-line explanations: preserve wording, separate the
            // existing line label and explicitly backticked snippet for reading.
            if let label = line.range(of: "^第\\s*[0-9]+(?:[–—-][0-9]+)?\\s*行", options: .regularExpression) {
                flushParagraph()
                blocks.append(.heading(3, String(line[label])))
                var rest = String(line[label.upperBound...]).trimmingCharacters(in: CharacterSet(charactersIn: " ：:"))
                if rest.hasPrefix("`"), let end = rest.dropFirst().firstIndex(of: "`") {
                    blocks.append(.code(String(rest[rest.index(after: rest.startIndex)..<end]), "code"))
                    rest = String(rest[rest.index(after: end)...]).trimmingCharacters(in: CharacterSet(charactersIn: " ：:"))
                }
                if !rest.isEmpty { blocks.append(.paragraph(rest)) }
                continue
            }
            if line.isEmpty { flushParagraph(); continue }
            if line == "---" || line == "***" { flushParagraph(); blocks.append(.divider); continue }
            if line.hasPrefix("### ") { flushParagraph(); blocks.append(.heading(3, String(line.dropFirst(4)))); continue }
            if line.hasPrefix("## ") { flushParagraph(); blocks.append(.heading(2, String(line.dropFirst(3)))); continue }
            if line.hasPrefix("# ") { flushParagraph(); blocks.append(.heading(1, String(line.dropFirst(2)))); continue }
            if line.hasPrefix("> ") { flushParagraph(); blocks.append(.quote(String(line.dropFirst(2)))); continue }
            if line.hasPrefix("- ") || line.hasPrefix("* ") { flushParagraph(); blocks.append(.bullet(String(line.dropFirst(2)))); continue }
            if line.range(of: "^[0-9]+\\.\\s+", options: .regularExpression) != nil {
                flushParagraph()
                blocks.append(.ordered(line)); continue
            }
            paragraph.append(line)
        }
        if isCode { blocks.append(.code(code.joined(separator: "\n"), codeLanguage)) }
        flushParagraph()
        flushTable()
        return blocks
    }
}
