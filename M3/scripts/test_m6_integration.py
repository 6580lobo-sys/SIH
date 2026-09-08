import sys
import os
import time
import threading

# Ensure we can import from m3_telemetry
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from publisher.api import create_publisher, start_stream
from generator.fault_injection import MisfireFault
from schema.telemetry_schema import EngineTelemetryMessage

def main():
    print("=== M6 Integration Simulation ===")
    
    # 1. M6 creates the publisher without any initial faults
    print("[M6] Creating publisher (standard_day, smooth throttle)")
    pub = create_publisher("standard_day", "smooth")
    
    # Track state
    received_msgs = []
    faults_seen = set()

    # 2. M6 defines its callback to consume messages
    def m6_callback(msg: EngineTelemetryMessage, active_faults: str):
        received_msgs.append((msg.timestamp, active_faults, msg.rpm, msg.vibration_amplitude))
        if active_faults != "healthy":
            faults_seen.add(active_faults)
        
        # Only print occasionally to not flood the console
        if len(received_msgs) % 10 == 0:
            print(f"  [Callback] t={msg.timestamp:4.1f}s | RPM={msg.rpm:6.0f} | Faults={active_faults}")

    # 3. M6 starts the stream in a background thread (so it can do other things / inject faults)
    print("[M6] Starting live stream in background thread (5.0 seconds)...")
    def run_publisher():
        start_stream(pub, m6_callback, duration_s=5.0)
        
    t = threading.Thread(target=run_publisher)
    t.start()
    
    # 4. M6 waits 2 seconds in real-time
    time.sleep(2.0)
    
    # 5. M6 injects a fault mid-run
    # We schedule it to activate at sim time 2.5s for 1.5s
    print("\n[M6] Injecting MisfireFault mid-run! (Scheduled to start at t=2.5s for 1.5s)")
    fault = MisfireFault(severity=0.8, start_time_s=2.5, duration_s=1.5)
    pub.fault_manager.add(fault)
    
    # 6. Wait for the publisher loop to finish
    t.join()
    
    print("\n=== Validation ===")
    print(f"Total messages received: {len(received_msgs)}")
    print(f"Faults detected by callback: {faults_seen}")
    
    # Basic assertions
    assert len(received_msgs) == 50, f"Expected 50 messages (10Hz * 5s), got {len(received_msgs)}"
    assert "misfire" in faults_seen, "The injected fault was not observed in the callback!"
    
    # Verify the timeline
    healthy_before = all(f == "healthy" for t, f, _, _ in received_msgs if t < 2.3)
    faulted_during = any(f == "misfire" for t, f, _, _ in received_msgs if 2.5 <= t < 4.0)
    healthy_after  = all(f == "healthy" for t, f, _, _ in received_msgs if t >= 4.2)
    
    if healthy_before and faulted_during and healthy_after:
        print("Success! The module responded correctly to the external fault injection mid-stream.")
    else:
        print("Failure in fault timeline validation.")
        print(f"Healthy before 2.3s: {healthy_before}")
        print(f"Faulted during 2.5s-4.0s: {faulted_during}")
        print(f"Healthy after 4.2s: {healthy_after}")
        sys.exit(1)

if __name__ == "__main__":
    main()
