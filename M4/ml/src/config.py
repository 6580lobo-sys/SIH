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

FAULT_TYPES = [
    "healthy",
    "overheating",
    "oil_pressure_drop",
    "vibration_bearing_fault",
    "misfire_or_injector_fault",
    "fuel_mixture_drift",
    "cooling_system_fault",
    "engine_overspeed",
    "oil_pressure_drop_escalating",
    "mixed_vibration_bearing_fault__engine_overspeed",
    "overheating_recovering",
    "vibration_bearing_fault_recovering",
    "mixed_engine_overspeed__overheating",
    "mixed_vibration_bearing_fault__misfire_or_injector_fault",
    "mixed_fuel_mixture_drift__overheating",
    "mixed_misfire_or_injector_fault__oil_pressure_drop",
    "overheating_escalating",
    "mixed_overheating__cooling_system_fault",
    "mixed_cooling_system_fault__oil_pressure_drop",
    "mixed_cooling_system_fault__misfire_or_injector_fault",
    "mixed_oil_pressure_drop__vibration_bearing_fault",
    "mixed_oil_pressure_drop__overheating",
    "mixed_fuel_mixture_drift__vibration_bearing_fault",
    "vibration_bearing_fault_escalating",
    "oil_pressure_drop_recovering",
    "mixed_overheating__misfire_or_injector_fault"
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
# Healthy envelope is > -0.035; scores below -0.035 indicate novelty/zero-day anomaly
IF_THRESHOLD = -0.035

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
