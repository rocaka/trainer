import SwiftUI
import AppKit
import UniformTypeIdentifiers
import ImageIO

enum CoverStorage {
    static var directory: URL { FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("Trainer/covers") }
    static func image(_ id: String) -> NSImage? {
        guard let uuid = UUID(uuidString: id) else { return nil }
        return NSImage(contentsOf: directory.appendingPathComponent(uuid.uuidString + ".jpg"))
    }
    @MainActor static func choose() throws -> String? {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.png, .jpeg, .heic]
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = false
        panel.message = "选择个人封面（不超过 20 MB），仅保存在本机，不发送给 AI。"
        guard panel.runModal() == .OK, let url = panel.url else { return nil }
        let access = url.startAccessingSecurityScopedResource()
        defer { if access { url.stopAccessingSecurityScopedResource() } }
        guard (try url.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? Int.max) <= 20_000_000,
              let source = CGImageSourceCreateWithURL(url as CFURL, nil),
              let thumbnail = CGImageSourceCreateThumbnailAtIndex(source, 0, [kCGImageSourceCreateThumbnailFromImageAlways: true, kCGImageSourceThumbnailMaxPixelSize: 2000, kCGImageSourceCreateThumbnailWithTransform: true] as CFDictionary),
              let data = NSBitmapImageRep(cgImage: thumbnail).representation(using: .jpeg, properties: [.compressionFactor: 0.85]) else {
            throw NSError(domain: "TrainerCover", code: 1, userInfo: [NSLocalizedDescriptionKey: "请选择不超过 20 MB 的有效图片。"])
        }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let id = UUID().uuidString
        try data.write(to: directory.appendingPathComponent(id + ".jpg"), options: .atomic)
        return id
    }
}

/// Code-native aurora artwork; no downloaded asset or AI service required.
struct ProfileCover: View {
    var reference: String
    var body: some View {
        GeometryReader { geometry in
            ZStack {
                if let image = CoverStorage.image(reference) {
                    Image(nsImage: image).resizable().scaledToFill().frame(width: geometry.size.width, height: geometry.size.height).clipped()
                } else {
                    LinearGradient(colors: [Color(red: 0.06, green: 0.10, blue: 0.20), .indigo.opacity(0.7), Color(red: 0.05, green: 0.22, blue: 0.26)], startPoint: .topLeading, endPoint: .bottomTrailing)
                    Ellipse().fill(.cyan.opacity(0.32)).frame(width: geometry.size.width * 0.7, height: 160).blur(radius: 48).rotationEffect(.degrees(-25)).offset(x: geometry.size.width * 0.3, y: -50)
                    Ellipse().fill(.purple.opacity(0.3)).frame(width: geometry.size.width * 0.6, height: 130).blur(radius: 40).offset(x: -geometry.size.width * 0.3, y: 60)
                }
                LinearGradient(colors: [.black.opacity(0.08), .black.opacity(0.65)], startPoint: .top, endPoint: .bottom)
            }
        }.accessibilityHidden(true)
    }
}
