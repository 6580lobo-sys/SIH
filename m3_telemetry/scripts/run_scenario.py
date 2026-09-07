import argparse
import sys
import yaml
import time
import os

from generator.fault_injection import (
    FaultManager,
    InjectorFault,
    MisfireFault,
    OilPressureDropFault,
    OverheatingFault,
    VibrationSpikeFault,
)
from generator.environment import ENVIRONMENT_PRESETS
from generator.throttle_profiles import AVAILABLE_MODES as THROTTLE_MODES
from publisher.streaming_harness import TelemetryPublisher
from publisher.csv_sink import CsvSink

FAULT_CLASS_MAP = {
    "injector": InjectorFault,
    "misfire": MisfireFault,
    "oil_drop_gradual": OilPressureDropFault,
    "oil_drop_sudden": OilPressureDropFault,
    "overheating": OverheatingFault,
    "vibration_spike": VibrationSpikeFault,
}

def load_scenario(yaml_path: str) -> dict:
    with open(yaml_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def run():
    parser = argparse.ArgumentParser(description="Run telemetry scenario from YAML config")
    parser.add_argument("--scenario-file", required=True, help="Path to YAML scenario config")
    parser.add_argument("--rate", type=float, default=10.0, help="Generation rate in Hz")
    parser.add_argument("--live", action="store_true", help="Run in real-time (default is fast-forward)")
    parser.add_argument("--live-print", action="store_true", help="Stream formatted lines to console in real-time (forces --live)")
    args = parser.parse_args()

    if args.live_print:
        args.live = True

    config = load_scenario(args.scenario_file)
    
    print(f"\n=== Scenario: {config.get('name', 'Unknown')} ===")
    
    faults = []
    for f_cfg in config.get("faults", []):
        f_type = f_cfg.get("type")
        if f_type not in FAULT_CLASS_MAP:
            print(f"ERROR: Unknown fault type '{f_type}'. Available: {list(FAULT_CLASS_MAP.keys())}")
            sys.exit(1)
            
        kwargs = {k: v for k, v in f_cfg.items() if k != "type"}
        
        # Map YAML convenience keys to the actual class parameters
        if "start_s" in kwargs:
            kwargs["start_time_s"] = kwargs.pop("start_s")
        
        # Map legacy/convenience string flags if present
        if f_type == "oil_drop_gradual":
            kwargs["mode"] = "gradual"
        elif f_type == "oil_drop_sudden":
            kwargs["mode"] = "sudden"
            
        cls = FAULT_CLASS_MAP[f_type]
        faults.append(cls(**kwargs))
        
    mgr = FaultManager(faults)
    
    env = config.get("environment", "standard_day")
    if env not in ENVIRONMENT_PRESETS:
        print(f"ERROR: Unknown environment '{env}'. Available: {list(ENVIRONMENT_PRESETS.keys())}")
        sys.exit(1)
        
    throttle = config.get("throttle_mode", "smooth")
    if throttle not in THROTTLE_MODES:
        print(f"ERROR: Unknown throttle mode '{throttle}'. Available: {list(THROTTLE_MODES)}")
        sys.exit(1)
        
    duration_s = float(config.get("duration_s", 30.0))
    output_csv = config.get("output_csv")
    
    csv_sink = None
    if output_csv:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(os.path.abspath(output_csv)), exist_ok=True)
        csv_sink = CsvSink(output_csv)
        
    def live_print_sink(msg, active_faults=""):
        d = msg.model_dump()
        t = d["timestamp_ms"]
        rpm = d["rpm"]
        cht = d["cht_c"]
        oil = d["oil_pressure_kpa"]
        vib = d["vibration_g"]
        
        if active_faults and active_faults != "healthy":
            fault_str = f"[[ {active_faults.upper()} ]]"
        else:
            fault_str = "OK"
            
        print(f"[{t}] RPM: {rpm:6.1f} | CHT: {cht:5.1f}°C | OIL: {oil:5.1f} kPa | VIB: {vib:4.2f}g | {fault_str}")

    def stdout_sink(msg, active_faults=""):
        label = active_faults if active_faults else "healthy"
        print(f"[{label}] {msg.model_dump_json()}")

    # Determine which sinks to use
    sinks = []
    if csv_sink:
        sinks.append(csv_sink)
    if args.live_print:
        sinks.append(live_print_sink)
    elif not csv_sink:
        # If nothing is specified, fallback to json stdout
        sinks.append(stdout_sink)

    def multi_sink(msg, active_faults=""):
        for s in sinks:
            s(msg, active_faults)
            
    sink = multi_sink
        
    pub = TelemetryPublisher(
        publish_cb=sink,
        environment_name=env,
        throttle_mode=throttle,
        fault_manager=mgr,
        rate_hz=args.rate
    )
    
    original_sleep = time.sleep
    original_time = time.time
    sim_time = time.time()
    
    if not args.live:
        def _mock_sleep(s): pass
        def _mock_time():
            nonlocal sim_time
            sim_time += (1.0 / args.rate)
            return sim_time
        time.sleep = _mock_sleep
        time.time = _mock_time
        print("[harness] Fast-forward mode enabled. Generating data...")

    try:
        pub.run(duration_s=duration_s)
    finally:
        time.sleep = original_sleep
        time.time = original_time
        if csv_sink:
            csv_sink.close()
            
    if output_csv:
        print(f"Done. Saved to {output_csv}")

if __name__ == "__main__":
    run()
