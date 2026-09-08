import pandas as pd
from pathlib import Path
from src.predict import predict_engine_health
from src.config import DATA_RAW_DIR, BASE_DIR, WINDOW_SIZE

def demo_scenario(csv_file: str, label: str):
    file_path = DATA_RAW_DIR / csv_file
    if not file_path.exists():
        file_path = BASE_DIR / "data" / csv_file
        
    if not file_path.exists():
        print(f"[ERROR] File not found: {csv_file}")
        return
        
    df = pd.read_csv(file_path)
    print(f"\n{'='*60}\nDEMO: {label}\nMission: {csv_file}, {len(df)} timesteps\n{'='*60}")
    
    anomaly_detected_at = None
    
    # We predict every few steps in demo to make it fast
    for i in range(WINDOW_SIZE, len(df), 5):
        window = df.iloc[i-WINDOW_SIZE:i]
        
        # Predict engine health from telemetry window
        result = predict_engine_health(window)
        
        if result["is_anomaly"]:
            if anomaly_detected_at is None:
                anomaly_detected_at = i
            
            rul_val = window.iloc[-1]["baseline_rul"] if "baseline_rul" in window.columns else "N/A"
            
            print(f"\n[ANOMALY] DETECTED at t={i}s")
            print(f"   Fault:       {result['fault_type']}")
            print(f"   Confidence:  {result['confidence']*100:.1f}%")
            print(f"   Severity:    {result['severity']}/3")
            print(f"   Health State:{result['health_state']}")
            print(f"   RUL:         {rul_val}")
            print(f"   Top Sensors: {', '.join(result['top_features'][:3])}")
            print(f"   Explanation: {result['explanation']}")
            
    if anomaly_detected_at is None:
        print("[OK] Engine ran healthy throughout mission - no anomalies detected.")

if __name__ == "__main__":
    demo_scenario("healthy_run_01.csv", "HEALTHY ENGINE RUN")
    #demo_scenario("oil_pressure_drop_01.csv", "OIL PRESSURE DROP FAULT")
    #demo_scenario("overheating_01.csv", "OVERHEATING FAULT")
    demo_scenario("test_mixed_mission_01.csv", "MY CUSTOM TEST DATA")

