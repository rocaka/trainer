import SwiftUI
import AppKit

struct TeachingCodeBlock: View {
    @AppStorage("trainer.code.size") private var codeSize = 14.0
    let code: String
    var language: String = "code"
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text(language).font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                Spacer()
                Button("复制代码") { NSPasteboard.general.clearContents(); NSPasteboard.general.setString(code, forType: .string) }
                    .buttonStyle(.borderless).font(.caption)
            }.padding(10)
            Divider()
            ScrollView(.horizontal) {
                Text(highlighted).font(.system(size: codeSize, design: .monospaced))
                    .textSelection(.enabled).lineSpacing(5).padding(14)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.black.opacity(0.22), in: RoundedRectangle(cornerRadius: 10))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(.white.opacity(0.10)))
    }

    // Lexical highlighting only; never executes or modifies the source.
    private var highlighted: AttributedString {
        let value = NSMutableAttributedString(string: code, attributes: [.foregroundColor: NSColor.labelColor])
let pattern = #"(?m)(//[^\n]*|[#][^\n]*|/\*[\s\S]*?\*/)|("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`[^`]*`)|\b(func|function|def|class|struct|enum|interface|package|import|from|return|if|else|for|while|switch|case|break|continue|let|var|const|val|fn|pub|use|impl|async|await|try|catch|throw|throws|defer|go|chan|select|range|type|map|public|private|static|void|int|string|bool|byte|float|double|nil|null|None|True|False|true|false)\b|\b([0-9]+(?:\.[0-9]+)?)\b"#
        if let regex = try? NSRegularExpression(pattern: pattern) {
            for match in regex.matches(in: code, range: NSRange(code.startIndex..., in: code)) {
                let color: NSColor = match.range(at: 1).location != NSNotFound ? .systemGray : match.range(at: 2).location != NSNotFound ? .systemGreen : match.range(at: 3).location != NSNotFound ? .systemPurple : .systemOrange
                value.addAttribute(.foregroundColor, value: color, range: match.range)
            }
        }
        return AttributedString(value)
    }
}
