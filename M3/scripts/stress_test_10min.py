import sys
import os
import time
import tracemalloc

# Ensure we can import from m3_telemetry
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from publisher.api import create_publisher, start_stream
from generator.fault_injection import (
    MisfireFault, OverheatingFault, OilPressureDropFault, 
    InjectorFault, VibrationSpikeFault
)

def main():
    print("Starting 10-minute stress test...")
    tracemalloc.start()
    
    pub = create_publisher("standard_day", "rapid_transient")
    
    # Inject faults every 90 seconds
    faults = [
        MisfireFault(start_time_s=90.0, duration_s=30.0, severity=0.8),
        OverheatingFault(start_time_s=180.0, duration_s=30.0, severity=0.9),
        OilPressureDropFault(start_time_s=270.0, duration_s=30.0, severity=1.0, mode="sudden"),
        OilPressureDropFault(start_time_s=360.0, duration_s=30.0, severity=0.8, mode="gradual"),
        InjectorFault(start_time_s=450.0, duration_s=30.0, severity=0.7),
        VibrationSpikeFault(start_time_s=540.0, duration_s=30.0, severity=0.9),
    ]
    for f in faults:
        pub.fault_manager.add(f)
        
    start_time = time.time()
    
    last_mark_time = start_time
    last_mark_msgs = 0
    total_msgs = 0
    
    reports = []
    
    def callback(msg, active_faults):
        nonlocal last_mark_time, last_mark_msgs, total_msgs
        total_msgs += 1
        
        # Check every 600 messages (approx 60 seconds)
        if total_msgs % 600 == 0:
            now = time.time()
            elapsed_interval = now - last_mark_time
            msgs_in_interval = total_msgs - last_mark_msgs
            achieved_rate = msgs_in_interval / elapsed_interval if elapsed_interval > 0 else 0
            
            # Memory
            current, peak = tracemalloc.get_traced_memory()
            mem_mb = current / 1024 / 1024
            
            minute = total_msgs // 600
            report = f"Minute {minute:2d}: Rate={achieved_rate:5.2f} Hz | Mem={mem_mb:5.2f} MB | Fault={active_faults}"
            print(report, flush=True)
            reports.append(report)
            
            last_mark_time = now
            last_mark_msgs = total_msgs

    print("Running stream for 600 seconds. Waiting...")
    try:
        start_stream(pub, callback, duration_s=600.0)
    except Exception as e:
        print(f"FAILED with error: {e}")
        sys.exit(1)
        
    print("\n--- FINAL REPORT ---")
    for r in reports:
        print(r)
        
    current, peak = tracemalloc.get_traced_memory()
    print(f"Peak memory traced: {peak / 1024 / 1024:.2f} MB")
    
if __name__ == "__main__":
    main()
