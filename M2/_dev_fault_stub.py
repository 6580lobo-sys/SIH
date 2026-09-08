"""
_dev_fault_stub.py — M1 Residual Input Adapter (SIH26054)

PRIMARY: Imports M1's real FaultedSimulator (via twin_core) and runs it to produce
         residual signals in the standard M2 schema: timestamp + res_* + fault_label.

FALLBACK: If twin_core is not installed, generates synthetic residuals
          matching the same schema for dev/smoke-testing.

M2 always receives: timestamp, res_rpm, res_cht, res_egt, res_oil_p, res_oil_t, res_fuel, res_vib, fault_label
M2 never computes residuals itself — that is M1's responsibility.
"""

import os
import numpy as np
import pandas as pd
import importlib.util


# ------------------------------------------------------------------
# Channel mapping: M1's residual keys  →  M2's expected column names
# ------------------------------------------------------------------
M1_TO_M2_CHANNEL_MAP = {
    "rpm":                  "res_rpm",
    "cht":                  "res_cht",
    "egt":                  "res_egt",
    "oil_pressure":         "res_oil_p",
    "oil_temp":             "res_oil_t",
    "fuel_flow":            "res_fuel",
    "vibration_amplitude":  "res_vib",
}


def generate_m1_residuals_real(
    fault_type: str = "overheating",
    fault_time: float = 30.0,
    duration: float = 150.0,
    dt: float = 0.5,
    throttle: float = 60.0,
    seed: int = 99
) -> pd.DataFrame:
    """
    Runs M1's real FaultedSimulator and returns residuals in M2 schema.

    Requires twin_core to be installed (M1's package).
    Raises ImportError if twin_core is not available.

    Args:
        fault_type: One of 'misfire', 'injector_fault', 'overheating',
                    'oil_pressure_drop', 'vibration_spike'.
        fault_time: Simulation time (s) when fault activates.
        duration:   Total mission duration in seconds.
        dt:         Simulation timestep in seconds.
        throttle:   Steady-state throttle command (%).
        seed:       Random seed.

    Returns:
        pd.DataFrame with columns: timestamp, res_rpm, res_cht, res_egt,
        res_oil_p, res_oil_t, res_fuel, res_vib, fault_label.
    """
    # Dynamically load M1's real modules (avoids IDE unresolved-import warnings
    # for optional twin_core dependency that may not be installed).
    import importlib
    _m1 = importlib.import_module("m1_real_data")           # raises ImportError if missing
    FaultedSimulator = _m1.FaultedSimulator
    _twin_mod = importlib.import_module("twin_core.twin")   # raises ImportError if missing
    DigitalTwin = _twin_mod.DigitalTwin
    _res_mod = importlib.import_module("twin_core.residual")
    ResidualEngine = _res_mod.ResidualEngine

    faulted = FaultedSimulator(
        fault_type=fault_type,
        fault_time=fault_time,
        seed=seed,
    )
    twin = DigitalTwin(actual_source=faulted.step)
    residual_eng = ResidualEngine()

    n_steps = int(duration / dt)
    profile = [throttle] * n_steps
    pairs = twin.run(profile, dt)
    results = residual_eng.process_batch(pairs)

    rows = []
    for r in results:
        row = {"timestamp": r["timestamp"]}
        for m1_key, m2_col in M1_TO_M2_CHANNEL_MAP.items():
            row[m2_col] = r["residuals"].get(m1_key, 0.0)
        row["fault_label"] = (
            fault_type if r["timestamp"] >= fault_time else "healthy"
        )
        rows.append(row)

    return pd.DataFrame(rows)


# ------------------------------------------------------------------
# Fallback: synthetic residuals (same schema, used when twin_core absent)
# ------------------------------------------------------------------

RESIDUAL_NOISE_STD = {
    "res_rpm":   15.0,
    "res_cht":    1.5,
    "res_egt":    3.0,
    "res_oil_p":  0.05,
    "res_oil_t":  1.0,
    "res_fuel":   0.3,
    "res_vib":    0.02,
}


def generate_m1_residuals(
    duration_min: float = 150.0,
    sample_rate_hz: float = 2.0,
    seed: int = 42
) -> pd.DataFrame:
    """
    PRIMARY: Tries to use M1's real FaultedSimulator via twin_core.
    FALLBACK: Generates synthetic residuals if twin_core is unavailable.

    Returns:
        pd.DataFrame with columns: timestamp, res_rpm, res_cht, res_egt,
        res_oil_p, res_oil_t, res_fuel, res_vib, fault_label.
    """
    try:
        print("  [M1 Interface] Attempting to use M1 real FaultedSimulator...")
        df = generate_m1_residuals_real(duration=duration_min * 60.0, dt=1.0 / sample_rate_hz)
        print("  [M1 Interface] Successfully loaded M1 real residuals.")
        return df
    except ImportError:
        print("  [M1 Interface] twin_core not found — using synthetic fallback.")
        return _generate_synthetic_residuals(duration_min, sample_rate_hz, seed)


def _generate_synthetic_residuals(
    duration_min: float = 150.0,
    sample_rate_hz: float = 2.0,
    seed: int = 42
) -> pd.DataFrame:
    """Synthetic M1 residual fallback (3-phase mission: healthy → degraded → misfire)."""
    rng = np.random.default_rng(seed)
    n_samples = int(duration_min * 60 * sample_rate_hz)
    timestamps = np.linspace(0, duration_min * 60, n_samples, endpoint=False)
    time_min = timestamps / 60.0

    res_rpm   = rng.normal(0, RESIDUAL_NOISE_STD["res_rpm"], n_samples)
    res_cht   = rng.normal(0, RESIDUAL_NOISE_STD["res_cht"], n_samples)
    res_egt   = rng.normal(0, RESIDUAL_NOISE_STD["res_egt"], n_samples)
    res_oil_p = rng.normal(0, RESIDUAL_NOISE_STD["res_oil_p"], n_samples)
    res_oil_t = rng.normal(0, RESIDUAL_NOISE_STD["res_oil_t"], n_samples)
    res_fuel  = rng.normal(0, RESIDUAL_NOISE_STD["res_fuel"], n_samples)
    res_vib   = rng.normal(0, RESIDUAL_NOISE_STD["res_vib"], n_samples)
    fault_labels = np.full(n_samples, "healthy", dtype=object)

    # Phase 2: Degradation (60–120 min)
    phase2_mask = (time_min >= 60) & (time_min < 120)
    p2 = np.clip((time_min[phase2_mask] - 60) / 60.0, 0, 1)
    res_cht[phase2_mask]   += p2 * 25.0
    res_egt[phase2_mask]   += p2 * 45.0
    res_oil_p[phase2_mask] -= p2 * 1.2
    res_oil_t[phase2_mask] += p2 * 12.0
    res_vib[phase2_mask]   += p2 * 0.15
    fault_labels[phase2_mask] = "degraded"

    # Phase 3: Misfire (120–150 min)
    phase3_mask = (time_min >= 120)
    p3 = np.clip((time_min[phase3_mask] - 120) / 30.0, 0, 1)
    n3 = phase3_mask.sum()
    res_rpm[phase3_mask] -= p3 * 200 + rng.normal(0, 40, n3)
    res_vib[phase3_mask] += p3 * 0.8 + rng.normal(0, 0.1, n3)
    res_cht[phase3_mask] += 25.0 + p3 * 15.0 + rng.normal(0, 5.0, n3)
    res_egt[phase3_mask] += 45.0 + p3 * 30.0 + rng.normal(0, 8.0, n3)
    res_oil_p[phase3_mask] -= 1.2 + p3 * 0.8
    res_fuel[phase3_mask] += p3 * 3.0
    fault_labels[phase3_mask] = "misfire"

    return pd.DataFrame({
        "timestamp":   timestamps,
        "res_rpm":     res_rpm,
        "res_cht":     res_cht,
        "res_egt":     res_egt,
        "res_oil_p":   res_oil_p,
        "res_oil_t":   res_oil_t,
        "res_fuel":    res_fuel,
        "res_vib":     res_vib,
        "fault_label": fault_labels,
    })


def save_sample_data(output_dir: str = "data") -> str:
    """Saves M1 residual data (real or synthetic) to a CSV."""
    os.makedirs(output_dir, exist_ok=True)
    df_res = generate_m1_residuals()
    res_path = os.path.join(output_dir, "m1_residual_sample.csv")
    df_res.to_csv(res_path, index=False, float_format="%.4f")
    return res_path


def _self_test():
    """Self-test: validates residual data structure and fault labels."""
    df_res = generate_m1_residuals(duration_min=150.0, sample_rate_hz=2.0)

    expected_cols = {
        "timestamp", "res_rpm", "res_cht", "res_egt",
        "res_oil_p", "res_oil_t", "res_fuel", "res_vib", "fault_label"
    }
    assert set(df_res.columns) == expected_cols, f"Columns mismatch: {set(df_res.columns)}"
    labels = set(df_res["fault_label"].unique())
    print(f"  Samples: {len(df_res)}")
    print(f"  Fault labels: {labels}")
    print("[PASS] _dev_fault_stub.py self-test passed!")


if __name__ == "__main__":
    _self_test()
    path = save_sample_data()
    print(f"  Saved: {path}")
