//! Daemon binary entrypoint for the SYSTEM MIND X Privileged Capability Broker.

use std::env;
use system_mind_broker::PrivilegedCapabilityBroker;
use system_mind_sensors::MockSensorAdapter;

const VERSION: &str = "1.0.0";

fn print_help() {
    println!("SYSTEM MIND X Privileged Broker Daemon v{}", VERSION);
    println!("Usage: system-mind-broker [OPTIONS]");
    println!();
    println!("Options:");
    println!("  --version     Print daemon version and exit");
    println!("  --status      Print broker readiness and platform sensors");
    println!("  --help        Print this help message and exit");
}

fn main() {
    let args: Vec<String> = env::args().collect();

    if args.iter().any(|a| a == "--version") {
        println!("system-mind-broker v{}", VERSION);
        return;
    }

    if args.iter().any(|a| a == "--status") {
        let broker = PrivilegedCapabilityBroker::new(Box::new(MockSensorAdapter::new()));
        match broker.execute_telemetry_read() {
            Ok(snapshot) => {
                println!("SYSTEM MIND X Privileged Broker: OPERATIONAL");
                println!("  Version: v{}", VERSION);
                println!("  Platform: {}", snapshot.os_platform);
                println!("  Thermal State: {}", snapshot.thermal_state);
                println!("  Memory RSS: {} bytes", snapshot.memory_rss_bytes);
            }
            Err(e) => {
                eprintln!("Broker initialization failed: {}", e);
                std::process::exit(1);
            }
        }
        return;
    }

    if args.iter().any(|a| a == "--help") || args.len() <= 1 {
        print_help();
        return;
    }

    eprintln!("Unknown argument. Run with --help for usage.");
    std::process::exit(1);
}
