//! SYSTEM MIND X — Desktop Shell Binary Entrypoint
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    system_mind_desktop_lib::run();
}
