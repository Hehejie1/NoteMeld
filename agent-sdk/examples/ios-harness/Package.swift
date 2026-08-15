// swift-tools-version: 5.9
import Foundation
import PackageDescription

let libraryDirectory = ProcessInfo.processInfo.environment["NOTEMELD_AGENT_LIBRARY_DIR"] ?? "."
let package = Package(
    name: "NoteMeldAgentIOSHarness",
    platforms: [.macOS(.v12), .iOS(.v15)],
    dependencies: [.package(path: "../../bindings/swift")],
    targets: [.executableTarget(
        name: "NoteMeldAgentIOSHarness",
        dependencies: [.product(name: "NoteMeldAgentSDK", package: "swift")],
        linkerSettings: [.unsafeFlags(["-L", libraryDirectory, "-lnotemeld_agent",
                                      "-Xlinker", "-rpath", "-Xlinker", libraryDirectory])]
    )]
)
