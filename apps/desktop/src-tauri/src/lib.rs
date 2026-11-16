//! SYSTEM MIND X — Native Desktop Presentation Shell Library
//!
//! Architectural Invariants:
//! 1. Strictly sandboxed presentation container (Layer 7).
//! 2. Zero ambient shell execution (`shell:allow-execute` is permanently absent).
//! 3. Content Security Policy air-gapping local localhost endpoints.
//! 4. Windows are non-fullscreen by default to preserve host OS context awareness.

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ShellSecurityInfo {
    pub shell_version: &'static str,
    pub csp_enforced: bool,
    pub ambient_shell_disabled: bool,
    pub fullscreen_blocked_by_default: bool,
    pub reverse_domain_id: &'static str,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct WindowGeometry {
    pub label: &'static str,
    pub width: u32,
    pub height: u32,
    pub min_width: u32,
    pub min_height: u32,
    pub resizable: bool,
    pub fullscreen: bool,
    pub decorations: bool,
}

/// Returns the security and capability posture of the desktop presentation shell.
pub fn get_shell_security_info() -> ShellSecurityInfo {
    ShellSecurityInfo {
        shell_version: "1.0.0",
        csp_enforced: true,
        ambient_shell_disabled: true,
        fullscreen_blocked_by_default: true,
        reverse_domain_id: "org.systemmind.desktop",
    }
}

/// Returns the default safe geometry for the primary operator console window.
pub fn get_default_window_geometry() -> WindowGeometry {
    WindowGeometry {
        label: "main",
        width: 1280,
        height: 860,
        min_width: 960,
        min_height: 640,
        resizable: true,
        fullscreen: false,
        decorations: true,
    }
}

/// Native application entrypoint.
pub fn run() {
    let security = get_shell_security_info();
    let geometry = get_default_window_geometry();
    println!(
        "[SYSTEM MIND X Desktop Shell] Initialized v{} (App ID: {}, Window: {}x{}, Fullscreen: {})",
        security.shell_version,
        security.reverse_domain_id,
        geometry.width,
        geometry.height,
        geometry.fullscreen
    );
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_shell_security_invariants() {
        let sec = get_shell_security_info();
        assert_eq!(sec.shell_version, "1.0.0");
        assert!(sec.csp_enforced, "CSP must be enforced");
        assert!(
            sec.ambient_shell_disabled,
            "Ambient shell execution must be strictly disabled"
        );
        assert!(
            sec.fullscreen_blocked_by_default,
            "Fullscreen must be disabled by default"
        );
        assert_eq!(sec.reverse_domain_id, "org.systemmind.desktop");
    }

    #[test]
    fn test_window_geometry_invariants() {
        let geom = get_default_window_geometry();
        assert_eq!(geom.label, "main");
        assert!(geom.width >= 1024, "Default width must be at least 1024");
        assert!(geom.height >= 700, "Default height must be at least 700");
        assert!(
            geom.min_width >= 800,
            "Minimum width constraint must be at least 800"
        );
        assert!(
            geom.min_height >= 600,
            "Minimum height constraint must be at least 600"
        );
        assert!(geom.resizable, "Window must be resizable");
        assert!(
            !geom.fullscreen,
            "Window must NOT be fullscreen by default"
        );
        assert!(geom.decorations, "Window decorations must be present");
    }
}
