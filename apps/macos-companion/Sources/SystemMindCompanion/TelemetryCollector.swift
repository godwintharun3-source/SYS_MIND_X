import Foundation
import AppKit
import ApplicationServices

public enum TelemetryCollector {

    public static func getThermalState() -> String {
        switch ProcessInfo.processInfo.thermalState {
        case .nominal:
            return "NOMINAL"
        case .fair:
            return "FAIR"
        case .serious:
            return "SERIOUS"
        case .critical:
            return "CRITICAL"
        @unknown default:
            return "UNKNOWN"
        }
    }

    public static func getFrontmostApp() -> FrontmostAppPayload? {
        guard let app = NSWorkspace.shared.frontmostApplication else {
            return nil
        }
        let name = app.localizedName ?? "Unknown"
        let bundleId = app.bundleIdentifier ?? "unknown.bundle.id"
        let pid = app.processIdentifier
        let path = app.bundleURL?.path ?? ""

        return FrontmostAppPayload(
            name: name,
            bundle_id: bundleId,
            pid: pid,
            path: path
        )
    }

    public static func getPermissions() -> PermissionsPayload {
        let isAccessibilityGranted = AXIsProcessTrusted()
        
        let tccPath = "/Library/Application Support/com.apple.TCC/TCC.db"
        let isFdaGranted = FileManager.default.isReadableFile(atPath: tccPath)

        return PermissionsPayload(
            accessibility_granted: isAccessibilityGranted,
            screen_recording_granted: false, // Default unprivileged state without prompt
            full_disk_access_granted: isFdaGranted
        )
    }

    public static func collectTelemetry(isMock: Bool = false) -> TelemetryResponsePayload {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let timestamp = formatter.string(from: Date())

        let thermal = getThermalState()
        let frontmost = getFrontmostApp()
        let permissions = getPermissions()
        let uptime = ProcessInfo.processInfo.systemUptime
        let user = NSUserName()

        return TelemetryResponsePayload(
            thermal_state: thermal,
            frontmost_app: frontmost,
            permissions: permissions,
            system_uptime_seconds: uptime,
            console_user: user,
            screen_locked: false,
            timestamp: timestamp,
            host_platform: "Darwin",
            bridge_channel: "SWIFT_NATIVE_IPC",
            scan_proves_safe: false,
            unavailable_telemetry: [],
            is_mock: isMock
        )
    }
}
