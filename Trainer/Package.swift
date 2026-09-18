// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "Trainer",
    platforms: [.macOS(.v14)],
    products: [.executable(name: "Trainer", targets: ["Trainer"])],
    targets: [.executableTarget(name: "Trainer", path: "Sources/Trainer")]
)
