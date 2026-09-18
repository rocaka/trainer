import SwiftUI

/// Shared, bounded motion. Reduced Motion keeps the same truthful values without loops.
struct FluidProgressStyle: ProgressViewStyle {
    @Environment(\.accessibilityReduceMotion) private var systemReduceMotion
    @AppStorage("trainer.motion.enabled") private var motionEnabled = true
    private var reduceMotion: Bool { systemReduceMotion || !motionEnabled }
    func makeBody(configuration: Configuration) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            if let fraction = configuration.fractionCompleted {
                FluidBar(value: fraction)
            } else {
                HStack(spacing: 9) {
                    TimelineView(.animation(minimumInterval: 1 / 24, paused: reduceMotion)) { timeline in
                        let phase = reduceMotion ? 0 : timeline.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 1.6) / 1.6
                        Circle().trim(from: 0.08, to: 0.82)
                            .stroke(AngularGradient(colors: [.cyan.opacity(0.12), .indigo, .cyan], center: .center), style: StrokeStyle(lineWidth: 2.5, lineCap: .round))
                            .rotationEffect(.degrees(phase * 360)).frame(width: 17, height: 17)
                            .shadow(color: .cyan.opacity(0.25), radius: 4)
                    }.frame(width: 20, height: 20).accessibilityHidden(true)
                    configuration.label
                }
            }
            if configuration.fractionCompleted != nil { configuration.label }
            configuration.currentValueLabel
        }
    }
}

struct FluidBar: View {
    var value: Double
    @Environment(\.accessibilityReduceMotion) private var systemReduceMotion
    @AppStorage("trainer.motion.enabled") private var motionEnabled = true
    private var reduceMotion: Bool { systemReduceMotion || !motionEnabled }
    private var amount: Double { value.isFinite ? min(1, max(0, value)) : 0 }
    var body: some View {
        GeometryReader { geometry in
            ZStack(alignment: .leading) {
                Capsule().fill(.white.opacity(0.075))
                Capsule().fill(LinearGradient(colors: [.indigo, .purple, .cyan], startPoint: .leading, endPoint: .trailing))
                    .overlay {
                        TimelineView(.animation(minimumInterval: 1 / 24, paused: reduceMotion || amount == 0)) { timeline in
                            let phase = reduceMotion ? 0.5 : timeline.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 3) / 3
                            LinearGradient(colors: [.clear, .white.opacity(0.5), .clear], startPoint: .leading, endPoint: .trailing)
                                .frame(width: max(20, geometry.size.width * 0.16))
                                .offset(x: (phase - 0.5) * (geometry.size.width + 60))
                        }
                    }.clipShape(Capsule())
                    .frame(width: geometry.size.width * amount)
                    .shadow(color: .indigo.opacity(amount > 0 ? 0.35 : 0), radius: 5)
            }.animation(reduceMotion ? nil : .smooth(duration: 0.7), value: amount)
        }.frame(height: 8)
        .accessibilityLabel("进度").accessibilityValue("\(Int(amount * 100))%")
    }
}

private struct FluidGlow: ViewModifier {
    @Environment(\.accessibilityReduceMotion) private var systemReduceMotion
    @AppStorage("trainer.motion.enabled") private var motionEnabled = true
    private var reduceMotion: Bool { systemReduceMotion || !motionEnabled }
    func body(content: Content) -> some View {
        content.overlay {
            if !reduceMotion {
                TimelineView(.animation(minimumInterval: 1 / 20)) { timeline in
                    let phase = timeline.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 5) / 5
                    GeometryReader { geometry in
                        LinearGradient(colors: [.clear, .cyan.opacity(0.65), .white.opacity(0.45), .clear], startPoint: .leading, endPoint: .trailing)
                            .frame(width: geometry.size.width * 0.25)
                            .offset(x: geometry.size.width * (phase * 1.5 - 0.25))
                    }
                }.mask(content).allowsHitTesting(false).accessibilityHidden(true)
            }
        }
    }
}

extension View {
    func fluidGlow() -> some View { modifier(FluidGlow()) }
}
