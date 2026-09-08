# M4 Baseline Implementation Plan
## SIH26054 — AI-Enabled Real-Time Digital Twin for MALE UAV Aero Piston Engines
### Module: M4 AI/ML — Anomaly Detection, Fault Classification & Explainability (Baseline)

---

> [!IMPORTANT]
> This plan is **self-contained and agent-executable**. Every file path, function signature, library version, data schema column, hyperparameter, and evaluation step is specified. An AI agent reading this document should be able to build the complete baseline from scratch without any external reference.

---

## 0. Project Context & Objective

**Competition:** Smart India Hackathon (SIH) 2026  
**Problem Statement:** PS26054 — DRDO, Real-Time AI-Enabled Digital Twin System for MALE UAV Aero Piston Engines  
**Module:** M4 — AI/ML Layer (Anomaly Detection + Fault Classification + Explainability)

### What M4 Must Answer
1. **Is this engine normal or abnormal?** → Isolation Forest anomaly detector
2. **If abnormal, which fault type?** → RandomForestClassifier fault classifier
3. **Why did the model raise an alert?** → Feature importance + SHAP explanation layer

### M4 Position in System Pipeline
```
M1 Physics Engine Model (Otto/Diesel-cycle Python simulator)
        ↓
M3 Telemetry Stream + Fault Injection (CSV / real-time)
        ↓
M2 Residual Engine + Health Index Calculator
        ↓
[THIS MODULE] M4 AI/ML — Isolation Forest + RandomForest + SHAP
        ↓
M5 Dashboard + Alerts (Streamlit / React)
        ↓
M6 Integration + Deployment (FastAPI)
```

**Baseline Scope:** Only Isolation Forest + RandomForestClassifier. LSTM/TCN/XGBoost are post-baseline improvements.

---

## 1. Repository & Directory Structure

Create the following directory tree under `ml/` at the project root:

```
ml/
├── data/
│   ├── raw/
│   │   ├── healthy_run_01.csv
│   │   ├── healthy_run_02.csv
│   │   ├── healthy_run_03.csv
│   │   ├── overheating_01.csv
│   │   ├── oil_pressure_drop_01.csv
│   │   ├── oil_pressure_drop_02.csv
│   │   ├── vibration_fault_01.csv
│   │   ├── misfire_01.csv
│   │   └── fuel_mixture_drift_01.csv
│   └── processed/
│       ├── features_train.csv
│       ├── features_val.csv
│       ├── features_test.csv
│       └── scaler_params.json
├── models/
│   ├── isolation_forest.pkl
│   ├── random_forest_classifier.pkl
│   └── scaler.pkl
├── reports/
│   ├── anomaly_metrics.json
│   ├── classification_metrics.json
│   ├── confusion_matrix.png
│   ├── anomaly_score_plot.png
│   ├── feature_importance.png
│   └── shap_summary.png
├── src/
│   ├── __init__.py
│   ├── config.py
│   ├── data_generator.py
│   ├── feature_engineering.py
│   ├── train_anomaly_detector.py
│   ├── train_fault_classifier.py
│   ├── evaluate.py
│   ├── explain.py
│   └── predict.py
├── api/
│   ├── __init__.py
│   └── main.py
├── tests/
│   ├── test_feature_engineering.py
│   ├── test_anomaly_detector.py
│   └── test_fault_classifier.py
├── requirements.txt
├── README.md
└── run_pipeline.py
```

---

## 2. Technology Stack (Exact Versions)

### Core Dependencies — `requirements.txt`

```
# Core
python>=3.10

# Data
numpy==1.26.4
pandas==2.2.2

# ML
scikit-learn==1.4.2
joblib==1.4.2

# Explainability
shap==0.45.1

# Visualization
matplotlib==3.9.0
seaborn==0.13.2
plotly==5.22.0

# API Serving
fastapi==0.111.0
uvicorn==0.30.1
pydantic==2.7.1

# Utilities
python-dotenv==1.0.1
tqdm==4.66.4

# Testing
pytest==8.2.1
```

### Installation Command
```bash
pip install -r requirements.txt
```

---

## 3. Fault Schema & Data Specification

### 3.1 Fault Types (Labels)

| Label | Description |
|---|---|
| `healthy` | Engine operating within normal parameters |
| `overheating` | CHT or EGT rising beyond safe range |
| `oil_pressure_drop` | Oil pressure falling below expected level |
| `vibration_bearing_fault` | Abnormal vibration from bearing wear |
| `misfire_or_injector_fault` | Fuel/air combustion irregularity |
| `fuel_mixture_drift` | Fuel-flow diverging from commanded value |
| `cooling_system_fault` | Cooling inefficiency causing thermal rise |

### 3.2 Fault Severity Scale

| Value | Meaning |
|---|---|
| 0 | Healthy — no fault |
| 1 | Mild degradation — watch |
| 2 | Warning — reduce load |
| 3 | Critical — abort mission |

### 3.3 Mission Phases

| Phase | Description |
|---|---|
| `idle` | Engine at ground idle |
| `taxi` | Low-power ground movement |
| `takeoff` | Max power climb phase |
| `cruise` | Steady level flight |
| `descent` | Power reduction, descent |
| `landing` | Final approach and touchdown |

### 3.4 Raw Telemetry Schema (M3 Output)

Every raw CSV file must contain **exactly these columns** in this order:

| Column | Type | Unit | Normal Range |
|---|---|---|---|
| `timestamp` | int | seconds | 0 → mission_end |
| `rpm` | float | RPM | 3500–4500 |
| `throttle` | float | % | 0–100 |
| `oil_pressure` | float | PSI | 45–70 |
| `oil_temp` | float | °C | 80–110 |
| `cht` | float | °C | 160–220 |
| `egt` | float | °C | 600–750 |
| `manifold_pressure` | float | inHg | 20–30 |
| `vibration` | float | g | 0.1–0.4 |
| `fuel_flow` | float | L/hr | 8–16 |
| `ambient_temp` | float | °C | -10–45 |
| `altitude` | float | meters | 0–5000 |
| `mission_phase` | str | — | see 3.3 |
| `fault_type` | str | — | see 3.1 |
| `fault_active` | int | binary | 0 or 1 |
| `fault_severity` | int | 0–3 | see 3.2 |
| `fault_start_time` | int | seconds | 0 or timestamp |
| `fault_end_time` | int | seconds | 0 or timestamp |

### 3.5 Residual Schema (M2 Output — merged into telemetry)

M2 calculates `actual - physics_model_expected` for each sensor:

| Column | Description |
|---|---|
| `residual_rpm` | rpm − rpm_expected |
| `residual_oil_pressure` | oil_pressure − op_expected |
| `residual_oil_temp` | oil_temp − ot_expected |
| `residual_cht` | cht − cht_expected |
| `residual_egt` | egt − egt_expected |
| `residual_manifold_pressure` | manifold_pressure − mp_expected |
| `residual_vibration` | vibration − vib_expected |
| `residual_fuel_flow` | fuel_flow − ff_expected |
| `health_index` | float 0.0–1.0, 1.0 = perfect health |
| `baseline_rul` | float, estimated Remaining Useful Life in hours |

---

## 4. Step-by-Step Implementation

---

### STEP 1 — `src/config.py` — Central Configuration

**Purpose:** Single source of truth for all constants, paths, and hyperparameters.

**File:** `ml/src/config.py`

```python
"""
config.py
Central configuration for M4 AI/ML baseline.
All paths, hyperparameters, and schema constants live here.
"""
import os
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR       = Path(__file__).resolve().parent.parent          # ml/
DATA_RAW_DIR   = BASE_DIR / "data" / "raw"
DATA_PROC_DIR  = BASE_DIR / "data" / "processed"
MODEL_DIR      = BASE_DIR / "models"
REPORT_DIR     = BASE_DIR / "reports"

# Ensure directories exist
for d in [DATA_RAW_DIR, DATA_PROC_DIR, MODEL_DIR, REPORT_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── Model file paths ────────────────────────────────────────────────────────
IF_MODEL_PATH  = MODEL_DIR / "isolation_forest.pkl"
RFC_MODEL_PATH = MODEL_DIR / "random_forest_classifier.pkl"
SCALER_PATH    = MODEL_DIR / "scaler.pkl"

# ── Telemetry Schema ────────────────────────────────────────────────────────
RAW_SENSOR_COLS = [
    "timestamp", "rpm", "throttle", "oil_pressure", "oil_temp",
    "cht", "egt", "manifold_pressure", "vibration", "fuel_flow",
    "ambient_temp", "altitude", "mission_phase",
    "fault_type", "fault_active", "fault_severity",
    "fault_start_time", "fault_end_time"
]

RESIDUAL_COLS = [
    "residual_rpm", "residual_oil_pressure", "residual_oil_temp",
    "residual_cht", "residual_egt", "residual_manifold_pressure",
    "residual_vibration", "residual_fuel_flow",
    "health_index", "baseline_rul"
]

SENSOR_COLS = [
    "rpm", "throttle", "oil_pressure", "oil_temp", "cht",
    "egt", "manifold_pressure", "vibration", "fuel_flow"
]

# ── Fault Schema ─────────────────────────────────────────────────────────────
FAULT_TYPES = [
    "healthy",
    "overheating",
    "oil_pressure_drop",
    "vibration_bearing_fault",
    "misfire_or_injector_fault",
    "fuel_mixture_drift",
    "cooling_system_fault"
]

FAULT_TYPE_TO_INT = {f: i for i, f in enumerate(FAULT_TYPES)}
INT_TO_FAULT_TYPE = {i: f for i, f in enumerate(FAULT_TYPES)}

MISSION_PHASES = ["idle", "taxi", "takeoff", "cruise", "descent", "landing"]

# ── Normal Operating Ranges (for data generation & validation) ───────────────
NORMAL_RANGES = {
    "rpm":               (3500, 4500),
    "throttle":          (0,    100),
    "oil_pressure":      (45,   70),
    "oil_temp":          (80,   110),
    "cht":               (160,  220),
    "egt":               (600,  750),
    "manifold_pressure": (20,   30),
    "vibration":         (0.1,  0.4),
    "fuel_flow":         (8,    16),
    "ambient_temp":      (-10,  45),
    "altitude":          (0,    5000),
}

# ── Feature Engineering ───────────────────────────────────────────────────────
WINDOW_SIZE   = 30    # seconds / timesteps for rolling features
STEP_SIZE     = 1     # prediction step (1 = every timestep)

# Rolling statistics computed for each sensor + residual column
ROLLING_STATS = ["mean", "std", "min", "max", "last"]

# Slope computed over the window
SLOPE_COLS = ["oil_pressure", "oil_temp", "cht", "vibration",
              "residual_oil_pressure", "residual_vibration"]

# Final feature list fed to both models (built by feature_engineering.py)
FEATURE_COLS = None  # dynamically set after feature engineering runs

# ── Isolation Forest Hyperparameters ──────────────────────────────────────────
IF_PARAMS = {
    "n_estimators":   200,
    "max_samples":    "auto",
    "contamination":  0.05,    # expected ~5% anomaly rate in training data
    "max_features":   1.0,
    "bootstrap":      False,
    "n_jobs":         -1,
    "random_state":   42,
    "verbose":        0
}

# Decision threshold for anomaly label (raw anomaly score from IF)
# Isolation Forest scores: -1 = anomaly, +1 = normal (raw decision_function)
# We threshold the score; tune this on validation data
IF_THRESHOLD = -0.05   # scores below this → anomaly

# ── RandomForestClassifier Hyperparameters ────────────────────────────────────
RFC_PARAMS = {
    "n_estimators":       300,
    "max_depth":          None,
    "min_samples_split":  5,
    "min_samples_leaf":   2,
    "max_features":       "sqrt",
    "class_weight":       "balanced",   # handles class imbalance
    "n_jobs":             -1,
    "random_state":       42,
    "verbose":            0
}

# ── Train/Val/Test Split Ratios ───────────────────────────────────────────────
TRAIN_RATIO = 0.70
VAL_RATIO   = 0.15
TEST_RATIO  = 0.15
# IMPORTANT: Split is performed by full CSV run (mission), NOT by random row.
# This prevents data leakage between windows of the same mission.

# ── Evaluation ────────────────────────────────────────────────────────────────
DETECTION_DELAY_WINDOW = 30    # max seconds after fault start to count as early detection
```

---

### STEP 2 — `src/data_generator.py` — Synthetic Data Generation

**Purpose:** Since M1/M2/M3 modules may not be ready, `data_generator.py` produces realistic synthetic CSV files for all fault types. These are used for training and evaluation.

**File:** `ml/src/data_generator.py`

**What it generates:**
- 3 healthy mission runs × 900 timesteps each
- 1 run per fault type × 900 timesteps, fault injected at t=300 lasting 600 timesteps
- All residuals (simulated as gaussian noise + offset for faults)
- Health index (decays during fault)
- Correct labels

**Functions to implement:**

```python
import numpy as np
import pandas as pd
from pathlib import Path
from src.config import (
    DATA_RAW_DIR, NORMAL_RANGES, MISSION_PHASES,
    FAULT_TYPES, FAULT_TYPE_TO_INT
)

# ─────────────────────────────────────────────────────────────
# FUNCTION: generate_mission_profile(n_steps)
# ─────────────────────────────────────────────────────────────
# Returns: np.array of mission_phase strings of length n_steps.
# Logic: Split n_steps into 6 phases: idle(5%), taxi(5%),
#        takeoff(10%), cruise(60%), descent(10%), landing(10%)

# ─────────────────────────────────────────────────────────────
# FUNCTION: generate_healthy_telemetry(n_steps=900, noise_std=0.02, seed=42)
# ─────────────────────────────────────────────────────────────
# Returns: pd.DataFrame with all RAW_SENSOR_COLS columns.
# Logic:
#   1. Generate base values per sensor within NORMAL_RANGES using np.random.
#   2. Add Gaussian noise (noise_std × range_width) to each sensor.
#   3. Vary values slightly with phase (e.g., rpm higher during takeoff).
#   4. Set fault_type="healthy", fault_active=0, fault_severity=0.
#   5. Set fault_start_time=0, fault_end_time=0.
#   6. Compute synthetic residuals: residual = N(0, 0.5 PSI/°C/etc.)
#   7. health_index = 1.0 throughout.
#   8. baseline_rul = 200.0 (arbitrary healthy RUL).

# ─────────────────────────────────────────────────────────────
# FUNCTION: inject_fault(df, fault_type, fault_start=300, severity=2, seed=42)
# ─────────────────────────────────────────────────────────────
# Returns: pd.DataFrame with fault injected from fault_start to end.
# Logic per fault_type:
#
#   "overheating":
#     cht += ramp from 0 to +60°C (linear over 100 steps), then +70°C
#     egt += ramp from 0 to +80°C
#     residual_cht = actual_cht - normal_cht → positive
#     residual_egt = actual_egt - normal_egt → positive
#     health_index decays from 1.0 to 0.4 linearly
#
#   "oil_pressure_drop":
#     oil_pressure -= ramp from 0 to -20 PSI
#     oil_temp += ramp from 0 to +15°C (pressure loss → temp rise)
#     residual_oil_pressure = actual - expected → strongly negative
#     residual_oil_temp → mildly positive
#     health_index decays from 1.0 to 0.3
#
#   "vibration_bearing_fault":
#     vibration += ramp from 0 to +0.8g
#     rpm fluctuation increases ±200 RPM noise
#     residual_vibration → strongly positive
#     health_index decays from 1.0 to 0.4
#
#   "misfire_or_injector_fault":
#     egt += intermittent spikes ±50°C (every 5 steps)
#     fuel_flow fluctuates ±2 L/hr
#     rpm drops intermittently by -300 RPM
#     residual_egt fluctuates ± strongly
#     health_index decays from 1.0 to 0.5
#
#   "fuel_mixture_drift":
#     fuel_flow += ramp from 0 to +4 L/hr (rich mixture)
#     egt += ramp +40°C
#     residual_fuel_flow → strongly positive
#     health_index decays from 1.0 to 0.6
#
#   "cooling_system_fault":
#     cht += ramp +50°C
#     oil_temp += ramp +20°C
#     residual_cht → strongly positive
#     health_index decays from 1.0 to 0.45
#
# After injection:
#   Set fault_type = fault_type for rows from fault_start onward
#   Set fault_active = 1
#   Set fault_severity = severity
#   Set fault_start_time = fault_start
#   Set fault_end_time = n_steps

# ─────────────────────────────────────────────────────────────
# FUNCTION: save_run(df, filename)
# ─────────────────────────────────────────────────────────────
# Saves df as CSV to DATA_RAW_DIR / filename.

# ─────────────────────────────────────────────────────────────
# MAIN: generate_all_datasets()
# ─────────────────────────────────────────────────────────────
# Calls:
#   save_run(generate_healthy_telemetry(seed=1), "healthy_run_01.csv")
#   save_run(generate_healthy_telemetry(seed=2), "healthy_run_02.csv")
#   save_run(generate_healthy_telemetry(seed=3), "healthy_run_03.csv")
#   For each fault in FAULT_TYPES[1:]:
#       base = generate_healthy_telemetry(seed=fault_seed)
#       faulty = inject_fault(base, fault_type=fault, fault_start=300)
#       save_run(faulty, f"{fault}_01.csv")
# Prints confirmation after each file is saved.

if __name__ == "__main__":
    generate_all_datasets()
    print("All synthetic datasets generated.")
```

**Run command:** `python -m src.data_generator`

---

### STEP 3 — `src/feature_engineering.py` — Feature Engineering

**Purpose:** Transform raw telemetry + residuals into ML-ready windowed features.

**File:** `ml/src/feature_engineering.py`

**Detailed logic:**

```python
"""
feature_engineering.py
Transforms raw telemetry CSVs into windowed feature matrices for ML training.

Pipeline:
  1. load_and_merge_csv(filepath)        → raw DataFrame
  2. clean_dataframe(df)                 → cleaned DataFrame  
  3. encode_mission_phase(df)            → adds one-hot phase columns
  4. compute_rolling_features(df)        → adds mean/std/min/max/last per window
  5. compute_slope_features(df)          → adds slope over window for key cols
  6. create_labels(df)                   → adds label_anomaly, label_fault_int
  7. drop_warmup_rows(df)                → removes first WINDOW_SIZE rows
  8. build_feature_matrix(raw_csvs)      → full pipeline, returns X, y_anomaly, y_fault
  9. split_by_run(file_list)             → train/val/test split by full run
  10. save_processed(X_train, X_val, X_test, y_train_a, y_train_f, ...)
"""

import numpy as np
import pandas as pd
import joblib
from sklearn.preprocessing import StandardScaler
from src.config import *

# ─────────────────────────────────────────────────────────────
# FUNCTION: load_and_merge_csv(filepath) → pd.DataFrame
# ─────────────────────────────────────────────────────────────
# Steps:
#   df = pd.read_csv(filepath)
#   Assert all RAW_SENSOR_COLS present.
#   If residual columns NOT present: compute synthetic residuals
#     residual_X = df[X] + np.random.normal(0, small_noise, len(df))
#     health_index = 1.0 (healthy) or computed from fault_severity
#   Return merged df.

# ─────────────────────────────────────────────────────────────
# FUNCTION: clean_dataframe(df) → pd.DataFrame
# ─────────────────────────────────────────────────────────────
# Steps:
#   1. Forward-fill missing values: df.fillna(method='ffill').fillna(method='bfill')
#   2. Clip sensor values to ±3× their NORMAL_RANGES width (remove wild outliers).
#   3. Sort by timestamp ascending.
#   4. Reset index.

# ─────────────────────────────────────────────────────────────
# FUNCTION: encode_mission_phase(df) → pd.DataFrame
# ─────────────────────────────────────────────────────────────
# One-hot encode mission_phase into binary columns:
#   mission_phase_idle, mission_phase_taxi, mission_phase_takeoff,
#   mission_phase_cruise, mission_phase_descent, mission_phase_landing
# Drop original mission_phase string column.

# ─────────────────────────────────────────────────────────────
# FUNCTION: compute_rolling_features(df, window=WINDOW_SIZE) → pd.DataFrame
# ─────────────────────────────────────────────────────────────
# For each col in (SENSOR_COLS + RESIDUAL_COLS excluding health_index and baseline_rul):
#   rolled = df[col].rolling(window=window, min_periods=1)
#   df[f"{col}_mean_{window}s"]  = rolled.mean()
#   df[f"{col}_std_{window}s"]   = rolled.std().fillna(0)
#   df[f"{col}_min_{window}s"]   = rolled.min()
#   df[f"{col}_max_{window}s"]   = rolled.max()
#   df[f"{col}_last"]            = df[col]  (raw value as "last")
# Returns df with all new columns.

# ─────────────────────────────────────────────────────────────
# FUNCTION: compute_slope_features(df, window=WINDOW_SIZE) → pd.DataFrame
# ─────────────────────────────────────────────────────────────
# For each col in SLOPE_COLS:
#   Compute linear regression slope over last `window` points.
#   Use np.polyfit(range(window), values[-window:], 1)[0] per row
#   OR use rolling().apply(lambda x: np.polyfit(range(len(x)), x, 1)[0])
#   Store as df[f"{col}_slope_{window}s"]

# ─────────────────────────────────────────────────────────────
# FUNCTION: create_labels(df) → pd.DataFrame
# ─────────────────────────────────────────────────────────────
# df["label_anomaly"]   = df["fault_active"].astype(int)
# df["label_fault_int"] = df["fault_type"].map(FAULT_TYPE_TO_INT)
# Return df.

# ─────────────────────────────────────────────────────────────
# FUNCTION: drop_warmup_rows(df, window=WINDOW_SIZE) → pd.DataFrame
# ─────────────────────────────────────────────────────────────
# Drop first `window` rows since rolling stats are unreliable there.
# df = df.iloc[window:].reset_index(drop=True)

# ─────────────────────────────────────────────────────────────
# FUNCTION: get_feature_columns(df) → List[str]
# ─────────────────────────────────────────────────────────────
# Returns all column names EXCEPT:
#   timestamp, mission_phase, fault_type, fault_active, fault_severity,
#   fault_start_time, fault_end_time, label_anomaly, label_fault_int
# This list becomes the definitive FEATURE_COLS.

# ─────────────────────────────────────────────────────────────
# FUNCTION: build_feature_matrix(csv_paths: List[Path]) → Dict
# ─────────────────────────────────────────────────────────────
# Returns: {
#   "X":          np.array (N, F),
#   "y_anomaly":  np.array (N,) int,
#   "y_fault":    np.array (N,) int,
#   "run_ids":    np.array (N,) int,  ← which run index each row came from
#   "feature_names": List[str]
# }
# Steps:
#   frames = []
#   for i, csv_path in enumerate(csv_paths):
#       df = load_and_merge_csv(csv_path)
#       df = clean_dataframe(df)
#       df = encode_mission_phase(df)
#       df = compute_rolling_features(df)
#       df = compute_slope_features(df)
#       df = create_labels(df)
#       df = drop_warmup_rows(df)
#       df["run_id"] = i
#       frames.append(df)
#   combined = pd.concat(frames, ignore_index=True)
#   feature_names = get_feature_columns(combined)
#   X = combined[feature_names].values
#   y_anomaly = combined["label_anomaly"].values
#   y_fault   = combined["label_fault_int"].values
#   run_ids   = combined["run_id"].values
#   return {...}

# ─────────────────────────────────────────────────────────────
# FUNCTION: split_by_run(data_dict, healthy_csvs, fault_csvs) → Dict
# ─────────────────────────────────────────────────────────────
# Split strategy: by full run (not by row) to prevent data leakage.
# Healthy runs:
#   run_01 → train, run_02 → train, run_03 → val
# Fault runs:
#   _01.csv → train (70%), _02.csv (if exists) → val, else val from same run last 15%
# Returns: {
#   "X_train", "X_val", "X_test",
#   "y_train_anomaly", "y_val_anomaly", "y_test_anomaly",
#   "y_train_fault", "y_val_fault", "y_test_fault",
#   "feature_names"
# }

# ─────────────────────────────────────────────────────────────
# FUNCTION: fit_and_save_scaler(X_train, feature_names) → StandardScaler
# ─────────────────────────────────────────────────────────────
# scaler = StandardScaler()
# scaler.fit(X_train)
# joblib.dump(scaler, SCALER_PATH)
# Save scaler_params.json with mean and std arrays.
# Return scaler.

# ─────────────────────────────────────────────────────────────
# FUNCTION: save_processed_splits(splits_dict)
# ─────────────────────────────────────────────────────────────
# Save each X/y array as CSV to DATA_PROC_DIR:
#   features_train.csv, features_val.csv, features_test.csv
# Include y_anomaly and y_fault as the last two columns.

if __name__ == "__main__":
    # Collect all raw CSVs
    all_csvs = sorted(DATA_RAW_DIR.glob("*.csv"))
    healthy_csvs = [f for f in all_csvs if "healthy" in f.name]
    fault_csvs   = [f for f in all_csvs if "healthy" not in f.name]
    
    data_dict = build_feature_matrix(all_csvs)
    splits    = split_by_run(data_dict, healthy_csvs, fault_csvs)
    scaler    = fit_and_save_scaler(splits["X_train"], data_dict["feature_names"])
    save_processed_splits(splits)
    print(f"Feature engineering complete. Feature count: {len(data_dict['feature_names'])}")
    print(f"Train: {splits['X_train'].shape}, Val: {splits['X_val'].shape}, Test: {splits['X_test'].shape}")
```

**Expected output:**
- ~150–200 engineered features per timestep
- `scaler.pkl` saved to `models/`
- `features_train.csv`, `features_val.csv`, `features_test.csv` in `data/processed/`

---

### STEP 4 — `src/train_anomaly_detector.py` — Isolation Forest Training

**Purpose:** Train the Isolation Forest on **healthy data only**, then evaluate on test set.

**File:** `ml/src/train_anomaly_detector.py`

```python
"""
train_anomaly_detector.py
Trains Isolation Forest anomaly detector on healthy engine telemetry.

Algorithm: Isolation Forest (scikit-learn)
  - Builds random trees that isolate observations.
  - Anomalies are isolated faster (shorter path length → higher anomaly score).
  - Trained ONLY on healthy data (semi-supervised anomaly detection).
  - At prediction: raw score from decision_function(X).
  - Threshold tuned on validation set to minimize false alarm rate.

Steps:
  1. Load scaler and processed split data.
  2. Filter X_train to healthy rows only (y_train_anomaly == 0).
  3. Scale X_healthy using loaded scaler.
  4. Train IsolationForest with IF_PARAMS.
  5. Save model to IF_MODEL_PATH.
  6. Evaluate on scaled X_val and X_test.
  7. Tune threshold on val set using F1-score optimization.
  8. Save anomaly_metrics.json.
  9. Plot anomaly scores over time and save anomaly_score_plot.png.
"""

import numpy as np
import pandas as pd
import joblib
import json
import matplotlib.pyplot as plt
from sklearn.ensemble import IsolationForest
from sklearn.metrics import (
    precision_score, recall_score, f1_score,
    confusion_matrix, classification_report
)
from src.config import *

# ─────────────────────────────────────────────────────────────
# FUNCTION: load_splits() → Dict
# ─────────────────────────────────────────────────────────────
# Loads features_train.csv, features_val.csv, features_test.csv.
# Reads feature_names from header (all cols except last 2).
# Returns dict with X_train, X_val, X_test, y_train_anomaly,
#   y_val_anomaly, y_test_anomaly, y_train_fault, y_val_fault,
#   y_test_fault, feature_names.

# ─────────────────────────────────────────────────────────────
# FUNCTION: train_isolation_forest(X_healthy_scaled) → IsolationForest
# ─────────────────────────────────────────────────────────────
# if = IsolationForest(**IF_PARAMS)
# if.fit(X_healthy_scaled)
# joblib.dump(if, IF_MODEL_PATH)
# Return if.

# ─────────────────────────────────────────────────────────────
# FUNCTION: tune_threshold(model, X_val_scaled, y_val_anomaly) → float
# ─────────────────────────────────────────────────────────────
# Get raw scores: scores = model.decision_function(X_val_scaled)
# Try thresholds from np.linspace(scores.min(), scores.max(), 200)
# For each threshold:
#   y_pred = (scores < threshold).astype(int)
#   f1 = f1_score(y_val_anomaly, y_pred, zero_division=0)
# Return threshold with best F1.
# Print best threshold and val F1.

# ─────────────────────────────────────────────────────────────
# FUNCTION: evaluate_anomaly_detector(model, threshold, X_test_scaled, y_test_anomaly) → Dict
# ─────────────────────────────────────────────────────────────
# scores = model.decision_function(X_test_scaled)
# y_pred = (scores < threshold).astype(int)
# metrics = {
#   "precision": precision_score(y_test_anomaly, y_pred),
#   "recall":    recall_score(y_test_anomaly, y_pred),
#   "f1_score":  f1_score(y_test_anomaly, y_pred),
#   "false_alarm_rate": np.sum((y_pred == 1) & (y_test_anomaly == 0)) / np.sum(y_test_anomaly == 0),
#   "threshold_used": float(threshold)
# }
# Save metrics to REPORT_DIR / "anomaly_metrics.json"
# Print classification_report.
# Return metrics.

# ─────────────────────────────────────────────────────────────
# FUNCTION: compute_detection_delay(model, threshold, X_test_scaled, y_test_anomaly, timestamps) → float
# ─────────────────────────────────────────────────────────────
# Find first index where y_test_anomaly switches from 0 → 1 (fault_start).
# Find first index where y_pred switches from 0 → 1 after fault_start.
# detection_delay = pred_fault_start - actual_fault_start (in timesteps/seconds)
# Return detection_delay (positive = delay, negative = early detection).

# ─────────────────────────────────────────────────────────────
# FUNCTION: plot_anomaly_scores(scores, y_true, threshold, savepath)
# ─────────────────────────────────────────────────────────────
# Plot raw anomaly score timeline.
# Shade red where y_true == 1 (actual fault).
# Draw horizontal line at threshold.
# Save to REPORT_DIR / "anomaly_score_plot.png"
# Use matplotlib with figsize=(14, 4).

if __name__ == "__main__":
    splits = load_splits()
    scaler = joblib.load(SCALER_PATH)
    
    # Scale data
    X_train_sc = scaler.transform(splits["X_train"])
    X_val_sc   = scaler.transform(splits["X_val"])
    X_test_sc  = scaler.transform(splits["X_test"])
    
    # Filter to healthy only for training
    mask_healthy = splits["y_train_anomaly"] == 0
    X_healthy_sc = X_train_sc[mask_healthy]
    print(f"Training IF on {X_healthy_sc.shape[0]} healthy samples.")
    
    model     = train_isolation_forest(X_healthy_sc)
    threshold = tune_threshold(model, X_val_sc, splits["y_val_anomaly"])
    metrics   = evaluate_anomaly_detector(model, threshold, X_test_sc, splits["y_test_anomaly"])
    
    scores_test = model.decision_function(X_test_sc)
    plot_anomaly_scores(scores_test, splits["y_test_anomaly"], threshold,
                        REPORT_DIR / "anomaly_score_plot.png")
    
    print(f"\nAnomaly Detection Metrics: {metrics}")
    print(f"Model saved to {IF_MODEL_PATH}")
```

**Expected output files:**
- `models/isolation_forest.pkl`
- `reports/anomaly_metrics.json` → `{"precision": 0.xx, "recall": 0.xx, "f1_score": 0.xx, "false_alarm_rate": 0.xx}`
- `reports/anomaly_score_plot.png`

---

### STEP 5 — `src/train_fault_classifier.py` — RandomForestClassifier Training

**Purpose:** Train a supervised multi-class fault classifier on labeled telemetry.

**File:** `ml/src/train_fault_classifier.py`

```python
"""
train_fault_classifier.py
Trains RandomForestClassifier for multi-class fault diagnosis.

Classes: healthy, overheating, oil_pressure_drop,
         vibration_bearing_fault, misfire_or_injector_fault,
         fuel_mixture_drift, cooling_system_fault

Training strategy:
  - Uses ALL data (healthy + all fault types).
  - class_weight="balanced" to handle class imbalance.
  - Trains on X_train, evaluates on X_val and X_test.
  - Saves model, metrics, confusion matrix, feature importance plot.
"""

import numpy as np
import pandas as pd
import joblib
import json
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score, classification_report,
    confusion_matrix, f1_score, precision_score, recall_score
)
from src.config import *

# ─────────────────────────────────────────────────────────────
# FUNCTION: train_random_forest(X_train_sc, y_train_fault) → RandomForestClassifier
# ─────────────────────────────────────────────────────────────
# rfc = RandomForestClassifier(**RFC_PARAMS)
# rfc.fit(X_train_sc, y_train_fault)
# joblib.dump(rfc, RFC_MODEL_PATH)
# Return rfc.

# ─────────────────────────────────────────────────────────────
# FUNCTION: evaluate_classifier(rfc, X_test_sc, y_test_fault, feature_names) → Dict
# ─────────────────────────────────────────────────────────────
# y_pred = rfc.predict(X_test_sc)
# y_prob = rfc.predict_proba(X_test_sc)
# metrics = {
#   "accuracy": accuracy_score(y_test_fault, y_pred),
#   "macro_f1": f1_score(y_test_fault, y_pred, average="macro"),
#   "weighted_f1": f1_score(y_test_fault, y_pred, average="weighted"),
#   "per_class_report": classification_report(y_test_fault, y_pred,
#                         target_names=FAULT_TYPES, output_dict=True)
# }
# Save to REPORT_DIR / "classification_metrics.json"
# Print full classification report.
# Return metrics.

# ─────────────────────────────────────────────────────────────
# FUNCTION: plot_confusion_matrix(y_true, y_pred, savepath)
# ─────────────────────────────────────────────────────────────
# cm = confusion_matrix(y_true, y_pred)
# plt.figure(figsize=(10, 8))
# sns.heatmap(cm, annot=True, fmt="d", xticklabels=FAULT_TYPES, yticklabels=FAULT_TYPES,
#             cmap="Blues")
# plt.xlabel("Predicted"); plt.ylabel("True")
# plt.title("Fault Classification Confusion Matrix")
# plt.tight_layout()
# plt.savefig(savepath, dpi=150)

# ─────────────────────────────────────────────────────────────
# FUNCTION: plot_feature_importance(rfc, feature_names, top_n=20, savepath)
# ─────────────────────────────────────────────────────────────
# importances = rfc.feature_importances_
# indices = np.argsort(importances)[-top_n:][::-1]
# plt.figure(figsize=(10, 6))
# plt.barh([feature_names[i] for i in indices], importances[indices])
# plt.xlabel("Importance"); plt.title(f"Top {top_n} Feature Importances")
# plt.tight_layout()
# plt.savefig(savepath, dpi=150)

# ─────────────────────────────────────────────────────────────
# FUNCTION: get_top_features(rfc, feature_names, n=5) → List[str]
# ─────────────────────────────────────────────────────────────
# Return top-n feature names sorted by importance descending.

if __name__ == "__main__":
    splits = load_splits()
    scaler = joblib.load(SCALER_PATH)
    
    X_train_sc = scaler.transform(splits["X_train"])
    X_val_sc   = scaler.transform(splits["X_val"])
    X_test_sc  = scaler.transform(splits["X_test"])
    
    rfc     = train_random_forest(X_train_sc, splits["y_train_fault"])
    metrics = evaluate_classifier(rfc, X_test_sc, splits["y_test_fault"], splits["feature_names"])
    
    y_pred_test = rfc.predict(X_test_sc)
    plot_confusion_matrix(splits["y_test_fault"], y_pred_test,
                          REPORT_DIR / "confusion_matrix.png")
    plot_feature_importance(rfc, splits["feature_names"], top_n=20,
                            savepath=REPORT_DIR / "feature_importance.png")
    
    print(f"\nClassification Metrics: {metrics}")
    print(f"Model saved to {RFC_MODEL_PATH}")
```

**Expected output files:**
- `models/random_forest_classifier.pkl`
- `reports/classification_metrics.json`
- `reports/confusion_matrix.png`
- `reports/feature_importance.png`

---

### STEP 6 — `src/explain.py` — Explainability Layer

**Purpose:** Attach human-readable explanations to every prediction using feature importance + SHAP + rule templates.

**File:** `ml/src/explain.py`

```python
"""
explain.py
Generates explanations for M4 predictions.

Two-layer explainability:
  Layer 1: RandomForest feature importance (fast, always available)
  Layer 2: SHAP values (richer, requires shap library)
  Layer 3: Rule-based templates (human-readable for dashboard)
"""

import numpy as np
import pandas as pd
import shap
import joblib
import matplotlib.pyplot as plt
from src.config import *

# ─────────────────────────────────────────────────────────────
# FUNCTION: load_explainer(rfc, X_background) → shap.TreeExplainer
# ─────────────────────────────────────────────────────────────
# explainer = shap.TreeExplainer(rfc, X_background[:100])
# Return explainer.
# (Use subsample of background data for speed.)

# ─────────────────────────────────────────────────────────────
# FUNCTION: get_shap_values(explainer, X_window_scaled) → np.array
# ─────────────────────────────────────────────────────────────
# shap_vals = explainer.shap_values(X_window_scaled)
# Returns array of shape (n_classes, n_features) for one sample.

# ─────────────────────────────────────────────────────────────
# FUNCTION: get_top_shap_features(shap_vals, feature_names, predicted_class, n=3) → List[str]
# ─────────────────────────────────────────────────────────────
# shap_for_class = shap_vals[predicted_class]
# top_indices = np.argsort(np.abs(shap_for_class))[-n:][::-1]
# Return [feature_names[i] for i in top_indices]

# ─────────────────────────────────────────────────────────────
# RULE TEMPLATES (stored in dict)
# ─────────────────────────────────────────────────────────────
EXPLANATION_TEMPLATES = {
    "healthy": "Engine is operating within normal parameters. All sensor readings and residuals are within expected range.",
    
    "overheating": (
        "Overheating detected. Cylinder head temperature and/or exhaust gas temperature are rising "
        "above expected values. Residuals for CHT ({cht_res:.1f}°C) and EGT ({egt_res:.1f}°C) are strongly positive. "
        "Recommend reducing power and checking cooling system."
    ),
    
    "oil_pressure_drop": (
        "Oil pressure degradation detected. Measured oil pressure is {op:.1f} PSI, "
        "which is {op_res:.1f} PSI below physics-model expectation and trending downward "
        "(slope: {op_slope:.2f} PSI/s). Oil temperature is also rising. "
        "Recommend reducing load and scheduling oil system inspection."
    ),
    
    "vibration_bearing_fault": (
        "Abnormal vibration detected. Vibration level is {vib:.2f}g, "
        "which is {vib_res:.2f}g above expected ({vib_slope:.3f}g/s trend). "
        "This pattern is consistent with bearing wear or mechanical imbalance. "
        "Recommend immediate inspection of rotating components."
    ),
    
    "misfire_or_injector_fault": (
        "Combustion irregularity detected. EGT is showing intermittent spikes (residual: {egt_res:.1f}°C) "
        "and RPM is fluctuating. Fuel flow shows irregular delivery pattern. "
        "Possible injector fault or ignition misfire. Recommend engine inspection."
    ),
    
    "fuel_mixture_drift": (
        "Fuel mixture drift detected. Fuel flow is {ff:.1f} L/hr, "
        "which is {ff_res:.1f} L/hr above commanded value. "
        "EGT trending upward indicates rich mixture condition. "
        "Recommend checking fuel metering system and mixture control."
    ),
    
    "cooling_system_fault": (
        "Cooling system degradation detected. CHT residual is {cht_res:.1f}°C above expected. "
        "Oil temperature is also elevated ({ot_res:.1f}°C residual). "
        "Cooling efficiency has dropped. Recommend coolant system check."
    )
}

# ─────────────────────────────────────────────────────────────
# FUNCTION: format_explanation(fault_type, sensor_values, top_features) → str
# ─────────────────────────────────────────────────────────────
# Use EXPLANATION_TEMPLATES[fault_type].format(**sensor_values)
# Append top_features as "Key sensors: {feat1}, {feat2}, {feat3}"
# Return formatted string.

# ─────────────────────────────────────────────────────────────
# FUNCTION: build_explanation(fault_type, confidence, feature_names, X_window_scaled,
#                             explainer=None, sensor_values=None) → Dict
# ─────────────────────────────────────────────────────────────
# If explainer available:
#   shap_vals = get_shap_values(explainer, X_window_scaled)
#   top_features = get_top_shap_features(shap_vals, feature_names, fault_type_int)
#   method = "shap"
# Else:
#   top_features = [feature_names ranked by rfc.feature_importances_][:3]
#   method = "feature_importance"
# 
# explanation_text = format_explanation(fault_type, sensor_values or {}, top_features)
# Return {
#   "fault_type": fault_type,
#   "confidence": float(confidence),
#   "top_features": top_features,
#   "explanation": explanation_text,
#   "method": method
# }

# ─────────────────────────────────────────────────────────────
# FUNCTION: plot_shap_summary(explainer, X_sample_scaled, feature_names, savepath)
# ─────────────────────────────────────────────────────────────
# shap_vals = explainer.shap_values(X_sample_scaled)
# shap.summary_plot(shap_vals, X_sample_scaled, feature_names=feature_names,
#                   class_names=FAULT_TYPES, show=False)
# plt.savefig(savepath, dpi=150, bbox_inches="tight")
# Save to REPORT_DIR / "shap_summary.png"
```

---

### STEP 7 — `src/predict.py` — Unified Prediction Function

**Purpose:** Single clean function that M5 dashboard and M6 API call.

**File:** `ml/src/predict.py`

```python
"""
predict.py
Main prediction interface for M4 module.

Entry point: predict_engine_health(window_df) → Dict

Input:
  window_df: pd.DataFrame with last WINDOW_SIZE rows of telemetry + residuals.
             Must contain all RAW_SENSOR_COLS + RESIDUAL_COLS columns.

Output:
{
  "timestamp":    str  (ISO 8601),
  "is_anomaly":   bool,
  "anomaly_score": float (higher = more anomalous, range 0-1 normalized),
  "health_state": str  ("normal" | "degrading" | "critical"),
  "fault_type":   str  (from FAULT_TYPES),
  "confidence":   float (0.0 - 1.0),
  "top_features": List[str] (top 3 feature names),
  "explanation":  str  (human-readable),
  "severity":     int  (0-3)
}
"""

import numpy as np
import pandas as pd
import joblib
from datetime import datetime
from src.config import *
from src.feature_engineering import (
    clean_dataframe, encode_mission_phase,
    compute_rolling_features, compute_slope_features,
    create_labels, get_feature_columns
)
from src.explain import build_explanation

# ─── Load models once at module import (cached) ────────────────────────────
_scaler  = joblib.load(SCALER_PATH)
_if_model = joblib.load(IF_MODEL_PATH)
_rfc     = joblib.load(RFC_MODEL_PATH)

# Load explainer (build from small background sample saved during training)
# _explainer = ... (optional, load if shap background saved)

# ─────────────────────────────────────────────────────────────
# FUNCTION: preprocess_window(window_df) → np.array (1, n_features)
# ─────────────────────────────────────────────────────────────
# Apply same pipeline as feature_engineering on the window:
#   clean → encode_phase → rolling → slope → get_features → scale
# Return scaled feature vector for the LAST row only.
# (The window is used for rolling stats; only last row is predicted.)

# ─────────────────────────────────────────────────────────────
# FUNCTION: compute_health_state(anomaly_score, if_threshold, confidence) → str
# ─────────────────────────────────────────────────────────────
# if anomaly_score > 0.7:  return "critical"
# elif anomaly_score > 0.4: return "degrading"
# else: return "normal"

# ─────────────────────────────────────────────────────────────
# FUNCTION: normalize_anomaly_score(raw_decision_score) → float (0-1)
# ─────────────────────────────────────────────────────────────
# IF decision_function returns negative for anomalies.
# Normalize to 0-1 where 1 = most anomalous:
#   normalized = 1 - (raw_score - score_min) / (score_max - score_min)
# Use pre-computed score_min/max from training (save these during training).

# ─────────────────────────────────────────────────────────────
# MAIN FUNCTION: predict_engine_health(window_df) → Dict
# ─────────────────────────────────────────────────────────────
def predict_engine_health(window_df: pd.DataFrame) -> dict:
    """
    Main M4 prediction interface.
    
    Args:
        window_df: DataFrame with last WINDOW_SIZE rows of engine telemetry.
                   Must contain RAW_SENSOR_COLS + RESIDUAL_COLS.
    
    Returns:
        dict with keys: timestamp, is_anomaly, anomaly_score, health_state,
                        fault_type, confidence, top_features, explanation, severity
    """
    # 1. Preprocess
    X_scaled = preprocess_window(window_df)
    
    # 2. Anomaly detection
    raw_score    = _if_model.decision_function(X_scaled)[0]
    is_anomaly   = bool(raw_score < IF_THRESHOLD)
    anomaly_score = normalize_anomaly_score(raw_score)
    health_state = compute_health_state(anomaly_score, IF_THRESHOLD, None)
    
    # 3. Fault classification (always run, but weight by is_anomaly)
    proba        = _rfc.predict_proba(X_scaled)[0]
    fault_int    = int(np.argmax(proba))
    fault_type   = INT_TO_FAULT_TYPE[fault_int]
    confidence   = float(proba[fault_int])
    
    # If not anomaly, override to healthy with original IF confidence
    if not is_anomaly:
        fault_type = "healthy"
        confidence = float(1 - anomaly_score)
    
    # 4. Determine severity from fault type + anomaly score
    if not is_anomaly:
        severity = 0
    elif anomaly_score < 0.4:
        severity = 1
    elif anomaly_score < 0.7:
        severity = 2
    else:
        severity = 3
    
    # 5. Build explanation
    feature_names = get_feature_columns_cached()
    sensor_vals   = extract_sensor_values(window_df.iloc[-1])
    explanation   = build_explanation(
        fault_type   = fault_type,
        confidence   = confidence,
        feature_names = feature_names,
        X_window_scaled = X_scaled,
        sensor_values = sensor_vals
    )
    
    return {
        "timestamp":     datetime.utcnow().isoformat(),
        "is_anomaly":    is_anomaly,
        "anomaly_score": round(anomaly_score, 4),
        "health_state":  health_state,
        "fault_type":    fault_type,
        "confidence":    round(confidence, 4),
        "top_features":  explanation["top_features"],
        "explanation":   explanation["explanation"],
        "severity":      severity
    }
```

---

### STEP 8 — `src/evaluate.py` — Comprehensive Evaluation

**Purpose:** Run all evaluation metrics for both models and generate reports.

**File:** `ml/src/evaluate.py`

```python
"""
evaluate.py
Runs full evaluation suite for both M4 models.

Outputs:
  - anomaly_metrics.json
  - classification_metrics.json
  - confusion_matrix.png
  - anomaly_score_plot.png
  - feature_importance.png
  - shap_summary.png (if SHAP available)

Metrics computed:
  Anomaly Detection:
    - Precision, Recall, F1-score
    - False Alarm Rate (healthy windows misclassified as fault)
    - Detection Delay (timesteps from fault injection to first alert)
    - ROC-AUC curve
    - Precision-Recall curve

  Fault Classification:
    - Accuracy
    - Per-class Precision, Recall, F1
    - Weighted F1, Macro F1
    - Confusion matrix (absolute + normalized)
    - Top-20 feature importances
"""

import numpy as np
import pandas as pd
import joblib
import json
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import (
    roc_auc_score, roc_curve,
    precision_recall_curve, average_precision_score
)
from src.config import *

# ─────────────────────────────────────────────────────────────
# FUNCTION: run_full_evaluation()
# ─────────────────────────────────────────────────────────────
# Loads all models, scaler, and test splits.
# Runs both evaluations.
# Saves all reports.

# ─────────────────────────────────────────────────────────────
# FUNCTION: compute_detection_delay(scores, y_true, threshold, step_size=STEP_SIZE) → float
# ─────────────────────────────────────────────────────────────
# Find first fault_start index in y_true (0→1 transition).
# Find first model detection index (score < threshold after fault_start).
# delay = detection_index - fault_start_index (in seconds assuming 1s steps)
# Return delay. (Negative = pre-detection before fault worsens, positive = late.)

# ─────────────────────────────────────────────────────────────
# FUNCTION: plot_roc_curve(y_true, scores, savepath)
# ─────────────────────────────────────────────────────────────
# (use -scores since higher = more anomalous after normalization)
# fpr, tpr, _ = roc_curve(y_true, -scores)
# auc = roc_auc_score(y_true, -scores)
# Plot and save.

# ─────────────────────────────────────────────────────────────
# FUNCTION: print_summary_table(anomaly_metrics, clf_metrics)
# ─────────────────────────────────────────────────────────────
# Prints formatted table of all metrics to stdout.

if __name__ == "__main__":
    run_full_evaluation()
    print("Evaluation complete. Reports saved to reports/")
```

---

### STEP 9 — `api/main.py` — FastAPI REST Endpoint

**Purpose:** Expose M4 predictions as an HTTP API for M5 dashboard and M6 integration.

**File:** `ml/api/main.py`

```python
"""
main.py — FastAPI application for M4 AI/ML module.

Endpoints:
  POST /predict          → predict_engine_health for a window of telemetry
  GET  /health           → service health check
  GET  /model-info       → model version and feature count
  POST /predict-stream   → streaming prediction (for live telemetry)

Authentication: None (internal service, assumed within M6 secure perimeter)
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import pandas as pd
import numpy as np
from src.predict import predict_engine_health
from src.config import WINDOW_SIZE, FAULT_TYPES

app = FastAPI(
    title       = "M4 AI/ML Engine Health API",
    description = "Anomaly detection and fault classification for MALE UAV aero piston engine digital twin.",
    version     = "1.0.0-baseline"
)

# Allow M5 dashboard to call from browser
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Request Schema ──────────────────────────────────────────────────────────
class TelemetryRow(BaseModel):
    """Single timestep of engine telemetry + residuals."""
    timestamp:              int
    rpm:                    float
    throttle:               float
    oil_pressure:           float
    oil_temp:               float
    cht:                    float
    egt:                    float
    manifold_pressure:      float
    vibration:              float
    fuel_flow:              float
    ambient_temp:           float
    altitude:               float
    mission_phase:          str
    # Residuals (optional — if not provided, set to 0.0)
    residual_rpm:           Optional[float] = 0.0
    residual_oil_pressure:  Optional[float] = 0.0
    residual_oil_temp:      Optional[float] = 0.0
    residual_cht:           Optional[float] = 0.0
    residual_egt:           Optional[float] = 0.0
    residual_manifold_pressure: Optional[float] = 0.0
    residual_vibration:     Optional[float] = 0.0
    residual_fuel_flow:     Optional[float] = 0.0
    health_index:           Optional[float] = 1.0
    baseline_rul:           Optional[float] = 200.0

class PredictRequest(BaseModel):
    """Window of WINDOW_SIZE telemetry rows."""
    window: List[TelemetryRow]

# ─── Response Schema ─────────────────────────────────────────────────────────
class PredictResponse(BaseModel):
    timestamp:     str
    is_anomaly:    bool
    anomaly_score: float
    health_state:  str     # "normal" | "degrading" | "critical"
    fault_type:    str
    confidence:    float
    top_features:  List[str]
    explanation:   str
    severity:      int     # 0-3

# ─── Endpoints ───────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "service": "M4 AI/ML Engine Health"}

@app.get("/model-info")
def model_info():
    return {
        "models": ["IsolationForest", "RandomForestClassifier"],
        "fault_types": FAULT_TYPES,
        "window_size": WINDOW_SIZE,
        "version": "1.0.0-baseline"
    }

@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest):
    if len(req.window) < WINDOW_SIZE:
        raise HTTPException(
            status_code=422,
            detail=f"Window must contain at least {WINDOW_SIZE} rows. Got {len(req.window)}."
        )
    # Convert to DataFrame
    window_df = pd.DataFrame([row.model_dump() for row in req.window])
    result = predict_engine_health(window_df)
    return PredictResponse(**result)
```

**Run command:** `uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload`

**API URL:** `http://localhost:8000/predict`

---

### STEP 10 — `run_pipeline.py` — Master Pipeline Runner

**Purpose:** Single script that runs the entire training pipeline end-to-end.

**File:** `ml/run_pipeline.py`

```python
"""
run_pipeline.py
Master pipeline runner — executes all M4 training steps in order.

Usage:
  python run_pipeline.py                  # full pipeline
  python run_pipeline.py --skip-data      # skip data generation
  python run_pipeline.py --skip-train     # skip model training (evaluation only)
"""

import argparse
import subprocess
import sys
import time

STEPS = [
    ("Data Generation",      "python -m src.data_generator"),
    ("Feature Engineering",  "python -m src.feature_engineering"),
    ("Anomaly Detector",     "python -m src.train_anomaly_detector"),
    ("Fault Classifier",     "python -m src.train_fault_classifier"),
    ("Evaluation",           "python -m src.evaluate"),
]

def run_step(name, cmd):
    print(f"\n{'='*60}")
    print(f"STEP: {name}")
    print(f"CMD:  {cmd}")
    print('='*60)
    t0 = time.time()
    result = subprocess.run(cmd, shell=True, check=True)
    elapsed = time.time() - t0
    print(f"DONE: {name} ({elapsed:.1f}s)")
    return elapsed

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-data",  action="store_true")
    parser.add_argument("--skip-train", action="store_true")
    args = parser.parse_args()
    
    for name, cmd in STEPS:
        if args.skip_data and "data_generator" in cmd:
            continue
        if args.skip_train and ("anomaly" in cmd or "classifier" in cmd):
            continue
        run_step(name, cmd)
    
    print("\n" + "="*60)
    print("M4 BASELINE PIPELINE COMPLETE")
    print("Models saved to ml/models/")
    print("Reports saved to ml/reports/")
    print("Start API: uvicorn api.main:app --port 8000")
    print("="*60)
```

---

### STEP 11 — `tests/` — Unit Tests

**File:** `ml/tests/test_feature_engineering.py`

```python
# Tests to implement:
# test_load_csv_returns_expected_columns()
# test_rolling_features_correct_shape()
# test_slope_features_positive_for_rising_signal()
# test_warmup_rows_dropped()
# test_label_encoding_correct()
# test_no_nan_in_features_after_pipeline()
```

**File:** `ml/tests/test_anomaly_detector.py`

```python
# Tests to implement:
# test_isolation_forest_predicts_healthy_as_normal()
# test_isolation_forest_predicts_fault_as_anomaly()
# test_model_file_created_after_training()
# test_threshold_in_valid_range()
```

**File:** `ml/tests/test_fault_classifier.py`

```python
# Tests to implement:
# test_classifier_returns_correct_number_of_classes()
# test_classifier_confidence_sums_to_one()
# test_feature_importance_shape_matches_features()
# test_predict_engine_health_output_schema()
```

**Run tests:** `pytest tests/ -v`

---

## 5. Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    M4 BASELINE DATA FLOW                        │
└─────────────────────────────────────────────────────────────────┘

[data_generator.py]
  └─→ data/raw/healthy_run_01.csv (900 rows × 18 cols)
  └─→ data/raw/oil_pressure_drop_01.csv (900 rows × 18 cols)
  └─→ ...7 more CSV files...

[feature_engineering.py]
  ├── Input:  data/raw/*.csv  (18 raw cols)
  ├── Steps:
  │   ├── Clean + fill NaN
  │   ├── One-hot encode mission_phase (+6 cols)
  │   ├── Rolling stats (30s window) for 17 sensors (+17×5 = 85 cols)
  │   ├── Slope features for 6 cols (+6 cols)
  │   └── Labels: label_anomaly (0/1), label_fault_int (0-6)
  ├── Output: ~150 feature columns
  ├── Saves: data/processed/features_train.csv
  │          data/processed/features_val.csv
  │          data/processed/features_test.csv
  └── Saves: models/scaler.pkl

[train_anomaly_detector.py]
  ├── Input:  X_train (healthy rows only), scaler.pkl
  ├── Model:  IsolationForest(n_estimators=200, contamination=0.05)
  ├── Tune:   threshold on X_val → max F1
  └── Saves:  models/isolation_forest.pkl
              reports/anomaly_metrics.json
              reports/anomaly_score_plot.png

[train_fault_classifier.py]
  ├── Input:  X_train (all classes), y_train_fault, scaler.pkl
  ├── Model:  RandomForestClassifier(n_estimators=300, class_weight="balanced")
  └── Saves:  models/random_forest_classifier.pkl
              reports/classification_metrics.json
              reports/confusion_matrix.png
              reports/feature_importance.png

[predict.py]
  ├── Input:  window_df (WINDOW_SIZE rows of live telemetry)
  ├── Load:   isolation_forest.pkl, random_forest_classifier.pkl, scaler.pkl
  ├── Steps:
  │   ├── Feature engineering on window
  │   ├── Scale
  │   ├── IF.decision_function() → anomaly_score
  │   ├── RFC.predict_proba()   → fault_type + confidence
  │   └── explain.build_explanation() → top_features + explanation
  └── Output: {is_anomaly, anomaly_score, health_state, fault_type,
                confidence, top_features, explanation, severity}

[api/main.py]
  ├── POST /predict → predict_engine_health(window_df)
  └── Returns PredictResponse JSON
```

---

## 6. Exact Feature List (Generated by feature_engineering.py)

Total features ≈ **158** columns:

| Group | Columns | Count |
|---|---|---|
| Raw sensors (last value) | rpm_last, oil_pressure_last, oil_temp_last, cht_last, egt_last, manifold_pressure_last, vibration_last, fuel_flow_last, throttle_last, ambient_temp_last, altitude_last | 11 |
| Raw residuals (last value) | residual_rpm_last, residual_oil_pressure_last, residual_oil_temp_last, residual_cht_last, residual_egt_last, residual_manifold_pressure_last, residual_vibration_last, residual_fuel_flow_last | 8 |
| Health/RUL | health_index, baseline_rul | 2 |
| Rolling mean (30s) | {col}_mean_30s for all 17 sensor+residual cols | 17 |
| Rolling std (30s) | {col}_std_30s | 17 |
| Rolling min (30s) | {col}_min_30s | 17 |
| Rolling max (30s) | {col}_max_30s | 17 |
| Slope features | oil_pressure_slope_30s, oil_temp_slope_30s, cht_slope_30s, vibration_slope_30s, residual_oil_pressure_slope_30s, residual_vibration_slope_30s | 6 |
| Mission phase (one-hot) | mission_phase_idle, mission_phase_taxi, mission_phase_takeoff, mission_phase_cruise, mission_phase_descent, mission_phase_landing | 6 |

---

## 7. Expected Performance Targets

### Anomaly Detection (Isolation Forest)

| Metric | Target (Baseline) |
|---|---|
| Precision | ≥ 0.80 |
| Recall | ≥ 0.85 |
| F1-score | ≥ 0.82 |
| False Alarm Rate | ≤ 0.10 |
| Detection Delay | ≤ 30 seconds |

### Fault Classification (RandomForestClassifier)

| Metric | Target (Baseline) |
|---|---|
| Overall Accuracy | ≥ 0.88 |
| Macro F1-score | ≥ 0.85 |
| Weighted F1-score | ≥ 0.88 |
| Per-class Recall | ≥ 0.80 for all classes |

---

## 8. Day-by-Day Execution Schedule

| Day | Milestone | Files to Complete | Expected Output |
|---|---|---|---|
| **Day 1** | Setup + Data Schema + Generation | `requirements.txt`, `config.py`, `data_generator.py` | 9 CSV files in `data/raw/` |
| **Day 2** | Feature Engineering | `feature_engineering.py` | `features_train/val/test.csv`, `scaler.pkl` |
| **Day 3** | Isolation Forest Baseline | `train_anomaly_detector.py` | `isolation_forest.pkl`, `anomaly_metrics.json`, plots |
| **Day 4** | RandomForest Classifier | `train_fault_classifier.py` | `random_forest_classifier.pkl`, `confusion_matrix.png` |
| **Day 5** | Explainability + Predict | `explain.py`, `predict.py` | `shap_summary.png`, working `predict_engine_health()` |
| **Day 6** | API + Integration | `api/main.py`, `run_pipeline.py` | Live FastAPI on `:8000` |
| **Day 7** | Tests + Demo Script | `tests/`, `evaluate.py` | All tests passing, demo ready |

---

## 9. Demo Scenario Script

Run this exact sequence to demonstrate M4 at the hackathon:

```python
# demo_script.py — Run this to demonstrate M4 live

import pandas as pd
from src.predict import predict_engine_health
from src.config import DATA_RAW_DIR, WINDOW_SIZE

def demo_scenario(csv_file: str, label: str):
    """Replay a recorded mission and show M4 detections."""
    df = pd.read_csv(DATA_RAW_DIR / csv_file)
    print(f"\n{'='*60}")
    print(f"DEMO: {label}")
    print(f"Mission: {csv_file}, {len(df)} timesteps")
    print('='*60)
    
    anomaly_detected_at = None
    
    for i in range(WINDOW_SIZE, len(df)):
        window = df.iloc[i-WINDOW_SIZE:i]
        result = predict_engine_health(window)
        
        if result["is_anomaly"] and anomaly_detected_at is None:
            anomaly_detected_at = i
            print(f"\n⚠️  ANOMALY DETECTED at t={i}s")
            print(f"   Fault:       {result['fault_type']}")
            print(f"   Confidence:  {result['confidence']*100:.1f}%")
            print(f"   Severity:    {result['severity']}/3")
            print(f"   Top Sensors: {', '.join(result['top_features'][:3])}")
            print(f"   Explanation: {result['explanation'][:120]}...")
    
    if anomaly_detected_at is None:
        print("✅ Engine ran healthy throughout mission — no anomalies detected.")

# Scenario 1: Healthy run — should show NO anomaly
demo_scenario("healthy_run_01.csv", "HEALTHY ENGINE RUN")

# Scenario 2: Oil pressure drop — should detect at ~t=310-330s
demo_scenario("oil_pressure_drop_01.csv", "OIL PRESSURE DROP FAULT")

# Scenario 3: Overheating — should detect at ~t=310-330s
demo_scenario("overheating_01.csv", "OVERHEATING FAULT")
```

**Run:** `python demo_script.py`

---

## 10. Files Summary Table

| File | Purpose | Lines (est.) | Key Libraries |
|---|---|---|---|
| `src/config.py` | All constants, paths, hyperparameters | ~120 | `pathlib` |
| `src/data_generator.py` | Synthetic telemetry generation | ~250 | `numpy`, `pandas` |
| `src/feature_engineering.py` | Rolling windows, slopes, encoding | ~300 | `pandas`, `numpy`, `sklearn` |
| `src/train_anomaly_detector.py` | Isolation Forest training + eval | ~200 | `sklearn`, `joblib`, `matplotlib` |
| `src/train_fault_classifier.py` | RandomForest training + eval | ~200 | `sklearn`, `joblib`, `seaborn` |
| `src/explain.py` | SHAP + template explanations | ~150 | `shap`, `matplotlib` |
| `src/predict.py` | Unified prediction function | ~150 | all above |
| `src/evaluate.py` | Full metric suite + plots | ~200 | `sklearn`, `matplotlib` |
| `api/main.py` | FastAPI REST interface | ~120 | `fastapi`, `pydantic` |
| `run_pipeline.py` | Master pipeline orchestrator | ~60 | `subprocess` |
| `tests/*.py` | Unit tests | ~150 | `pytest` |
| `demo_script.py` | Hackathon demo runner | ~50 | `pandas` |

---

## 11. Environment Setup Commands

```bash
# 1. Clone / navigate to project
cd ml/

# 2. Create virtual environment
python -m venv .venv

# 3. Activate (Windows)
.venv\Scripts\activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Run full pipeline
python run_pipeline.py

# 6. Start API server
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# 7. Run tests
pytest tests/ -v

# 8. Run demo
python demo_script.py
```

---

## 12. Integration Contract with Other Modules

### What M4 Expects FROM M3 (Telemetry)
- Live stream of rows matching `RAW_SENSOR_COLS` schema (Section 3.4)
- Minimum `WINDOW_SIZE=30` rows buffered before first prediction

### What M4 Expects FROM M2 (Residuals)
- Merged columns matching `RESIDUAL_COLS` schema (Section 3.5)
- If M2 is not ready: M4 runs with zeroed residuals (degraded accuracy)

### What M4 GIVES TO M5 (Dashboard)
```json
{
  "timestamp":    "2026-09-06T10:30:00",
  "is_anomaly":   true,
  "anomaly_score": 0.82,
  "health_state": "degrading",
  "fault_type":   "oil_pressure_drop",
  "confidence":   0.91,
  "top_features": ["residual_oil_pressure_mean_30s", "oil_pressure_slope_30s", "oil_temp_max_30s"],
  "explanation":  "Oil pressure is 18 PSI below physics-model expectation and continues to fall while oil temperature is rising.",
  "severity":     2
}
```

### What M4 GIVES TO M6 (API)
- REST endpoint: `POST http://localhost:8000/predict`
- Request: `{"window": [<30 TelemetryRow objects>]}`
- Response: `PredictResponse` JSON (schema above)

---

## 13. Open Questions / Assumptions

> [!NOTE]
> These are assumptions made where M1/M2/M3 module details are not yet finalized.

1. **Residual availability**: If M2 residuals are not available at training time, `data_generator.py` simulates them. Real residuals from M2 will improve model performance.
2. **Sampling rate**: Assumed 1 Hz (1 row = 1 second). If M3 uses a different rate, `WINDOW_SIZE` and `STEP_SIZE` in `config.py` should be adjusted.
3. **Mission length**: Assumed 900 seconds (15 min) per run. Adjust in `data_generator.py` as needed.
4. **Fault injection timing**: Faults injected at t=300s. Real fault data from M3 may have different timing.
5. **API security**: API has no authentication — assumed internal service within M6's deployment boundary.
6. **Model retraining**: No online learning in baseline. Retrain by rerunning `run_pipeline.py`.

---

*Generated for SIH 2026 | M4 AI/ML Module | Baseline Implementation Plan v1.0*
