import pandas as pd
import numpy as np

files = {
    "Misfire": {
        "path": "data/replay_library/fault_misfire_standard.csv",
        "primary": ["rpm", "vibration_g"]
    },
    "Overheating": {
        "path": "data/replay_library/fault_overheating_standard.csv",
        "primary": ["cht_c"]
    },
    "Oil Pressure Drop": {
        "path": "data/replay_library/fault_oil_pressure_drop_standard.csv",
        "primary": ["oil_pressure_kpa"]
    },
    "Injector Fault": {
        "path": "data/replay_library/fault_injector_standard.csv",
        "primary": ["fuel_flow_lph", "egt_c"]
    }
}

for name, meta in files.items():
    df = pd.read_csv(meta["path"])
    labels = df["active_faults"].fillna("healthy")
    
    # In standard replays, fault is 10s to 20s.
    # We can just segment by labels != "healthy"
    is_fault = labels != "healthy"
    
    # strictly find indices
    fault_indices = np.where(is_fault)[0]
    if len(fault_indices) == 0:
        continue
        
    start_idx = fault_indices[0]
    end_idx = fault_indices[-1]
    
    before = df.iloc[:start_idx]
    during = df.iloc[start_idx:end_idx+1]
    after = df.iloc[end_idx+1:]
    
    print(f"\n=== {name} ===")
    for col in meta["primary"]:
        mean_b = before[col].mean()
        mean_d = during[col].mean()
        mean_a = after[col].mean() if len(after) > 0 else mean_b
        
        pct_change = ((mean_d - mean_b) / mean_b) * 100
        
        print(f"  Sensor: {col}")
        print(f"    Before: {mean_b:8.2f}")
        print(f"    During: {mean_d:8.2f} ({pct_change:+6.1f}%)")
        print(f"    After : {mean_a:8.2f}")

