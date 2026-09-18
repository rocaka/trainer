import SwiftUI
import AppKit
import UniformTypeIdentifiers

extension Notification.Name {
    static let trainerProfileChanged = Notification.Name("trainer.profile.changed")
}

enum AvatarStorage {
    static var directory: URL {
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Trainer/avatars", isDirectory: true)
    }
    static func image(_ reference: String) -> NSImage? {
        guard reference.hasPrefix("local-image:"),
              let id = UUID(uuidString: String(reference.dropFirst(12))) else { return nil }
        return NSImage(contentsOf: directory.appendingPathComponent(id.uuidString + ".png"))
    }
    @MainActor static func choose() throws -> String? {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.png, .jpeg, .heic]
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        panel.message = "头像仅保存在本机，不会发送给 AI 服务。"
        guard panel.runModal() == .OK, let url = panel.url else { return nil }
        let access = url.startAccessingSecurityScopedResource()
        defer { if access { url.stopAccessingSecurityScopedResource() } }
        let size = try url.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0
        guard size <= 10_000_000, let original = NSImage(contentsOf: url), original.size.width > 0, original.size.height > 0 else {
            throw NSError(domain: "TrainerAvatar", code: 1, userInfo: [NSLocalizedDescriptionKey: "请选择不超过 10 MB 的有效图片。"])
        }
        let canvas = NSImage(size: NSSize(width: 256, height: 256))
        canvas.lockFocus()
        let edge = min(original.size.width, original.size.height)
        original.draw(in: NSRect(x: 0, y: 0, width: 256, height: 256), from: NSRect(x: (original.size.width - edge) / 2, y: (original.size.height - edge) / 2, width: edge, height: edge), operation: .copy, fraction: 1)
        canvas.unlockFocus()
        guard let tiff = canvas.tiffRepresentation, let bitmap = NSBitmapImageRep(data: tiff), let png = bitmap.representation(using: .png, properties: [:]) else {
            throw NSError(domain: "TrainerAvatar", code: 2, userInfo: [NSLocalizedDescriptionKey: "图片处理失败，请换一张图片。"])
        }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let id = UUID().uuidString
        try png.write(to: directory.appendingPathComponent(id + ".png"), options: .atomic)
        return "local-image:" + id
    }
}

struct ProfileAvatar: View {
    let value: String
    var size: CGFloat = 40
    var body: some View {
        Group {
            if let image = AvatarStorage.image(value) {
                Image(nsImage: image).resizable().scaledToFill()
            } else {
                Text(value.hasPrefix("local-image:") ? "🧑‍💻" : value).font(.system(size: size * 0.52))
            }
        }.frame(width: size, height: size).background(.ultraThinMaterial, in: Circle())
            .clipShape(Circle()).overlay(Circle().stroke(.indigo.opacity(0.4)))
            .accessibilityLabel("用户头像")
    }
}
