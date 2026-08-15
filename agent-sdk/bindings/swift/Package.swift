// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "NoteMeldAgentSDK",
    platforms: [.macOS(.v12), .iOS(.v15)],
    products: [.library(name: "NoteMeldAgentSDK", targets: ["NoteMeldAgentSDK"])],
    targets: [
        .target(
            name: "CNotemeldAgent",
            path: "Sources/CNotemeldAgent",
            publicHeadersPath: "include"
        ),
        .target(
            name: "NoteMeldAgentSDK",
            dependencies: ["CNotemeldAgent"],
            path: "Sources/NoteMeldAgentSDK"
        )
    ]
)
