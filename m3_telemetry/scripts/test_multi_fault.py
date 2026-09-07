import os
import time
import pandas as pd
from pydantic import ValidationError

from generator.fault_injection import (
    FaultManager,
    OverheatingFault,
    OilPressureDropFault,
    MisfireFault,
    VibrationSpikeFault
)
from publisher.streaming_harness import TelemetryPublisher
from publisher.csv_sink import CsvSink

def run_multi_fault_tests():
    # Mock time for fast-forward batch generation
    original_sleep = time.sleep
    original_time = time.time
    sim_time = time.time()
    
    def _mock_sleep(s):
        pass
        
    def _mock_time():
        nonlocal sim_time
        sim_time += 0.1
        return sim_time
        
    time.sleep = _mock_sleep
    time.time = _mock_time
    
    pairings = [
        ("Overheat_OilDrop", [
            OverheatingFault(start_time_s=5.0, duration_s=15.0, severity=0.8),
            OilPressureDropFault(start_time_s=12.0, duration_s=6.0, mode="gradual", severity=0.8)
        ]),
        ("Misfire_VibSpike", [
            MisfireFault(start_time_s=5.0, duration_s=10.0, severity=0.8),
            VibrationSpikeFault(pattern="intermittent", start_time_s=10.0, duration_s=10.0, severity=0.8)
        ])
    ]
    
    os.makedirs("data/multi_fault", exist_ok=True)
    
    try:
        for name, faults in pairings:
            print(f"\n=== Testing Pairing: {name} ===")
            mgr = FaultManager(faults)
            csv_path = f"data/multi_fault/{name}.csv"
            sink = CsvSink(csv_path)
            
            pub = TelemetryPublisher(
                publish_cb=sink,
                environment_name="standard_day",
                throttle_mode="rapid_transient",
                fault_manager=mgr,
                rate_hz=10
            )
            
            try:
                pub.run(duration_s=25.0)
                print("Schema validation: PASSED (No ValidationErrors thrown during generation)")
            except ValidationError as e:
                print(f"Schema validation: FAILED!\n{e}")
                continue
            finally:
                sink.close()
                
            df = pd.read_csv(csv_path)
            labels = df["active_faults"].fillna("")
            
            # Find rows with a comma, indicating multiple active faults
            overlap = df[labels.str.contains(",")]
            
            if not overlap.empty:
                print(f"Overlap window found! Label example: '{overlap.iloc[0]['active_faults']}'")
                expected_f1 = faults[0].name
                expected_f2 = faults[1].name
                assert expected_f1 in overlap.iloc[0]["active_faults"], f"Missing {expected_f1}"
                assert expected_f2 in overlap.iloc[0]["active_faults"], f"Missing {expected_f2}"
                print("Overlap labels correctly contain both faults.")
            else:
                print("WARNING: No overlap window found! Labels:")
                print(labels.unique())
                
    finally:
        time.sleep = original_sleep
        time.time = original_time

if __name__ == "__main__":
    run_multi_fault_tests()
