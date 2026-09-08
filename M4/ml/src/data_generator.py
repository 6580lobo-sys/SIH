import numpy as np
import pandas as pd
from pathlib import Path
from src.config import (
    DATA_RAW_DIR, NORMAL_RANGES, MISSION_PHASES,
    FAULT_TYPES, FAULT_TYPE_TO_INT, RAW_SENSOR_COLS
)

def generate_mission_profile(n_steps):
    phases = []
    # idle(5%), taxi(5%), takeoff(10%), cruise(60%), descent(10%), landing(10%)
    counts = [int(n_steps*0.05), int(n_steps*0.05), int(n_steps*0.10), 
              int(n_steps*0.60), int(n_steps*0.10)]
    counts.append(n_steps - sum(counts)) # remainder for landing
    
    for i, phase in enumerate(MISSION_PHASES):
        phases.extend([phase] * counts[i])
    return np.array(phases)

def generate_healthy_telemetry(n_steps=900, noise_std=0.02, seed=42):
    np.random.seed(seed)
    df = pd.DataFrame(index=range(n_steps))
    df['timestamp'] = np.arange(n_steps)
    df['mission_phase'] = generate_mission_profile(n_steps)
    
    # Sensors
    for sensor, (min_val, max_val) in NORMAL_RANGES.items():
        base_val = np.random.uniform(min_val, max_val)
        noise = np.random.normal(0, noise_std * (max_val - min_val), n_steps)
        df[sensor] = base_val + noise
    
    # Labels
    df['fault_type'] = "healthy"
    df['fault_active'] = 0
    df['fault_severity'] = 0
    df['fault_start_time'] = 0
    df['fault_end_time'] = 0
    
    # Residuals
    for sensor in ['rpm', 'oil_pressure', 'oil_temp', 'cht', 'egt', 'manifold_pressure', 'vibration', 'fuel_flow']:
        df[f'residual_{sensor}'] = np.random.normal(0, 0.5, n_steps)
        
    df['health_index'] = 1.0
    df['baseline_rul'] = 200.0
    
    return df

def inject_fault(df, fault_type, fault_start=300, severity=2, seed=42):
    np.random.seed(seed)
    n_steps = len(df)
    fault_len = n_steps - fault_start
    ramp = np.linspace(0, 1, fault_len)
    
    df_faulty = df.copy()
    
    if fault_type == "overheating":
        df_faulty.loc[fault_start:, 'cht'] += ramp * 60
        df_faulty.loc[fault_start:, 'egt'] += ramp * 80
        df_faulty.loc[fault_start:, 'residual_cht'] += ramp * 60
        df_faulty.loc[fault_start:, 'residual_egt'] += ramp * 80
        df_faulty.loc[fault_start:, 'health_index'] -= ramp * 0.6
        
    elif fault_type == "oil_pressure_drop":
        df_faulty.loc[fault_start:, 'oil_pressure'] -= ramp * 20
        df_faulty.loc[fault_start:, 'oil_temp'] += ramp * 15
        df_faulty.loc[fault_start:, 'residual_oil_pressure'] -= ramp * 20
        df_faulty.loc[fault_start:, 'residual_oil_temp'] += ramp * 15
        df_faulty.loc[fault_start:, 'health_index'] -= ramp * 0.7
        
    elif fault_type == "vibration_bearing_fault":
        df_faulty.loc[fault_start:, 'vibration'] += ramp * 0.8
        df_faulty.loc[fault_start:, 'rpm'] += np.random.normal(0, 200, fault_len)
        df_faulty.loc[fault_start:, 'residual_vibration'] += ramp * 0.8
        df_faulty.loc[fault_start:, 'health_index'] -= ramp * 0.6
        
    elif fault_type == "misfire_or_injector_fault":
        spikes = np.zeros(fault_len)
        spikes[::5] = np.random.normal(50, 10, len(spikes[::5]))
        df_faulty.loc[fault_start:, 'egt'] += spikes
        df_faulty.loc[fault_start:, 'fuel_flow'] += np.random.normal(0, 2, fault_len)
        drops = np.zeros(fault_len)
        drops[::5] = -300
        df_faulty.loc[fault_start:, 'rpm'] += drops
        df_faulty.loc[fault_start:, 'residual_egt'] += spikes
        df_faulty.loc[fault_start:, 'health_index'] -= ramp * 0.5
        
    elif fault_type == "fuel_mixture_drift":
        df_faulty.loc[fault_start:, 'fuel_flow'] += ramp * 4
        df_faulty.loc[fault_start:, 'egt'] += ramp * 40
        df_faulty.loc[fault_start:, 'residual_fuel_flow'] += ramp * 4
        df_faulty.loc[fault_start:, 'health_index'] -= ramp * 0.4
        
    elif fault_type == "cooling_system_fault":
        df_faulty.loc[fault_start:, 'cht'] += ramp * 50
        df_faulty.loc[fault_start:, 'oil_temp'] += ramp * 20
        df_faulty.loc[fault_start:, 'residual_cht'] += ramp * 50
        df_faulty.loc[fault_start:, 'health_index'] -= ramp * 0.55
        
    elif fault_type == "engine_overspeed":
        # Simulating a massive RPM spike
        df_faulty.loc[fault_start:, 'rpm'] += ramp * 5000
        df_faulty.loc[fault_start:, 'residual_rpm'] += ramp * 5000
        df_faulty.loc[fault_start:, 'health_index'] -= ramp * 0.8
        
    df_faulty.loc[fault_start:, 'fault_type'] = fault_type
    df_faulty.loc[fault_start:, 'fault_active'] = 1
    df_faulty.loc[fault_start:, 'fault_severity'] = severity
    df_faulty.loc[fault_start:, 'fault_start_time'] = fault_start
    df_faulty.loc[fault_start:, 'fault_end_time'] = n_steps
    
    return df_faulty

def save_run(df, filename):
    filepath = DATA_RAW_DIR / filename
    df.to_csv(filepath, index=False)
    print(f"Saved {filename}")

def generate_all_datasets():
    save_run(generate_healthy_telemetry(seed=1), "healthy_run_01.csv")
    save_run(generate_healthy_telemetry(seed=2), "healthy_run_02.csv")
    save_run(generate_healthy_telemetry(seed=3), "healthy_run_03.csv")
    
    fault_seeds = {
        "overheating": 10,
        "oil_pressure_drop": 11,
        "vibration_bearing_fault": 12,
        "misfire_or_injector_fault": 13,
        "fuel_mixture_drift": 14,
        "cooling_system_fault": 15,
        "engine_overspeed": 16
    }
    
    for fault in FAULT_TYPES[1:]:
        base = generate_healthy_telemetry(seed=fault_seeds.get(fault, 42))
        faulty = inject_fault(base, fault_type=fault, fault_start=300)
        save_run(faulty, f"{fault}_01.csv")
        
    base2 = generate_healthy_telemetry(seed=111)
    faulty2 = inject_fault(base2, fault_type="oil_pressure_drop", fault_start=300)
    save_run(faulty2, "oil_pressure_drop_02.csv")

if __name__ == "__main__":
    generate_all_datasets()
    print("All synthetic datasets generated.")
