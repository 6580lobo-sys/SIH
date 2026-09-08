import argparse
import sys
import yaml
import os
import logging
from datetime import datetime
import json

# Ensure we can import from m3_telemetry
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from publisher.api import create_publisher, start_stream
from generator.fault_injection import (
    InjectorFault,
    MisfireFault,
    OilPressureDropFault,
    OverheatingFault,
    VibrationSpikeFault,
)
from pydantic import ValidationError

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

def main():
    parser = argparse.ArgumentParser(description="M6 Integration Issue Reproducer")
    parser.add_argument("--scenario-file", required=True, help="Path to YAML scenario config (.yaml)")
    parser.add_argument("--issue-desc", type=str, required=True, help="Short description of the unexpected behavior (e.g., 'Misfire fault didn't trigger vibration spike')")
    
    args = parser.parse_args()
    
    # 1. Setup Logging Directory
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    logs_dir = os.path.join(base_dir, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    scenario_name = os.path.splitext(os.path.basename(args.scenario_file))[0]
    log_file = os.path.join(logs_dir, f"repro_{scenario_name}_{timestamp_str}.log")
    
    # Configure root logger
    logging.basicConfig(
        filename=log_file,
        filemode="w",
        format="%(asctime)s | %(levelname)s | %(message)s",
        level=logging.DEBUG
    )
    
    # Also log INFO and above to console so the user sees progress
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    logging.getLogger().addHandler(console)
    
    logging.info("=== M6 Issue Reproduction Run ===")
    logging.info(f"Issue Description : {args.issue_desc}")
    logging.info(f"Scenario File     : {args.scenario_file}")
    logging.info(f"Detailed Log File : {log_file}")
    
    # 2. Parse YAML Scenario Config
    try:
        config = load_scenario(args.scenario_file)
    except Exception as e:
        logging.error(f"Failed to load scenario {args.scenario_file}: {e}")
        sys.exit(1)
        
    env = config.get("environment", "standard_day")
    throttle = config.get("throttle_mode", "smooth")
    duration_s = float(config.get("duration_s", 10.0))
    
    logging.info(f"Config -> Env: {env}, Throttle: {throttle}, Duration: {duration_s}s")
    
    # 3. Initialize Publisher via Clean API
    logging.info("Initializing publisher via publisher.api...")
    try:
        pub = create_publisher(environment=env, throttle_mode=throttle)
    except Exception as e:
        logging.error(f"Failed to create publisher: {e}")
        sys.exit(1)
        
    # 4. Attach Faults to the API Publisher dynamically
    for f_cfg in config.get("faults", []):
        f_type = f_cfg.get("type")
        if f_type not in FAULT_CLASS_MAP:
            logging.error(f"Unknown fault type '{f_type}'")
            continue
            
        kwargs = {k: v for k, v in f_cfg.items() if k != "type"}
        # Normalize yaml syntax keys to class kwargs
        if "start_s" in kwargs:
            kwargs["start_time_s"] = kwargs.pop("start_s")
            
        if f_type == "oil_drop_gradual":
            kwargs["mode"] = "gradual"
        elif f_type == "oil_drop_sudden":
            kwargs["mode"] = "sudden"
            
        cls = FAULT_CLASS_MAP[f_type]
        fault_obj = cls(**kwargs)
        pub.fault_manager.add(fault_obj)
        logging.info(f"Scheduled Fault: {fault_obj}")
        
    # 5. Define Callback to capture all state transitions and validate schema
    messages_received = 0
    last_fault_state = "healthy"
    
    def repro_callback(msg, active_faults):
        nonlocal messages_received, last_fault_state
        messages_received += 1
        
        # Log state changes explicitly (Shows up in Console + File)
        if active_faults != last_fault_state:
            logging.info(f"[{msg.timestamp:5.1f}s] FAULT STATE CHANGE: {last_fault_state} -> {active_faults}")
            last_fault_state = active_faults
            
        # Log every schema validation to the file (DEBUG level only goes to File)
        try:
            dump = msg.model_dump()
            logging.debug(f"[{msg.timestamp:5.1f}s] VALIDATED SCHEMA: {json.dumps(dump)}")
        except Exception as e:
            logging.error(f"[{msg.timestamp:5.1f}s] UNEXPECTED ERROR serializing message: {e}")

    # 6. Run Stream
    logging.info("Starting live stream (blocking)...")
    try:
        start_stream(pub, repro_callback, duration_s=duration_s)
        logging.info(f"Stream completed normally. {messages_received} messages processed and validated.")
    except ValidationError as e:
        logging.error("CRITICAL: Schema Validation Failed during execution!")
        logging.error(e.json())
    except Exception as e:
        logging.error(f"CRITICAL: Runtime exception: {e}")
        logging.exception(e)
    finally:
        logging.info("=== End Reproduction Run ===")
        print(f"\nVerbose logs safely saved to: {log_file}")
        print("Please attach this log to your M6 integration bug report so M3 can quickly diff against expected behavior!")

if __name__ == "__main__":
    main()
