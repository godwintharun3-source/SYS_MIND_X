import Foundation

func main() {
    let args = CommandLine.arguments

    if args.contains("--version") {
        print("SYSTEM MIND X macOS Companion Agent v1.0.0 (Swift 6)")
        exit(0)
    }

    let isOneShot = args.contains("--oneshot")
    let telemetry = TelemetryCollector.collectTelemetry()

    if isOneShot {
        print("==================================================================================")
        print(" SYSTEM MIND X — Swift Native Companion Agent Telemetry")
        print("==================================================================================")
        print("  Thermal State:        \(telemetry.thermal_state)")
        if let app = telemetry.frontmost_app {
            print("  Frontmost App:        \(app.name) (\(app.bundle_id)) [PID: \(app.pid)]")
        } else {
            print("  Frontmost App:        None / Headless")
        }
        print("  System Uptime:        \(String(format: "%.1f", telemetry.system_uptime_seconds)) seconds")
        print("  Console User:         \(telemetry.console_user)")
        print("  Accessibility TCC:    \(telemetry.permissions.accessibility_granted ? "Granted" : "Restricted")")
        print("  Full Disk Access:     \(telemetry.permissions.full_disk_access_granted ? "Accessible" : "Restricted")")
        print("  Scan != Safe:         \(telemetry.scan_proves_safe ? "VIOLATION" : "Enforced (False)")")
        print("==================================================================================")
        exit(0)
    }

    // Default: output formatted JSON
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]

    do {
        let jsonData = try encoder.encode(telemetry)
        if let jsonString = String(data: jsonData, encoding: .utf8) {
            print(jsonString)
        }
    } catch {
        fputs("Failed to serialize telemetry to JSON: \(error)\n", stderr)
        exit(1)
    }
}

main()
