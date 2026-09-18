import SwiftUI
import Charts
import AppKit
import UniformTypeIdentifiers

struct LearnerProfile: Codable { var id: String; var name: String; var bio: String; var avatar: String }
struct AbilityDimension: Decodable { let name: String; let count: Int }
struct LanguageAbility: Decodable {
    let name: String; let evidenceCount: Int; let score: Int?; let status: String
    let githubBytes, githubRepositoryCount: Int
    private enum CodingKeys: String, CodingKey { case name, evidenceCount, score, status, githubBytes, githubRepositoryCount }
    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        name = try values.decode(String.self, forKey: .name)
        evidenceCount = try values.decode(Int.self, forKey: .evidenceCount)
        score = try values.decodeIfPresent(Int.self, forKey: .score)
        status = try values.decode(String.self, forKey: .status)
        githubBytes = try values.decodeIfPresent(Int.self, forKey: .githubBytes) ?? 0
        githubRepositoryCount = try values.decodeIfPresent(Int.self, forKey: .githubRepositoryCount) ?? 0
    }
}
struct LearnerAchievement: Decodable { let title: String; let unlocked: Bool; let current: Int?; let target: Int?; let detail: String?; let icon: String? }
struct LearningActivity: Decodable { let day: String; let count: Int }
struct GitHubLanguage: Decodable { let name: String; let bytes, repositories: Int }
struct GitHubSummary: Decodable {
    let login, refreshedAt, privacy: String
    let repositoryCount, totalContributions, commitCount, pullRequestCount, issueCount: Int
    let languages: [GitHubLanguage]
    let activity: [LearningActivity]
}
struct RadarAxis: Identifiable {
    let name: String; let assessmentScore: Int?; let githubSignal: Int
    var id: String { name }
}
struct LearningRecord: Decodable { let concept_id: String; let evidence_type: String; let note: String; let created_at: String }
struct LearnerSummary: Decodable {
    let profile: LearnerProfile
    let xp, level, conceptCount, evidenceCount: Int
    let dimensions: [AbilityDimension]
    let languages: [LanguageAbility]
    let github: GitHubSummary?
    let achievements: [LearnerAchievement]
    let activity: [LearningActivity]
    let recent: [LearningRecord]
    let storagePath: String
    let currentStreak, longestStreak, activeDays: Int
}

struct LearnerDashboard: View {
    @Environment(\.accessibilityReduceMotion) private var systemReduceMotion
    @AppStorage("trainer.motion.enabled") private var motionEnabled = true
    private var reduceMotion: Bool { systemReduceMotion || !motionEnabled }
    var onBack: () -> Void
    var onRecord: () -> Void
    @State private var summary: LearnerSummary?
    @StateObject private var github = GitHubConnectionModel()
    @State private var profile = LearnerProfile(id: "local", name: "学习者", bio: "", avatar: "🧑‍💻")
    @State private var message = ""
    @State private var busy = false
    @State private var editing = false
    @State private var showTasks = false
    @State private var showAIService = false
    @State private var showVSCode = false
    @State private var showSettings = false
    @State private var showGitHub = false
    @AppStorage("trainer.profile.cover") private var cover = ""
    @State private var period = "每日"
    private let icons = ["text.bubble", "book", "curlybraces", "ladybug", "arrow.triangle.branch"]

    private var githubStatusControl: some View {
        Menu {
            Button("检查 GitHub 登录状态") { github.restore() }
            if github.connected {
                Button("立即同步 GitHub 数据") { github.refresh() }.disabled(github.busy)
            } else {
                Button("连接 GitHub") { showGitHub = true }
            }
            Divider()
            Button("打开 GitHub 连接管理") { showGitHub = true }
        } label: {
            HStack(spacing: 7) {
                if github.busy { ProgressView().controlSize(.small) }
                else { Image(systemName: "point.3.connected.trianglepath.dotted") }
                Text(github.busy ? "同步中" : (github.connected ? "GitHub 已连接" : "GitHub 未连接"))
            }.font(.callout.weight(.semibold))
                .foregroundStyle(github.connected ? .teal : .secondary)
                .padding(.horizontal, 10).padding(.vertical, 6)
                .background(.thinMaterial, in: Capsule())
        }.menuStyle(.borderlessButton)
            .help(github.connected ? "GitHub 已授权；可立即同步活动和项目语言" : "检查或连接 GitHub")
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Button(action: onBack) { Label("返回课程", systemImage: "chevron.left") }.buttonStyle(.plain)
                Text("学习档案").font(.headline)
                Spacer()
                Button { showVSCode = true } label: { ConnectionStatus(compact: true) }.buttonStyle(.plain)
                githubStatusControl
                Button { showSettings = true } label: { Image(systemName: "gearshape").frame(width: 28, height: 28) }.buttonStyle(.plain).help("设置")
                Button { Task { await load(save: false) } } label: {
                    Image(systemName: "arrow.clockwise").frame(width: 28, height: 28)
                }.buttonStyle(.plain).disabled(busy).help("刷新档案").accessibilityLabel("刷新档案")
            }.padding(.horizontal, 20).padding(.vertical, 10).background(.ultraThinMaterial)
            Divider()
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    ProfileHero(profile: profile, cover: cover, edit: { editing.toggle() }, chooseCover: {
                        do { if let chosen = try CoverStorage.choose() { cover = chosen } }
                        catch { message = error.localizedDescription }
                    }, resetCover: { cover = "" })
                    if editing { profileEditor }
                    if !message.isEmpty { Label(message, systemImage: "info.circle").foregroundStyle(.secondary) }
                    if let summary { dashboard(summary) }
                    else if busy { ProgressView("正在加载学习档案…").frame(maxWidth: .infinity, minHeight: 220) }
                    else { ContentUnavailableView("档案暂不可用", systemImage: "wifi.exclamationmark", description: Text("请检查本地 Gateway，然后点击右上方刷新。")) }
                }.padding(28).frame(maxWidth: .infinity, alignment: .leading)
            }
        }.task {
            github.restore()
            await load(save: false)
        }
        .sheet(isPresented: $showTasks) { TaskCenter() }
        .sheet(isPresented: $showAIService) { AIServiceSettings() }
        .sheet(isPresented: $showVSCode) { VSCodePairing() }
        .sheet(isPresented: $showSettings) { TrainerSettings() }
        .sheet(isPresented: $showGitHub) {
            GitHubConnectionView(onInsightsSynced: { Task { await load(save: false) } })
                .frame(minWidth: 560, minHeight: 420).padding(24)
        }
        .onReceive(NotificationCenter.default.publisher(for: .trainerGitHubInsightsSynced)) { _ in
            Task { await load(save: false) }
        }
    }

    private var profileEditor: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Picker("头像", selection: $profile.avatar) {
                    if profile.avatar.hasPrefix("local-image:") { Text("自定义图片").tag(profile.avatar) }
                    ForEach(["🧑‍💻", "👩‍🚀", "🦊", "🐼", "🌱"], id: \.self) { Text($0).tag($0) }
                }.frame(width: 145)
                Button("上传图片") {
                    do { if let avatar = try AvatarStorage.choose() { profile.avatar = avatar; message = "头像预览已更新，点击保存资料后同步。" } }
                    catch { message = error.localizedDescription }
                }
                TextField("昵称", text: $profile.name)
            }
            TextField("简介与学习目标", text: $profile.bio, axis: .vertical).lineLimit(2...5)
            Button("保存资料") { Task { await load(save: true) } }.buttonStyle(.borderedProminent).disabled(busy)
        }.dashboardCard()
    }

    private func dashboard(_ data: LearnerSummary) -> some View {
        VStack(alignment: .leading, spacing: 24) {
            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 12), count: 4), spacing: 12) {
                summaryMetric("学习等级", "Lv.\(data.level)", "本级 \(data.xp % 100) / 100 XP", "再获 \(100 - data.xp % 100) XP 升级\n累计 \(data.xp) XP", "sparkles", progress: Double(data.xp % 100) / 100)
                summaryMetric("学习足迹", "\(data.conceptCount) 个学习点", "累计提交 \(data.evidenceCount) 条记录", "涉及 \(data.languages.count) 种语言\n首次记录学习点 +10 XP", "books.vertical")
                summaryMetric("连续学习", "\(data.currentStreak) 天", "近 7 天活跃 \(data.activity.suffix(7).filter { $0.count > 0 }.count) 天", "今日提交 \(data.activity.last?.count ?? 0) 条\n以提交记录为准，不计在线时长", "flame")
                summaryMetric("最佳连续", "\(data.longestStreak) 天", "累计活跃 \(data.activeDays) 天", "近 7 天提交 \(data.activity.suffix(7).reduce(0) { $0 + $1.count }) 条\n按本机日期统计连续天数", "calendar.badge.checkmark")
            }
            activityPanel(data)
            if let github = data.github { githubActivityPanel(github) }
            else { githubNotSyncedPanel }
            VStack(alignment: .leading, spacing: 16) {
                Label("练习记录分布", systemImage: "chart.pie").font(.headline)
                Text("记录入口：在课程右侧回答当前教练问题，再点击「记录理解证据」。凭据类型由问题自动确定，不需要手动选择。")
                    .font(.callout).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                HStack(spacing: 24) {
                    metric("近 7 天", "\(data.activity.suffix(7).reduce(0) { $0 + $1.count }) 条", "已提交的学习凭据", "calendar")
                    metric("语言探索", "\(data.languages.count) 种", "有明确语言记录", "curlybraces")
                    metric("已解锁成就", "\(data.achievements.filter(\.unlocked).count) 项", "按学习足迹累计", "medal")
                }
                ForEach(Array(data.dimensions.enumerated()), id: \.element.name) { index, item in
                    VStack(spacing: 8) {
                        HStack {
                            Label(item.name, systemImage: icons[index % icons.count])
                            Spacer()
                            Text("\(item.count) 条 · \(data.evidenceCount == 0 ? 0 : Int(Double(item.count) / Double(data.evidenceCount) * 100))%").monospacedDigit().foregroundStyle(.secondary)
                            Button("去学习") { onRecord() }
                                .help("返回当前课程；凭据类型由当前问题自动确定，不会自动提交记录。")
                        }.font(.callout)
                        FluidBar(value: Double(item.count) / Double(max(1, data.evidenceCount)))
                    }.padding(.vertical, 5)
                }
                Text("统计口径：按教练问题自动确定的凭据类型计数，占比以全部凭据为分母。不是 IDE 阅读时长或代码行数；记录仍由你主动提交，重复提交会增加条数但不重复增加 XP。")
                    .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }.dashboardCard()
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .top, spacing: 20) {
                    radarPanel(data).frame(minWidth: 350)
                    dimensionTable(data).frame(minWidth: 300)
                }
                VStack(spacing: 20) { radarPanel(data); dimensionTable(data) }
            }
            AchievementGallery(items: data.achievements).dashboardCard()
            VStack(alignment: .leading, spacing: 14) {
                Label("最近学习凭据", systemImage: "list.bullet.rectangle").font(.headline)
                if data.recent.isEmpty { Text("还没有记录。在课程中提交理解、代码或调试观察后，这里会显示学习足迹。").foregroundStyle(.secondary) }
                ForEach(Array(data.recent.enumerated()), id: \.offset) { _, record in
                    HStack(alignment: .top, spacing: 16) {
                        Image(systemName: "checkmark.circle").foregroundStyle(.teal)
                        VStack(alignment: .leading, spacing: 5) {
                            Text(record.note).textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
                            Text(record.concept_id).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                        }
                        Spacer(minLength: 0)
                        Text(String(record.created_at.prefix(10))).font(.caption).foregroundStyle(.secondary)
                    }
                    Divider()
                }
            }.dashboardCard()
            VStack(alignment: .leading, spacing: 8) {
                Label("本机数据与隐私", systemImage: "externaldrive").font(.headline)
                Text(data.storagePath).textSelection(.enabled).font(.callout.monospaced())
                Button("导出本地备份 ZIP") { Task { await exportBackup() } }.disabled(busy)
                Button("从备份恢复") { Task { await restoreBackup() } }.disabled(busy)
                Text("删除 .app 通常不影响此目录；清理软件、删除用户数据或更换电脑仍可能丢失数据。请将备份另存到外置盘或自己的备份空间。")
                    .font(.caption).foregroundStyle(.secondary)
                Text("资料与凭据存储在本机 SQLite；课程与版本独立保存。当前不含云登录和同步。等级表示积累，图表表示练习分布，不代表已验证掌握。")
                    .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }.dashboardCard()
        }
    }

    private func metric(_ title: String, _ value: String, _ detail: String, _ icon: String) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(title, systemImage: icon).font(.callout).foregroundStyle(.secondary)
            Text(value).font(.system(size: 27, weight: .semibold, design: .rounded)).monospacedDigit()
            Text(detail).font(.caption).foregroundStyle(.secondary)
        }.frame(maxWidth: .infinity, alignment: .leading).dashboardCard()
    }

    private func summaryMetric(_ title: String, _ value: String, _ detail: String, _ footer: String, _ icon: String, progress: Double? = nil) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(title, systemImage: icon).font(.callout).foregroundStyle(.secondary)
            Text(value).font(.system(size: 25, weight: .semibold, design: .rounded)).monospacedDigit().minimumScaleFactor(0.7).lineLimit(1)
            Text(detail).font(.caption).foregroundStyle(.secondary)
            Spacer(minLength: 4)
            if let progress { FluidBar(value: progress) } else { Divider() }
            Text(footer).font(.caption).foregroundStyle(.secondary).lineSpacing(4).fixedSize(horizontal: false, vertical: true)
        }.frame(height: 145, alignment: .topLeading).dashboardCard()
    }

    private func activityPanel(_ data: LearnerSummary) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Label("学习活动", systemImage: "calendar").font(.headline)
                Spacer()
                Picker("统计周期", selection: $period) { ForEach(["每日", "每周", "累计"], id: \.self) { Text($0) } }.pickerStyle(.segmented).frame(width: 210)
            }
            if period == "每日" {
                ActivityHeatmap(days: data.activity)
                HStack {
                    Text("过去 365 天 · 凭据数量"); Spacer(); Text("少")
                    ForEach(0..<5) { index in RoundedRectangle(cornerRadius: 2).fill(Color.indigo.opacity(0.12 + Double(index) * 0.2)).frame(width: 11, height: 11) }
                    Text("多")
                }.font(.caption).foregroundStyle(.secondary)
            } else {
                if data.activity.allSatisfy({ $0.count == 0 }) {
                    ContentUnavailableView("这段时间还没有学习记录", systemImage: "chart.bar.xaxis", description: Text("在课程中保存学习凭据后，这里会显示\(period == "每周" ? "每周活动" : "累计趋势")。零记录不是加载失败。"))
                        .frame(maxWidth: .infinity, minHeight: 170, alignment: .center)
                } else {
                Chart(chartActivity(data), id: \.day) { item in
                    BarMark(x: .value("日期", item.day), y: .value("凭据", item.count)).foregroundStyle(.indigo.gradient)
                }.chartXAxis { AxisMarks(values: .automatic(desiredCount: 4)) }.frame(height: 170)
                    .animation(reduceMotion ? nil : .smooth(duration: 0.7), value: period)
                    .fluidGlow()
                }
                Text(period == "每周" ? "最近 365 天按连续 7 日分组，末组可能不足 7 日。" : "最近 365 天内的累计凭据，不包含更早历史。")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }.dashboardCard()
    }

    private func chartActivity(_ data: LearnerSummary) -> [LearningActivity] {
        if period == "累计" {
            var total = 0
            return data.activity.map { total += $0.count; return LearningActivity(day: $0.day, count: total) }
        }
        return stride(from: 0, to: data.activity.count, by: 7).map { start in
            LearningActivity(day: data.activity[start].day, count: data.activity[start..<min(start + 7, data.activity.count)].reduce(0) { $0 + $1.count })
        }
    }

    private func radarPanel(_ data: LearnerSummary) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("语言能力与 GitHub 项目信号", systemImage: "pentagon").font(.headline)
            if data.languages.isEmpty {
                ContentUnavailableView("尚无语言数据", systemImage: "curlybraces", description: Text("保存带有明确课程语言的学习凭据，或在设置中连接 GitHub 后刷新项目语言。"))
                    .frame(height: 230)
            } else {
                let axes = radarAxes(data.languages)
                ScrollView([.horizontal, .vertical]) {
                    AbilityRadar(axes: axes)
                        .frame(width: CGFloat(max(330, axes.count * 42)), height: CGFloat(max(285, axes.count * 42)))
                        .fluidGlow()
                }.frame(height: 320)
            }
            HStack(spacing: 14) {
                Label("实线 · 课堂 AI 评估", systemImage: "chart.line.uptrend.xyaxis").foregroundStyle(.cyan)
                Label("虚线 · GitHub 项目语言信号", systemImage: "point.3.connected.trianglepath.dotted").foregroundStyle(.orange)
            }.font(.caption)
            ForEach(data.languages, id: \.name) { language in
                Text("\(language.name) · \(language.score.map { "课堂 \($0) / 100" } ?? "课堂待评估") · \(language.evidenceCount) 条凭据")
                    .font(.caption).foregroundStyle(.secondary)
                    .help("\(language.name)：\(language.evidenceCount) 条已提交记录。\(language.status)。课堂分数来自 AI 评估；GitHub 信号只表示该语言出现在已同步项目中。")
            }
            Text("实线刻度 0–100 是课堂凭据的 AI 评估均值；虚线按 GitHub 仓库语言字节占比归一化，仅表示项目接触面。两者不会相互换算，也不等同于整体掌握度。雷达最多展示信号最强的 8 种语言，完整清单见右侧。")
                .font(.caption).foregroundStyle(.secondary)
        }.frame(maxWidth: .infinity).dashboardCard()
    }

    private func radarAxes(_ languages: [LanguageAbility]) -> [RadarAxis] {
        let maxBytes = max(1, languages.map(\.githubBytes).max() ?? 0)
        return languages.map { language in
            let bytes = language.githubBytes
            let signal = bytes == 0 ? 0 : max(10, min(100, Int((Double(bytes) / Double(maxBytes)).squareRoot() * 100)))
            return RadarAxis(name: language.name, assessmentScore: language.score, githubSignal: signal)
        }.sorted { max($0.assessmentScore ?? 0, $0.githubSignal) > max($1.assessmentScore ?? 0, $1.githubSignal) }
            .prefix(8).map { $0 }
    }

    private func dimensionTable(_ data: LearnerSummary) -> some View {
        VStack(alignment: .leading, spacing: 18) {
            Label("语言能力档案", systemImage: "curlybraces").font(.headline)
            ForEach(data.languages, id: \.name) { language in
                VStack(spacing: 8) {
                    HStack {
                        Text(language.name); Spacer()
                        Text(language.status).foregroundStyle(.secondary)
                    }
                    Text("\(language.evidenceCount) 条相关学习记录").font(.caption).foregroundStyle(.secondary).frame(maxWidth: .infinity, alignment: .leading)
                    if language.githubBytes > 0 {
                        Text("GitHub：\(language.githubRepositoryCount) 个项目 · \(ByteCountFormatter.string(fromByteCount: Int64(language.githubBytes), countStyle: .file))")
                            .font(.caption).foregroundStyle(.orange).frame(maxWidth: .infinity, alignment: .leading)
                    }
                    if let score = language.score { FluidBar(value: Double(score) / 100) }
                    Divider()
                }.font(.callout)
            }
            Text("课堂语言取自课程凭据；GitHub 语言来自可读取仓库的代码字节聚合。框架、源码和仓库名不会被同步。").font(.caption).foregroundStyle(.secondary)
        }.frame(maxWidth: .infinity).dashboardCard()
    }

    private func githubActivityPanel(_ github: GitHubSummary) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Label("GitHub 活动", systemImage: "point.3.connected.trianglepath.dotted").font(.headline)
                Spacer()
                Text("@\(github.login)").foregroundStyle(.secondary)
                Button("刷新 GitHub") { self.github.refresh() }.buttonStyle(.bordered).disabled(self.github.busy)
                Button("管理") { showGitHub = true }.buttonStyle(.bordered)
            }
            HStack(spacing: 24) {
                metric("贡献", "\(github.totalContributions)", "近一年贡献口径", "calendar.badge.clock")
                metric("提交", "\(github.commitCount)", "GitHub 统计", "arrow.triangle.branch")
                metric("项目语言", "\(github.languages.count) 种", "已分析 \(github.repositoryCount) 个项目", "curlybraces")
            }
            GitHubContributionHeatmap(days: github.activity)
            Text("\(github.privacy) 数据上次同步：\(String(github.refreshedAt.prefix(10)))。GitHub 活动不是学习时长、课程完成度或能力评分。")
                .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
        }.dashboardCard()
    }

    private var githubNotSyncedPanel: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Label("GitHub 活动", systemImage: "point.3.connected.trianglepath.dotted").font(.headline)
                Spacer()
                Text(github.connected ? "已连接 · 尚未同步" : "未连接")
                    .font(.caption.weight(.semibold)).foregroundStyle(github.connected ? .orange : .secondary)
            }
            Text(github.connected
                 ? "GitHub 登录有效，但尚未把活动和项目语言写入此档案。点击下方按钮即可同步。"
                 : "连接 GitHub 后，这里会展示近一年贡献热力图，并将仓库语言作为独立的项目语言信号加入雷达图。")
                .foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            HStack {
                Button(github.connected ? "同步 GitHub 活动与项目语言" : "连接 GitHub") {
                    if github.connected { github.refresh() } else { showGitHub = true }
                }.buttonStyle(.borderedProminent).disabled(github.busy)
                Button("连接管理") { showGitHub = true }.buttonStyle(.bordered)
            }
            if github.busy { HStack { ProgressView().controlSize(.small); Text("正在读取 GitHub 活动与项目语言…") }.font(.caption).foregroundStyle(.secondary) }
            if let message = github.message { Text(message).font(.caption).foregroundStyle(.secondary) }
            Text("仅请求 read:user：同步公开仓库的语言字节聚合和近一年贡献日历；不会同步源码、仓库名、文件路径或提交内容。")
                .font(.caption).foregroundStyle(.secondary)
        }.dashboardCard()
    }

    @MainActor private func exportBackup() async {
        let panel = NSSavePanel()
        panel.allowedContentTypes = [.zip]
        panel.nameFieldStringValue = "Trainer-backup.zip"
        guard panel.runModal() == .OK, let destination = panel.url else { return }
        // Do not overwrite an existing export, even after a save-panel confirmation.
        guard !FileManager.default.fileExists(atPath: destination.path) else { message = "该文件已存在，请用新名称保存。"; return }
        busy = true
        defer { busy = false }
        do {
            var request = URLRequest(url: URL(string: "http://127.0.0.1:8787/v1/backups")!)
            request.httpMethod = "POST"
            request.timeoutInterval = 180
            request.setValue(LocalGatewaySession.token, forHTTPHeaderField: "X-Trainer-Session")
            let (data, response) = try await URLSession.shared.data(for: request)
            guard (response as? HTTPURLResponse)?.statusCode == 201 else { throw URLError(.badServerResponse) }
            struct Export: Decodable { let path: String }
            let result = try JSONDecoder().decode(Export.self, from: data)
            try FileManager.default.copyItem(at: URL(fileURLWithPath: result.path), to: destination)
            message = "备份已导出：\(destination.lastPathComponent)。包含个人记录与项目资料，请妥善保管。"
            NSWorkspace.shared.activateFileViewerSelecting([destination])
        } catch { message = "备份未导出：\(error.localizedDescription)" }
    }

    private func restoreBackup() async {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.zip]
        panel.allowsMultipleSelection = false
        guard panel.runModal() == .OK, let source = panel.url else { return }
        busy = true
        defer { busy = false }
        do {
            func request(_ action: String, confirmed: Bool = false) async throws -> [String: Any] {
                var request = URLRequest(url: URL(string: "http://127.0.0.1:8787/v1/backups/\(action)")!)
                request.httpMethod = "POST"; request.timeoutInterval = 180
                request.setValue(LocalGatewaySession.token, forHTTPHeaderField: "X-Trainer-Session")
                request.httpBody = try JSONSerialization.data(withJSONObject: ["path": source.path, "confirmed": confirmed])
                let (data, response) = try await URLSession.shared.data(for: request)
                let result = (try JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
                guard (response as? HTTPURLResponse)?.statusCode == 200 else {
                    throw NSError(domain: "Trainer", code: 1, userInfo: [NSLocalizedDescriptionKey: result["error"] as? String ?? "恢复请求失败"])
                }
                return result
            }
            let preview = try await request("inspect")
            let alert = NSAlert()
            alert.messageText = "恢复这份 Trainer 备份？"
            alert.informativeText = "备份包含 \(preview["fileCount"] ?? 0) 项。当前资料与课程将保留到恢复历史目录，然后切换到备份内容。API 密钥不受影响。"
            alert.addButton(withTitle: "恢复"); alert.addButton(withTitle: "取消")
            guard alert.runModal() == .alertFirstButtonReturn else { return }
            let result = try await request("restore", confirmed: true)
            await load(save: false)
            message = "恢复完成。原数据保留于：\(result["previousDataPath"] ?? "")。请重新选择课程。"
        } catch { message = "未恢复：\(error.localizedDescription)" }
    }

    private func load(save: Bool) async {
        busy = true
        defer { busy = false }
        do {
            var request = URLRequest(url: URL(string: "http://127.0.0.1:8787/v1/me")!)
            request.timeoutInterval = 15
            if save {
                request.httpMethod = "POST"
                request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                request.setValue(LocalGatewaySession.token, forHTTPHeaderField: "X-Trainer-Session")
                request.httpBody = try JSONEncoder().encode(profile)
            }
            let (data, response) = try await URLSession.shared.data(for: request)
            guard (response as? HTTPURLResponse)?.statusCode == 200 else { throw URLError(.badServerResponse) }
            let value = try JSONDecoder().decode(LearnerSummary.self, from: data)
            summary = value; profile = value.profile
            NotificationCenter.default.post(name: .trainerProfileChanged, object: value.profile)
            message = save ? "资料已保存到本机。" : ""
            if save { editing = false }
        } catch { message = "无法读取档案：\(error.localizedDescription)" }
    }
}

private extension View {
    func dashboardCard() -> some View {
        frame(maxWidth: .infinity, alignment: .leading).padding(20).background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 18))
            .overlay(RoundedRectangle(cornerRadius: 18).stroke(.white.opacity(0.08)))
    }
}

struct AbilityRadar: View {
    let axes: [RadarAxis]
    var body: some View {
        Canvas { context, size in
            guard !axes.isEmpty else { return }
            let center = CGPoint(x: size.width / 2, y: size.height / 2)
            let radius = min(size.width / 2 - 65, size.height / 2 - 35)
            func point(_ index: Int, _ scale: Double) -> CGPoint {
                let angle = Double(index) * 2 * .pi / Double(axes.count) - .pi / 2
                return CGPoint(x: center.x + cos(angle) * radius * scale, y: center.y + sin(angle) * radius * scale)
            }
            func polygon(_ values: [Double]) -> Path {
                Path { path in
                    path.move(to: point(0, values[0]))
                    for index in 1..<values.count { path.addLine(to: point(index, values[index])) }
                    path.closeSubpath()
                }
            }
            for ring in 1...5 {
                let r = radius * Double(ring) / 5
                let grid = axes.count < 3 ? Path(ellipseIn: CGRect(x: center.x - r, y: center.y - r, width: r * 2, height: r * 2)) : polygon(Array(repeating: Double(ring) / 5, count: axes.count))
                context.stroke(grid, with: .color(.cyan.opacity(0.22)), lineWidth: 1)
            }
            for index in axes.indices {
                var axis = Path(); axis.move(to: center); axis.addLine(to: point(index, 1))
                context.stroke(axis, with: .color(.white.opacity(0.1)))
                context.draw(Text(axes[index].name).font(.caption).foregroundColor(.secondary), at: point(index, 1.3))
            }
            let classroom = axes.map { Double($0.assessmentScore ?? 0) / 100 }
            if classroom.contains(where: { $0 > 0 }) {
                let shape = polygon(classroom)
                context.fill(shape, with: .color(.indigo.opacity(0.28)))
                context.stroke(shape, with: .color(.cyan), lineWidth: 3)
            }
            let github = axes.map { Double($0.githubSignal) / 100 }
            if github.contains(where: { $0 > 0 }) {
                context.stroke(polygon(github), with: .color(.orange.opacity(0.9)), style: StrokeStyle(lineWidth: 2, dash: [6, 4]))
            }
            for index in axes.indices {
                if axes[index].assessmentScore != nil {
                    let p = point(index, Double(axes[index].assessmentScore ?? 0) / 100)
                    context.fill(Path(ellipseIn: CGRect(x: p.x - 3, y: p.y - 3, width: 6, height: 6)), with: .color(.teal))
                }
            }
        }.accessibilityLabel("语言能力与 GitHub 项目信号雷达：" + axes.map(\.name).joined(separator: "，"))
    }
}

struct ActivityHeatmap: View {
    let days: [LearningActivity]
    @State private var hovered: LearningActivity?
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
        GeometryReader { geometry in
            let columns = max(1, Int(ceil(Double(days.count) / 7)))
            let cell = max(3, min(14, (geometry.size.width - Double(columns - 1) * 3) / Double(columns)))
            HStack(alignment: .top, spacing: 3) {
                ForEach(0..<columns, id: \.self) { column in
                    VStack(spacing: 3) {
                        ForEach(0..<7) { row in
                            let index = column * 7 + row
                            if index < days.count {
                                let day = days[index]
                                ActivityCell(count: day.count, selected: hovered?.day == day.day)
                                    .frame(width: cell, height: cell)
                                    .onHover { inside in hovered = inside ? day : nil }
                                    .help("\(day.day)：\(day.count) 条凭据")
                                    .accessibilityLabel("\(day.day)：\(day.count) 条凭据")
                            }
                        }
                    }
                }
            }.frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)
        }.frame(height: 117)
        Text(hovered.map { "\($0.day) · \($0.count) 条学习凭据 · \($0.count == 0 ? "当天没有提交记录" : "已记录学习活动；不代表学习时长")" } ?? "悬浮日期方格查看当天记录；亮色表示有学习活动。")
            .font(.caption).foregroundStyle(.secondary).frame(height: 20)
        }
    }
}

struct GitHubContributionHeatmap: View {
    let days: [LearningActivity]
    @State private var hovered: LearningActivity?
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if days.isEmpty {
                ContentUnavailableView("尚无 GitHub 活动", systemImage: "calendar.badge.exclamationmark", description: Text("在设置中刷新 GitHub 后，近一年贡献日历会显示在这里。"))
                    .frame(maxWidth: .infinity, minHeight: 110)
            } else {
                GeometryReader { geometry in
                    let columns = max(1, Int(ceil(Double(days.count) / 7)))
                    let cell = max(3, min(14, (geometry.size.width - Double(columns - 1) * 3) / Double(columns)))
                    HStack(alignment: .top, spacing: 3) {
                        ForEach(0..<columns, id: \.self) { column in
                            VStack(spacing: 3) {
                                ForEach(0..<7) { row in
                                    let index = column * 7 + row
                                    if index < days.count {
                                        let day = days[index]
                                        GitHubActivityCell(day: day, size: cell, selected: hovered?.day == day.day)
                                            .onHover { inside in hovered = inside ? day : nil }
                                    }
                                }
                            }
                        }
                    }.frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)
                }.frame(height: 117)
                Text(hovered.map { "\($0.day) · \($0.count) 项 GitHub 贡献" } ?? "悬浮日期方格查看贡献数；该日历包含提交、议题、PR 等。")
                    .font(.caption).foregroundStyle(.secondary).frame(height: 20)
            }
        }
    }
}

private struct GitHubActivityCell: View {
    let day: LearningActivity
    let size: Double
    let selected: Bool
    var body: some View {
        let opacity = day.count == 0 ? 0.08 : min(0.95, 0.22 + Double(day.count) * 0.08)
        RoundedRectangle(cornerRadius: 3)
            .fill(Color.green.opacity(opacity))
            .frame(width: size, height: size)
            .overlay(RoundedRectangle(cornerRadius: 3).stroke(selected ? .white : .clear, lineWidth: 1))
            .help("\(day.day)：\(day.count) 项 GitHub 贡献")
            .accessibilityLabel("\(day.day)，\(day.count) 项 GitHub 贡献")
    }
}

private struct ActivityCell: View {
    let count: Int
    let selected: Bool
    @Environment(\.accessibilityReduceMotion) private var systemReduceMotion
    @AppStorage("trainer.motion.enabled") private var motionEnabled = true
    private var reduceMotion: Bool { systemReduceMotion || !motionEnabled }
    var body: some View {
        TimelineView(.animation(minimumInterval: 1 / 20, paused: reduceMotion || count == 0)) { timeline in
            let pulse = reduceMotion ? 0.5 : (sin(timeline.date.timeIntervalSinceReferenceDate * 2) + 1) / 2
            RoundedRectangle(cornerRadius: 3)
                .fill(count == 0 ? Color.white.opacity(0.06) : Color.indigo.opacity(min(1, 0.6 + Double(count) * 0.1)))
                .overlay(RoundedRectangle(cornerRadius: 3).stroke(selected ? Color.white : Color.cyan.opacity(count > 0 ? 0.3 + pulse * 0.6 : 0), lineWidth: 1))
                .shadow(color: .cyan.opacity(count > 0 ? 0.2 + pulse * 0.45 : 0), radius: selected ? 7 : 4)
        }
    }
}
