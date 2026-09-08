"""Public API for the m3_telemetry module.

This module provides a programmatic interface for generating or replaying
telemetry without relying on CLI arguments or standard output. It is designed
to be easily integrated into shared event loops, orchestrators, or API endpoints.
"""

import csv
import sys
import contextlib
import os
from typing import Iterator, Callable, Optional, Dict, Any, List

from schema.telemetry_schema import EngineTelemetryMessage
from publisher.streaming_harness import TelemetryPublisher, FAULT_REGISTRY
from generator.fault_injection import (
    FaultManager,
    NoOpFault,
    OilPressureDropFault,
    OverheatingFault,
)


def create_publisher(
    environment: str,
    throttle_mode: str,
    faults: Optional[List[Dict[str, Any]]] = None
) -> TelemetryPublisher:
    """Create a configured TelemetryPublisher.

    Args:
        environment: Environment preset (e.g., 'standard_day', 'hot_day').
        throttle_mode: Throttle profile mode (e.g., 'smooth', 'idle_only').
        faults: List of dictionaries specifying faults to inject.
            Example: [{'type': 'misfire', 'start_s': 5.0, 'duration_s': 10.0, 'severity': 0.7}]

    Returns:
        A configured TelemetryPublisher instance.
    """
    fault_manager = FaultManager()
    
    if faults:
        for fault_def in faults:
            fault_type = fault_def.get("type")
            if fault_type not in FAULT_REGISTRY:
                available = ", ".join(sorted(FAULT_REGISTRY.keys()))
                raise ValueError(f"Unknown fault type: {fault_type}. Available: {available}")
            
            cls = FAULT_REGISTRY[fault_type]
            start_s = float(fault_def.get("start_s", 0.0))
            duration_s = fault_def.get("duration_s")
            if duration_s is not None:
                duration_s = float(duration_s)
            severity = float(fault_def.get("severity", 0.5))

            # Build fault scenario based on its specific requirements
            if cls is NoOpFault:
                scenario = cls(start_time_s=start_s, duration_s=duration_s)
            elif cls is OilPressureDropFault:
                mode = "sudden" if fault_type == "oil_drop_sudden" else "gradual"
                dur = duration_s if duration_s is not None else 30.0
                scenario = cls(
                    severity=severity,
                    mode=mode,
                    start_time_s=start_s,
                    duration_s=dur,
                )
            elif cls is OverheatingFault:
                dur = duration_s if duration_s is not None else 30.0
                scenario = cls(
                    severity=severity,
                    start_time_s=start_s,
                    duration_s=dur,
                )
            else:
                scenario = cls(
                    severity=severity,
                    start_time_s=start_s,
                    duration_s=duration_s,
                )
            fault_manager.add(scenario)

    # Use a dummy default publish_cb; start_stream will overwrite it.
    publisher = TelemetryPublisher(
        rate_hz=10.0,
        publish_cb=lambda msg, active: None, 
        fault_manager=fault_manager,
        environment_name=environment,
        throttle_mode=throttle_mode,
    )
    return publisher


def start_stream(
    publisher: TelemetryPublisher,
    callback: Callable[[EngineTelemetryMessage, str], None],
    duration_s: Optional[float] = None
) -> None:
    """Start streaming telemetry data to the provided callback.

    Args:
        publisher: TelemetryPublisher instance to run.
        callback: Function to handle each (EngineTelemetryMessage, active_faults_label).
        duration_s: How many seconds to stream. If None, stream for 1 year.
    """
    # Overwrite the callback to route telemetry directly to the caller's function
    publisher.publish_cb = callback
    
    # If duration_s is None, provide a very large default so it streams indefinitely.
    # 31536000 seconds is 365 days.
    run_duration = duration_s if duration_s is not None else 31536000.0

    try:
        # Suppress the stderr output from publisher.run to keep it completely silent for APIs
        with open(os.devnull, 'w') as devnull:
            with contextlib.redirect_stderr(devnull):
                publisher.run(duration_s=run_duration)
    except KeyboardInterrupt:
        # Silently exit on Ctrl+C since M6 orchestrator handles the interruption
        pass


def load_replay_csv(path: str) -> Iterator[EngineTelemetryMessage]:
    """Yield telemetry messages from a saved CSV file.

    Args:
        path: Path to the CSV file.

    Yields:
        Parsed EngineTelemetryMessage instances.
    """
    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # active_faults is for labelling, not part of the schema
            if "active_faults" in row:
                del row["active_faults"]
            yield EngineTelemetryMessage(**row)


if __name__ == "__main__":
    # --------------------------------------------------------------------------
    # Usage Example
    # --------------------------------------------------------------------------
    print("Example 1: Streaming synthetic data in-memory")
    
    # 1. Create a publisher with a fault profile
    faults = [
        {"type": "misfire", "start_s": 1.0, "duration_s": 2.0, "severity": 0.8}
    ]
    pub = create_publisher(environment="standard_day", throttle_mode="smooth", faults=faults)
    
    # 2. Define a callback to receive data
    def my_callback(msg: EngineTelemetryMessage, fault_label: str):
        print(f"Received msg {msg.msg_id} at {msg.timestamp_ms}. Faults: {fault_label}, RPM: {msg.rpm:.1f}")

    # 3. Stream data for 3 seconds
    start_stream(pub, my_callback, duration_s=3.0)
    
    # Example 2: Replaying data from CSV (assuming test_default.csv exists)
    # import os
    # test_csv = os.path.join(os.path.dirname(__file__), "..", "test_default.csv")
    # if os.path.exists(test_csv):
    #     print("\nExample 2: Replaying from CSV")
    #     replay_iter = load_replay_csv(test_csv)
    #     for i, msg in enumerate(replay_iter):
    #         print(f"Replayed msg: {msg.msg_id}, RPM: {msg.rpm:.1f}")
    #         if i >= 4:
    #             break
