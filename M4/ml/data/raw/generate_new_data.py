"""
generate_new_data.py
====================
SIH26054 — M4 AI/ML Module — Supplementary Training Data Generator
===================================================================

Author  : M4 Team
Purpose : Generate additional, diverse, high-quality CSV files that follow
          the EXACT schema defined in the M4 FINAL_implementation_plan.md.

          Covers:
            A. Pure healthy runs (varied seeds, phases, ambient conditions)
            B. Single-fault runs (all 7 fault types)
            C. Mixed / compound fault runs (critical for ML generalisation)
            D. Gradual / slow-burn degradation runs
            E. High-stress & extreme-environment runs
            F. Edge-case & near-threshold runs
            G. Fault-then-recovery (transient) runs
            H. Multi-phase fault injection runs

CSV Schema (exact, per implementation plan §3.4 + §3.5):
  timestamp, mission_phase,
  rpm, throttle, oil_pressure, oil_temp, cht, egt,
  manifold_pressure, vibration, fuel_flow,
  ambient_temp, altitude,
  fault_type, fault_active, fault_severity,
  fault_start_time, fault_end_time,
  residual_rpm, residual_oil_pressure, residual_oil_temp,
  residual_cht, residual_egt, residual_manifold_pressure,
  residual_vibration, residual_fuel_flow,
  health_index, baseline_rul

Run:
    python generate_new_data.py
Outputs go to ./  (same folder as this script) so they can be merged
into M4/ml/data/raw later.
"""

import numpy as np
import pandas as pd
from pathlib import Path

# ── Output folder ────────────────────────────────────────────────────────────
OUT_DIR = Path(__file__).resolve().parent
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Schema constants (mirrors M4/ml/src/config.py) ──────────────────────────
MISSION_PHASES = ["idle", "taxi", "takeoff", "cruise", "descent", "landing"]

FAULT_TYPES = [
    "healthy",
    "overheating",
    "oil_pressure_drop",
    "vibration_bearing_fault",
    "misfire_or_injector_fault",
    "fuel_mixture_drift",
    "cooling_system_fault",
    "engine_overspeed",
]

# Normal operating ranges
NORMAL_RANGES = {
    "rpm":               (3500, 4500),
    "throttle":          (30,   90),       # realistic inflight range
    "oil_pressure":      (45,   70),
    "oil_temp":          (80,   110),
    "cht":               (160,  220),
    "egt":               (600,  750),
    "manifold_pressure": (20,   30),
    "vibration":         (0.10, 0.40),
    "fuel_flow":         (8,    16),
    "ambient_temp":      (-10,  45),
    "altitude":          (0,    5000),
}

# Residual noise for healthy engine (small Gaussian)
RESIDUAL_NOISE_STD = {
    "rpm":               3.0,
    "oil_pressure":      0.4,
    "oil_temp":          0.5,
    "cht":               0.8,
    "egt":               1.5,
    "manifold_pressure": 0.15,
    "vibration":         0.005,
    "fuel_flow":         0.08,
}

# ────────────────────────────────────────────────────────────────────────────
# HELPER: mission phase profile
# ────────────────────────────────────────────────────────────────────────────
def generate_mission_profile(n_steps, fracs=(0.05, 0.05, 0.10, 0.60, 0.10, 0.10)):
    phases = []
    counts = [int(n_steps * f) for f in fracs]
    counts[-1] += n_steps - sum(counts)  # absorb rounding remainder
    for phase, count in zip(MISSION_PHASES, counts):
        phases.extend([phase] * count)
    return np.array(phases[:n_steps])


# ────────────────────────────────────────────────────────────────────────────
# HELPER: phase-dependent base sensor values
# ────────────────────────────────────────────────────────────────────────────
PHASE_MODIFIER = {
    # (rpm_delta, throttle_delta, cht_delta, egt_delta, manifold_delta, fuel_delta)
    "idle":    (-400, -25, -20, -80, -5,  -4),
    "taxi":    (-200, -10, -10, -40, -3,  -2),
    "takeoff": ( 400,  20,  20,  60,  4,   4),
    "cruise":  (   0,   0,   0,   0,  0,   0),
    "descent": (-300, -20, -10, -50, -3,  -3),
    "landing": (-350, -25, -15, -60, -4,  -3),
}


def phase_adjusted_sensors(phase, base_sensors):
    """Apply phase deltas to a dict of base sensor values."""
    d = dict(base_sensors)
    pm = PHASE_MODIFIER[phase]
    d["rpm"]               += pm[0]
    d["throttle"]          += pm[1]
    d["cht"]               += pm[2]
    d["egt"]               += pm[3]
    d["manifold_pressure"] += pm[4]
    d["fuel_flow"]         += pm[5]
    return d


# ────────────────────────────────────────────────────────────────────────────
# CORE: generate healthy baseline telemetry
# ────────────────────────────────────────────────────────────────────────────
def generate_healthy_telemetry(
    n_steps=900,
    noise_std=0.018,
    seed=42,
    ambient_temp=None,
    altitude=None,
):
    rng = np.random.default_rng(seed)

    # Choose random baseline inside normal ranges
    base = {
        sensor: rng.uniform(lo + 0.2 * (hi - lo), hi - 0.2 * (hi - lo))
        for sensor, (lo, hi) in NORMAL_RANGES.items()
    }

    # Override env if provided
    if ambient_temp is not None:
        base["ambient_temp"] = float(ambient_temp)
    if altitude is not None:
        base["altitude"] = float(altitude)

    phases = generate_mission_profile(n_steps)

    rows = []
    for t in range(n_steps):
        phase = phases[t]
        adj = phase_adjusted_sensors(phase, base)

        row = {"timestamp": t, "mission_phase": phase}

        for sensor, (lo, hi) in NORMAL_RANGES.items():
            noise = rng.normal(0, noise_std * (hi - lo))
            val = np.clip(adj[sensor] + noise, lo * 0.85, hi * 1.20)
            row[sensor] = val

        # Healthy labels
        row["fault_type"]       = "healthy"
        row["fault_active"]     = 0
        row["fault_severity"]   = 0
        row["fault_start_time"] = 0
        row["fault_end_time"]   = 0

        # Synthetic residuals (physics model ≈ actual for healthy)
        for sensor, std in RESIDUAL_NOISE_STD.items():
            row[f"residual_{sensor}"] = rng.normal(0, std)

        row["health_index"]  = 1.0
        row["baseline_rul"]  = 200.0 - t * 0.005   # slight natural burn-down

        rows.append(row)

    return pd.DataFrame(rows)


# ────────────────────────────────────────────────────────────────────────────
# CORE: inject a single fault
# ────────────────────────────────────────────────────────────────────────────
def inject_fault(
    df: pd.DataFrame,
    fault_type: str,
    fault_start: int = 300,
    severity: int = 2,
    ramp_steps: int = 100,
    seed: int = 42,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    df = df.copy()
    n = len(df)
    fault_end = n

    # Build ramp (0→1 over ramp_steps, then stays 1)
    def ramp_arr(start, steps, total):
        arr = np.zeros(total - start)
        r = np.linspace(0, 1, min(ramp_steps, len(arr)))
        arr[: len(r)] = r
        arr[len(r) :] = 1.0
        return arr

    idx = slice(fault_start, n)
    ramp = ramp_arr(fault_start, ramp_steps, n)

    if fault_type == "overheating":
        df.loc[idx, "cht"]               += ramp * 65
        df.loc[idx, "egt"]               += ramp * 80
        df.loc[idx, "oil_temp"]          += ramp * 12   # secondary heat soak
        df.loc[idx, "residual_cht"]      += ramp * 65
        df.loc[idx, "residual_egt"]      += ramp * 80
        df.loc[idx, "residual_oil_temp"] += ramp * 10
        df.loc[idx, "health_index"]      -= ramp * 0.60

    elif fault_type == "oil_pressure_drop":
        df.loc[idx, "oil_pressure"]          -= ramp * 22
        df.loc[idx, "oil_temp"]              += ramp * 16
        df.loc[idx, "residual_oil_pressure"] -= ramp * 22
        df.loc[idx, "residual_oil_temp"]     += ramp * 14
        df.loc[idx, "health_index"]          -= ramp * 0.70

    elif fault_type == "vibration_bearing_fault":
        vib_noise = rng.normal(0, 0.05, n - fault_start)
        df.loc[idx, "vibration"]         += ramp * 0.85 + vib_noise
        df.loc[idx, "rpm"]               += rng.normal(0, 180, n - fault_start) * ramp
        df.loc[idx, "residual_vibration"] += ramp * 0.85
        df.loc[idx, "health_index"]       -= ramp * 0.60

    elif fault_type == "misfire_or_injector_fault":
        # Intermittent spikes every 4–6 steps
        spike_arr = np.zeros(n - fault_start)
        step = 5
        for i in range(0, len(spike_arr), step):
            if rng.random() > 0.3:
                spike_arr[i] = rng.uniform(30, 80)
        drop_arr = np.zeros(n - fault_start)
        for i in range(0, len(drop_arr), step):
            if rng.random() > 0.3:
                drop_arr[i] = -rng.uniform(200, 400)

        df.loc[idx, "egt"]          += spike_arr * ramp
        df.loc[idx, "rpm"]          += drop_arr * ramp
        df.loc[idx, "fuel_flow"]    += rng.normal(0, 1.5, n - fault_start) * ramp
        df.loc[idx, "residual_egt"] += spike_arr * ramp
        df.loc[idx, "health_index"] -= ramp * 0.50

    elif fault_type == "fuel_mixture_drift":
        df.loc[idx, "fuel_flow"]         += ramp * 4.5
        df.loc[idx, "egt"]               += ramp * 42
        df.loc[idx, "residual_fuel_flow"] += ramp * 4.5
        df.loc[idx, "residual_egt"]       += ramp * 38
        df.loc[idx, "health_index"]       -= ramp * 0.42

    elif fault_type == "cooling_system_fault":
        df.loc[idx, "cht"]               += ramp * 55
        df.loc[idx, "oil_temp"]          += ramp * 22
        df.loc[idx, "residual_cht"]      += ramp * 55
        df.loc[idx, "residual_oil_temp"] += ramp * 20
        df.loc[idx, "health_index"]      -= ramp * 0.52

    elif fault_type == "engine_overspeed":
        df.loc[idx, "rpm"]          += ramp * 1800
        df.loc[idx, "vibration"]    += ramp * 0.40
        df.loc[idx, "egt"]          += ramp * 60
        df.loc[idx, "residual_rpm"] += ramp * 1800
        df.loc[idx, "health_index"] -= ramp * 0.80

    # Clamp health_index to [0, 1]
    df["health_index"] = df["health_index"].clip(0.0, 1.0)

    # Set fault metadata
    df.loc[idx, "fault_type"]       = fault_type
    df.loc[idx, "fault_active"]     = 1
    df.loc[idx, "fault_severity"]   = severity
    df.loc[idx, "fault_start_time"] = fault_start
    df.loc[idx, "fault_end_time"]   = fault_end

    return df


# ────────────────────────────────────────────────────────────────────────────
# MIXED FAULT: inject two overlapping faults
# ────────────────────────────────────────────────────────────────────────────
def inject_mixed_fault(
    df: pd.DataFrame,
    fault1: str,
    fault2: str,
    fault1_start: int = 250,
    fault2_start: int = 400,
    severity: int = 3,
    seed: int = 99,
) -> pd.DataFrame:
    """
    Inject two faults sequentially with overlap.
    fault1 starts at fault1_start, fault2 starts at fault2_start.
    The label after fault2_start is 'mixed_<fault1>_<fault2>'.
    """
    df = inject_fault(df, fault1, fault_start=fault1_start, severity=severity - 1, seed=seed)
    df = inject_fault(df, fault2, fault_start=fault2_start, severity=severity, seed=seed + 7)

    # Override label for overlapping region
    mixed_label = f"mixed_{fault1}__{fault2}"
    df.loc[fault2_start:, "fault_type"]     = mixed_label
    df.loc[fault2_start:, "fault_severity"] = severity
    df.loc[fault2_start:, "fault_active"]   = 1

    return df


# ────────────────────────────────────────────────────────────────────────────
# GRADUAL DEGRADATION: very slow ramp, hard to spot early
# ────────────────────────────────────────────────────────────────────────────
def generate_gradual_degradation(fault_type: str, seed: int = 200, n_steps: int = 1800):
    """
    Fault starts at step 100 but ramps VERY slowly (over 1000 steps).
    Health index decays to 0.5 by end.
    Tests early detection capability.
    """
    df = generate_healthy_telemetry(n_steps=n_steps, seed=seed)
    rng = np.random.default_rng(seed)
    n = n_steps
    fault_start = 100
    idx = slice(fault_start, n)
    ramp = np.linspace(0, 1, n - fault_start) ** 2  # squared → very slow then fast

    if fault_type == "overheating":
        df.loc[idx, "cht"]          += ramp * 50
        df.loc[idx, "egt"]          += ramp * 60
        df.loc[idx, "residual_cht"] += ramp * 50
        df.loc[idx, "residual_egt"] += ramp * 55
    elif fault_type == "oil_pressure_drop":
        df.loc[idx, "oil_pressure"]          -= ramp * 18
        df.loc[idx, "residual_oil_pressure"] -= ramp * 18
        df.loc[idx, "oil_temp"]              += ramp * 10
    elif fault_type == "vibration_bearing_fault":
        df.loc[idx, "vibration"]         += ramp * 0.6
        df.loc[idx, "residual_vibration"] += ramp * 0.6
    elif fault_type == "fuel_mixture_drift":
        df.loc[idx, "fuel_flow"]         += ramp * 3.5
        df.loc[idx, "residual_fuel_flow"] += ramp * 3.0
        df.loc[idx, "egt"]               += ramp * 30
    elif fault_type == "cooling_system_fault":
        df.loc[idx, "cht"]               += ramp * 40
        df.loc[idx, "residual_cht"]      += ramp * 38

    df.loc[idx, "health_index"]      -= ramp * 0.5
    df["health_index"]                = df["health_index"].clip(0, 1)
    df.loc[idx, "fault_type"]         = fault_type
    df.loc[idx, "fault_active"]       = 1
    df.loc[idx, "fault_severity"]     = 1   # starts mild
    df.loc[idx, "fault_start_time"]   = fault_start
    df.loc[idx, "fault_end_time"]     = n_steps
    return df


# ────────────────────────────────────────────────────────────────────────────
# TRANSIENT: fault appears then recovers (partial recovery scenario)
# ────────────────────────────────────────────────────────────────────────────
def generate_transient_fault(fault_type: str, seed: int = 300, n_steps: int = 900):
    """
    Fault appears from step 250 → 550, then engine partially recovers (500→650).
    Teaches ML that recovery patterns are NOT normal either.
    """
    df = generate_healthy_telemetry(n_steps=n_steps, seed=seed)
    rng = np.random.default_rng(seed)

    fault_start = 250
    fault_peak  = 400
    fault_end   = 550
    recovery_end = 650

    # Ramp up
    up_ramp  = np.linspace(0, 1, fault_peak - fault_start)
    flat     = np.ones(fault_end - fault_peak)
    # Ramp down (partial recovery — does not return to zero)
    down_ramp = np.linspace(1, 0.35, recovery_end - fault_end)

    combined = np.concatenate([up_ramp, flat, down_ramp])
    full_idx_len = recovery_end - fault_start

    def apply_transient(col, offset):
        base = df.loc[fault_start:recovery_end - 1, col].values.copy()
        delta = combined[:full_idx_len] * offset
        df.loc[fault_start:recovery_end - 1, col] = base + delta

    if fault_type == "overheating":
        apply_transient("cht", 55)
        apply_transient("egt", 70)
        apply_transient("residual_cht", 55)
        apply_transient("residual_egt", 65)
    elif fault_type == "oil_pressure_drop":
        apply_transient("oil_pressure", -20)
        apply_transient("oil_temp", 14)
        apply_transient("residual_oil_pressure", -20)
    elif fault_type == "vibration_bearing_fault":
        apply_transient("vibration", 0.7)
        apply_transient("residual_vibration", 0.7)

    # Health index
    hi_delta = np.concatenate([up_ramp * 0.55, flat * 0.55, down_ramp * 0.55])
    df.loc[fault_start:recovery_end - 1, "health_index"] -= hi_delta
    df["health_index"] = df["health_index"].clip(0, 1)

    df.loc[fault_start:fault_end - 1, "fault_type"]       = fault_type
    df.loc[fault_start:fault_end - 1, "fault_active"]     = 1
    df.loc[fault_start:fault_end - 1, "fault_severity"]   = 2
    df.loc[fault_start:fault_end - 1, "fault_start_time"] = fault_start
    df.loc[fault_start:fault_end - 1, "fault_end_time"]   = fault_end

    # Recovery region — still label as fault (degraded state)
    df.loc[fault_end:recovery_end - 1, "fault_type"]     = f"{fault_type}_recovering"
    df.loc[fault_end:recovery_end - 1, "fault_active"]   = 1
    df.loc[fault_end:recovery_end - 1, "fault_severity"] = 1

    return df


# ────────────────────────────────────────────────────────────────────────────
# NEAR-THRESHOLD: values hover at the edge of normal — hard negatives for ML
# ────────────────────────────────────────────────────────────────────────────
def generate_near_threshold_healthy(sensor: str, direction: str = "high", seed: int = 400):
    """
    Generates a healthy run where one sensor sits near (but inside) its upper
    or lower normal limit. Tests false-alarm rate.
    """
    rng = np.random.default_rng(seed)
    df = generate_healthy_telemetry(n_steps=900, seed=seed)

    lo, hi = NORMAL_RANGES[sensor]
    margin = 0.05 * (hi - lo)

    if direction == "high":
        target = hi - margin
    else:
        target = lo + margin

    # Gradually push sensor toward target over 400 steps
    ramp = np.linspace(0, 1, 500)
    current = df.loc[400:899, sensor].values
    new_vals = current + ramp * (target - current)
    df.loc[400:899, sensor] = new_vals

    # Still healthy
    df["fault_type"]     = "healthy"
    df["fault_active"]   = 0
    df["fault_severity"] = 0

    return df


# ────────────────────────────────────────────────────────────────────────────
# HIGH STRESS ENVIRONMENT: high altitude, hot day, max throttle
# ────────────────────────────────────────────────────────────────────────────
def generate_high_stress_healthy(seed: int = 500):
    """
    High-altitude (4500 m), hot day (42°C), aggressive throttle profile.
    Engine is still healthy — stress test for false-alarm rate.
    """
    df = generate_healthy_telemetry(
        n_steps=900, seed=seed, ambient_temp=42, altitude=4500
    )
    rng = np.random.default_rng(seed)

    # Boost throttle to simulate hard cruise
    df["throttle"] = np.clip(
        df["throttle"] + rng.normal(15, 3, len(df)), 0, 100
    )
    # High altitude → lower manifold pressure
    df["manifold_pressure"] -= 4.0
    # Hot day → CHT and EGT naturally higher
    df["cht"] += rng.normal(12, 2, len(df))
    df["egt"] += rng.normal(18, 4, len(df))
    df["oil_temp"] += rng.normal(8, 2, len(df))

    df["fault_type"]   = "healthy"
    df["fault_active"] = 0
    return df


def generate_cold_high_altitude(seed: int = 600):
    """Cold day (-8°C), high altitude (4800 m). Engine healthy but stressed."""
    df = generate_healthy_telemetry(
        n_steps=900, seed=seed, ambient_temp=-8, altitude=4800
    )
    rng = np.random.default_rng(seed)
    df["manifold_pressure"] -= 5.0
    df["cht"]   -= rng.normal(8, 2, len(df))
    df["egt"]   -= rng.normal(10, 3, len(df))
    df["oil_temp"] -= rng.normal(5, 1, len(df))
    df["fuel_flow"] += rng.normal(1.0, 0.2, len(df))   # rich mixture at cold
    df["fault_type"]   = "healthy"
    df["fault_active"] = 0
    return df


# ────────────────────────────────────────────────────────────────────────────
# MIXED SCENARIO LIBRARY
# ────────────────────────────────────────────────────────────────────────────
MIXED_SCENARIOS = [
    # (fault1,                    fault2,                    f1_start, f2_start, label_suffix)
    ("overheating",               "cooling_system_fault",    200,      380,      "overheat_coolsys"),
    ("oil_pressure_drop",         "overheating",             250,      420,      "oildrop_overheat"),
    ("vibration_bearing_fault",   "misfire_or_injector_fault", 200,   360,      "vib_misfire"),
    ("fuel_mixture_drift",        "overheating",             300,      450,      "fueldrift_overheat"),
    ("misfire_or_injector_fault", "oil_pressure_drop",       200,      400,      "misfire_oildrop"),
    ("cooling_system_fault",      "oil_pressure_drop",       250,      430,      "coolsys_oildrop"),
    ("vibration_bearing_fault",   "engine_overspeed",        250,      420,      "vib_overspeed"),
    ("fuel_mixture_drift",        "vibration_bearing_fault", 280,      440,      "fueldrift_vib"),
    ("overheating",               "misfire_or_injector_fault", 300,   480,      "overheat_misfire"),
    ("engine_overspeed",          "overheating",             200,      350,      "overspeed_overheat"),
    # Triple-effect cascade (represented as 2-pass injection)
    ("oil_pressure_drop",         "vibration_bearing_fault", 200,      380,      "oildrop_vib"),
    ("cooling_system_fault",      "misfire_or_injector_fault", 200,   380,      "coolsys_misfire"),
]


# ────────────────────────────────────────────────────────────────────────────
# SAVE HELPER
# ────────────────────────────────────────────────────────────────────────────
REQUIRED_COLS = [
    "timestamp", "mission_phase",
    "rpm", "throttle", "oil_pressure", "oil_temp",
    "cht", "egt", "manifold_pressure", "vibration", "fuel_flow",
    "ambient_temp", "altitude",
    "fault_type", "fault_active", "fault_severity",
    "fault_start_time", "fault_end_time",
    "residual_rpm", "residual_oil_pressure", "residual_oil_temp",
    "residual_cht", "residual_egt", "residual_manifold_pressure",
    "residual_vibration", "residual_fuel_flow",
    "health_index", "baseline_rul",
]


def save_csv(df: pd.DataFrame, filename: str):
    # Ensure all required columns present
    for col in REQUIRED_COLS:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")

    # Reorder to canonical schema
    out_df = df[REQUIRED_COLS].copy()

    # Round floats to 6 decimal places for cleaner CSVs
    float_cols = out_df.select_dtypes(include="float64").columns
    out_df[float_cols] = out_df[float_cols].round(6)

    filepath = OUT_DIR / filename
    out_df.to_csv(filepath, index=False)
    rows = len(out_df)
    faults = out_df[out_df["fault_active"] == 1].shape[0]
    print(f"  [OK] {filename:60s}  rows={rows:5d}  fault_rows={faults:5d}")


# ────────────────────────────────────────────────────────────────────────────
# MAIN GENERATION LOGIC
# ────────────────────────────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("M4 Supplementary Training Data Generator")
    print("=" * 70)
    generated = []

    # ── A. HEALTHY RUNS (varied seeds & environments) ────────────────────────
    print("\n[A] Healthy Runs")
    healthy_configs = [
        (401, None,  None,    "healthy_run_04.csv"),
        (402, None,  None,    "healthy_run_05.csv"),
        (403, None,  None,    "healthy_run_06.csv"),
        (404, 25,    500,     "healthy_medium_alt_01.csv"),
        (405, 15,   2500,     "healthy_medium_alt_02.csv"),
        (406, -5,   4000,     "healthy_high_alt_cold_01.csv"),
        (407, 38,   1000,     "healthy_hot_low_alt_01.csv"),
        (408, 40,   3500,     "healthy_hot_high_alt_01.csv"),
        (409, 0,    2000,     "healthy_standard_extra_01.csv"),
        (410, 20,   1500,     "healthy_standard_extra_02.csv"),
    ]
    for seed, amb, alt, fname in healthy_configs:
        df = generate_healthy_telemetry(n_steps=900, seed=seed,
                                        ambient_temp=amb, altitude=alt)
        save_csv(df, fname)
        generated.append(fname)

    # ── B. SINGLE FAULT RUNS — additional seeds and timings ─────────────────
    print("\n[B] Single Fault Runs")
    single_fault_configs = [
        # (fault_type,                 n_steps, fault_start, severity, seed, suffix)
        ("overheating",               900,  200, 2, 501, "overheating_02.csv"),
        ("overheating",               900,  400, 3, 502, "overheating_03.csv"),
        ("overheating",              1200,  300, 2, 503, "overheating_04_long.csv"),
        ("oil_pressure_drop",         900,  200, 2, 511, "oil_pressure_drop_03.csv"),
        ("oil_pressure_drop",         900,  500, 3, 512, "oil_pressure_drop_04.csv"),
        ("oil_pressure_drop",        1200,  350, 2, 513, "oil_pressure_drop_05_long.csv"),
        ("vibration_bearing_fault",   900,  250, 2, 521, "vibration_bearing_fault_02.csv"),
        ("vibration_bearing_fault",   900,  400, 3, 522, "vibration_bearing_fault_03.csv"),
        ("vibration_bearing_fault",  1200,  300, 2, 523, "vibration_bearing_fault_04_long.csv"),
        ("misfire_or_injector_fault", 900,  200, 2, 531, "misfire_or_injector_fault_02.csv"),
        ("misfire_or_injector_fault", 900,  450, 3, 532, "misfire_or_injector_fault_03.csv"),
        ("misfire_or_injector_fault",1200,  300, 2, 533, "misfire_or_injector_fault_04_long.csv"),
        ("fuel_mixture_drift",        900,  200, 2, 541, "fuel_mixture_drift_02.csv"),
        ("fuel_mixture_drift",        900,  400, 2, 542, "fuel_mixture_drift_03.csv"),
        ("fuel_mixture_drift",       1200,  350, 3, 543, "fuel_mixture_drift_04_long.csv"),
        ("cooling_system_fault",      900,  200, 2, 551, "cooling_system_fault_02.csv"),
        ("cooling_system_fault",      900,  450, 3, 552, "cooling_system_fault_03.csv"),
        ("cooling_system_fault",     1200,  300, 2, 553, "cooling_system_fault_04_long.csv"),
        ("engine_overspeed",          900,  300, 3, 561, "engine_overspeed_02.csv"),
        ("engine_overspeed",          900,  200, 3, 562, "engine_overspeed_03.csv"),
        ("engine_overspeed",         1200,  400, 3, 563, "engine_overspeed_04_long.csv"),
    ]

    for fault_type, n_steps, fault_start, sev, seed, fname in single_fault_configs:
        base = generate_healthy_telemetry(n_steps=n_steps, seed=seed)
        df   = inject_fault(base, fault_type, fault_start=fault_start,
                            severity=sev, seed=seed + 1000)
        save_csv(df, fname)
        generated.append(fname)

    # ── C. MIXED / COMPOUND FAULT RUNS ──────────────────────────────────────
    print("\n[C] Mixed / Compound Fault Runs")
    for i, (f1, f2, s1, s2, suffix) in enumerate(MIXED_SCENARIOS):
        seed = 600 + i * 7
        base = generate_healthy_telemetry(n_steps=1000, seed=seed)
        df   = inject_mixed_fault(base, f1, f2,
                                  fault1_start=s1, fault2_start=s2,
                                  severity=3, seed=seed + 50)
        fname = f"mixed_{suffix}_01.csv"
        save_csv(df, fname)
        generated.append(fname)

    # Extra mixed: same fault type double injection (escalation)
    for ft, seed, fname in [
        ("overheating",             700, "mixed_overheating_escalation_01.csv"),
        ("oil_pressure_drop",       701, "mixed_oildrop_escalation_01.csv"),
        ("vibration_bearing_fault", 702, "mixed_vibration_escalation_01.csv"),
    ]:
        base = generate_healthy_telemetry(n_steps=1000, seed=seed)
        df   = inject_fault(base, ft, fault_start=200, severity=1, seed=seed)
        df   = inject_fault(df,   ft, fault_start=500, severity=3, seed=seed + 10)
        df.loc[500:, "fault_type"] = f"{ft}_escalating"
        save_csv(df, fname)
        generated.append(fname)

    # ── D. GRADUAL DEGRADATION RUNS ─────────────────────────────────────────
    print("\n[D] Gradual Degradation Runs")
    gradual_configs = [
        ("overheating",             800, "gradual_overheating_01.csv"),
        ("oil_pressure_drop",       801, "gradual_oil_pressure_drop_01.csv"),
        ("vibration_bearing_fault", 802, "gradual_vibration_bearing_fault_01.csv"),
        ("fuel_mixture_drift",      803, "gradual_fuel_mixture_drift_01.csv"),
        ("cooling_system_fault",    804, "gradual_cooling_system_fault_01.csv"),
    ]
    for fault_type, seed, fname in gradual_configs:
        df = generate_gradual_degradation(fault_type, seed=seed, n_steps=1800)
        save_csv(df, fname)
        generated.append(fname)

    # ── E. TRANSIENT / RECOVERY RUNS ────────────────────────────────────────
    print("\n[E] Transient / Fault-then-Recovery Runs")
    transient_configs = [
        ("overheating",             900, "transient_overheating_01.csv"),
        ("oil_pressure_drop",       901, "transient_oil_pressure_drop_01.csv"),
        ("vibration_bearing_fault", 902, "transient_vibration_bearing_fault_01.csv"),
    ]
    for fault_type, seed, fname in transient_configs:
        df = generate_transient_fault(fault_type, seed=seed)
        save_csv(df, fname)
        generated.append(fname)

    # ── F. NEAR-THRESHOLD HEALTHY RUNS (hard negatives) ─────────────────────
    print("\n[F] Near-Threshold Healthy Runs")
    near_configs = [
        ("cht",          "high",  1001, "near_threshold_cht_high_01.csv"),
        ("egt",          "high",  1002, "near_threshold_egt_high_01.csv"),
        ("oil_pressure", "low",   1003, "near_threshold_oilp_low_01.csv"),
        ("vibration",    "high",  1004, "near_threshold_vib_high_01.csv"),
        ("fuel_flow",    "high",  1005, "near_threshold_ff_high_01.csv"),
        ("oil_temp",     "high",  1006, "near_threshold_oilt_high_01.csv"),
    ]
    for sensor, direction, seed, fname in near_configs:
        df = generate_near_threshold_healthy(sensor, direction, seed=seed)
        save_csv(df, fname)
        generated.append(fname)

    # ── G. HIGH-STRESS HEALTHY RUNS ─────────────────────────────────────────
    print("\n[G] High-Stress & Extreme Environment Runs")
    df = generate_high_stress_healthy(seed=1100)
    save_csv(df, "healthy_high_stress_hot_01.csv")
    generated.append("healthy_high_stress_hot_01.csv")

    df = generate_cold_high_altitude(seed=1101)
    save_csv(df, "healthy_cold_high_alt_01.csv")
    generated.append("healthy_cold_high_alt_01.csv")

    # High stress WITH a fault
    for fault_type, seed, fname in [
        ("overheating",           1200, "highstress_overheating_01.csv"),
        ("oil_pressure_drop",     1201, "highstress_oil_pressure_drop_01.csv"),
        ("vibration_bearing_fault", 1202, "highstress_vibration_bearing_01.csv"),
    ]:
        base = generate_high_stress_healthy(seed=seed)
        df   = inject_fault(base, fault_type, fault_start=350, severity=3, seed=seed)
        save_csv(df, fname)
        generated.append(fname)

    # ── H. MULTI-PHASE SPECIFIC FAULT INJECTION ──────────────────────────────
    print("\n[H] Multi-Phase Fault Injection (fault during specific phases)")
    phase_fault_configs = [
        # fault during takeoff (phase starts ~t=90 for 900-step mission)
        ("overheating",             1300, 90,  "phase_takeoff_overheating_01.csv"),
        ("oil_pressure_drop",       1301, 90,  "phase_takeoff_oildrop_01.csv"),
        # fault during cruise (phase ~t=180)
        ("vibration_bearing_fault", 1310, 180, "phase_cruise_vibration_01.csv"),
        ("fuel_mixture_drift",      1311, 180, "phase_cruise_fueldrift_01.csv"),
        # fault during descent (~t=720)
        ("overheating",             1320, 720, "phase_descent_overheating_01.csv"),
        ("misfire_or_injector_fault",1321,720, "phase_descent_misfire_01.csv"),
    ]
    for fault_type, seed, f_start, fname in phase_fault_configs:
        base = generate_healthy_telemetry(n_steps=900, seed=seed)
        df   = inject_fault(base, fault_type, fault_start=f_start, severity=2, seed=seed)
        save_csv(df, fname)
        generated.append(fname)

    # ── I. SENSOR NOISE VARIATION (high noise healthy — stress false-alarm) ──
    print("\n[I] High-Noise Healthy Runs")
    for seed, noise, fname in [
        (1400, 0.05, "healthy_high_noise_01.csv"),
        (1401, 0.07, "healthy_high_noise_02.csv"),
        (1402, 0.03, "healthy_moderate_noise_01.csv"),
    ]:
        df = generate_healthy_telemetry(n_steps=900, seed=seed, noise_std=noise)
        save_csv(df, fname)
        generated.append(fname)

    # ── SUMMARY ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print(f"DONE. Generated {len(generated)} CSV files in: {OUT_DIR}")
    print("=" * 70)

    # Print breakdown by category
    category_counts = {}
    for fname in generated:
        if fname.startswith("healthy"):        cat = "healthy"
        elif fname.startswith("mixed"):        cat = "mixed_fault"
        elif fname.startswith("gradual"):      cat = "gradual_degradation"
        elif fname.startswith("transient"):    cat = "transient_recovery"
        elif fname.startswith("near_threshold"): cat = "near_threshold"
        elif fname.startswith("highstress"):   cat = "high_stress_fault"
        elif fname.startswith("phase_"):       cat = "phase_specific_fault"
        else:                                  cat = "single_fault"
        category_counts[cat] = category_counts.get(cat, 0) + 1

    print("\nBreakdown:")
    for cat, count in sorted(category_counts.items()):
        print(f"  {cat:35s}: {count} files")


if __name__ == "__main__":
    main()
