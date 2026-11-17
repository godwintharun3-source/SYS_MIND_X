import Foundation

public struct FrontmostAppPayload: Codable {
    public let name: String
    public let bundle_id: String
    public let pid: Int32
    public let path: String

    public init(name: String, bundle_id: String, pid: Int32, path: String) {
        self.name = name
        self.bundle_id = bundle_id
        self.pid = pid
        self.path = path
    }
}

public struct PermissionsPayload: Codable {
    public let accessibility_granted: Bool
    public let screen_recording_granted: Bool
    public let full_disk_access_granted: Bool

    public init(accessibility_granted: Bool, screen_recording_granted: Bool, full_disk_access_granted: Bool) {
        self.accessibility_granted = accessibility_granted
        self.screen_recording_granted = screen_recording_granted
        self.full_disk_access_granted = full_disk_access_granted
    }
}

public struct TelemetryResponsePayload: Codable {
    public let thermal_state: String
    public let frontmost_app: FrontmostAppPayload?
    public let permissions: PermissionsPayload
    public let system_uptime_seconds: Double
    public let console_user: String
    public let screen_locked: Bool
    public let timestamp: String
    public let host_platform: String
    public let bridge_channel: String
    public let scan_proves_safe: Bool
    public let unavailable_telemetry: [String]
    public let is_mock: Bool

    public init(
        thermal_state: String,
        frontmost_app: FrontmostAppPayload?,
        permissions: PermissionsPayload,
        system_uptime_seconds: Double,
        console_user: String,
        screen_locked: Bool,
        timestamp: String,
        host_platform: String,
        bridge_channel: String,
        scan_proves_safe: Bool = false,
        unavailable_telemetry: [String] = [],
        is_mock: Bool = false
    ) {
        self.thermal_state = thermal_state
        self.frontmost_app = frontmost_app
        self.permissions = permissions
        self.system_uptime_seconds = system_uptime_seconds
        self.console_user = console_user
        self.screen_locked = screen_locked
        self.timestamp = timestamp
        self.host_platform = host_platform
        self.bridge_channel = bridge_channel
        self.scan_proves_safe = scan_proves_safe
        self.unavailable_telemetry = unavailable_telemetry
        self.is_mock = is_mock
    }
}

public struct JsonRpcRequest: Codable {
    public let jsonrpc: String
    public let id: String
    public let method: String
}

public struct JsonRpcResponse: Codable {
    public let jsonrpc: String
    public let id: String
    public let result: TelemetryResponsePayload?
    public let error: String?
}
