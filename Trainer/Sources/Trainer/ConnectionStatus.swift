import SwiftUI

/// Heartbeat status is distinct from stored pairing; no source collection occurs here.
@MainActor final class ConnectionMonitor: ObservableObject {
    static let shared = ConnectionMonitor()
    struct Snapshot: Decodable { let paired: Int; let online: Int; let linked: Int }
    @Published var snapshot: Snapshot?
    @Published var failed = false
    private var loop: Task<Void, Never>?
    func start() {
        guard loop == nil else { return }
        loop = Task {
            while !Task.isCancelled {
                await refresh()
                do { try await Task.sleep(for: .seconds(5)) } catch { return }
            }
        }
    }
    private func refresh() async {
        var request = URLRequest(url: URL(string: "http://127.0.0.1:8787/v2/pairings/connection-status")!)
        request.timeoutInterval = 4
        request.setValue(LocalGatewaySession.token, forHTTPHeaderField: "X-Trainer-Session")
        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            guard (response as? HTTPURLResponse)?.statusCode == 200 else { throw URLError(.badServerResponse) }
            snapshot = try JSONDecoder().decode(Snapshot.self, from: data)
            failed = false
        } catch { if !Task.isCancelled { failed = true } }
    }
}

struct ConnectionStatus: View {
    var compact = false
    @Environment(\.accessibilityReduceMotion) private var systemReduceMotion
    @AppStorage("trainer.motion.enabled") private var motionEnabled = true
    private var reduceMotion: Bool { systemReduceMotion || !motionEnabled }
    @Environment(\.scenePhase) private var scenePhase
    @ObservedObject private var monitor = ConnectionMonitor.shared
    private var snapshot: ConnectionMonitor.Snapshot? { monitor.snapshot }
    private var failed: Bool { monitor.failed }
    private var title: String {
        if failed { return "连接状态不可用" }
        guard let value = snapshot else { return "正在检查连接" }
        if value.online > 0 { return "VS Code 在线 · \(value.online)" }
        return value.paired > 0 ? "已配对 · 等待 VS Code" : "VS Code 未配对"
    }
    private var tint: Color { failed ? .orange : snapshot == nil ? .purple : (snapshot?.online ?? 0) > 0 ? .cyan : .gray }
    private var flowing: Bool { !failed && (snapshot == nil || (snapshot?.online ?? 0) > 0) }
    var body: some View {
        HStack(spacing: 10) {
            TimelineView(.animation(minimumInterval: 1 / 20, paused: reduceMotion || !flowing || scenePhase != .active)) { time in
                let phase = reduceMotion || !flowing ? 0 : time.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 2.5) / 2.5
                ZStack {
                    if flowing {
                        Circle().fill(tint.opacity(0.22)).frame(width: 19, height: 19)
                            .scaleEffect(reduceMotion ? 1 : 1 + 0.25 * sin(phase * .pi * 2))
                            .blur(radius: 3)
                    }
                    Circle()
                    .fill(tint)
                    .frame(width: 8, height: 8)
                    .opacity(flowing ? 0.8 + 0.2 * sin(phase * .pi * 2) : 0.65)
                    .shadow(color: tint.opacity(flowing ? 0.8 : 0), radius: flowing ? 5 + 3 * sin(phase * .pi * 2) : 0)
                }.frame(width: 22, height: 24)
            }.accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 5) {
                Text(title).font(compact ? .caption.weight(.semibold) : .headline)
                if !compact {
                    Text(failed ? "无法读取 Gateway 状态，将自动重试。" : "\(snapshot?.paired ?? 0) 个有效配对 · \(snapshot?.linked ?? 0) 条目录关联")
                        .font(.caption).foregroundStyle(.secondary)
                    Text("15 秒心跳 · 45 秒无回应视为离线。目录关联不代表源码已授权。")
                        .font(.caption2).foregroundStyle(.secondary)
                }
            }
            if !compact { Spacer(minLength: 0) }
        }
        .padding(.vertical, compact ? 6 : 10)
        .contentShape(Rectangle())
        .animation(reduceMotion ? nil : .easeInOut(duration: 0.4), value: title)
        .help("点击连接管理可配对或撤销目录关联；在线状态依据最近心跳。")
        .task { monitor.start() }
    }
}
