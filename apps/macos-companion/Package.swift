// swift-tools-version: 5.7
// The swift-tools-version declares the minimum version of Swift required to build this package.

import PackageDescription

let package = Package(
    name: "SystemMindCompanion",
    platforms: [
        .macOS(.v12)
    ],
    products: [
        .executable(
            name: "SystemMindCompanion",
            targets: ["SystemMindCompanion"]
        )
    ],
    dependencies: [],
    targets: [
        .executableTarget(
            name: "SystemMindCompanion",
            dependencies: [],
            path: "Sources/SystemMindCompanion"
        )
    ]
)
