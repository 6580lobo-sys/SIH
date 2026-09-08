"""
rul_baseline.py — M2 Baseline Rule-Based RUL (SIH26054)
Estimates Remaining Useful Life by linear extrapolation of health index trend.

RUL = (EOL_threshold - current_HI) / |health_slope_per_minute|

Mission-configurable: max_rul_min = mission_duration_hours * 60
"""

import pandas as pd
import numpy as np
from scipy.stats import linregress


def estimate_rul_point(
    health_series: pd.Series,
    timestamps_sec: pd.Series,
    window: int = 20,
    eol_threshold: float = 20.0,
    mission_duration_hours: float = 8.0,
    hi_trigger: float = 85.0
) -> tuple:
    """
    Estimates RUL from the most recent 'window' samples of health index.

    Args:
        health_series:        Series of health_index values.
        timestamps_sec:       Series of timestamps in seconds.
        window:               Number of recent samples for regression.
        eol_threshold:        Health index at end-of-life.
        mission_duration_hours: Operator-set mission duration.
        hi_trigger:           Only estimate RUL when HI < this value.

    Returns:
        (rul_est, rul_status):
          rul_est: float minutes (NaN if not estimable)
          rul_status: "estimable" | "not_estimable" | "beyond_horizon"
    """
    max_rul_min = mission_duration_hours * 60.0
    n = len(health_series)

    # Not enough data
    if n < 5:
        return float("nan"), "not_estimable"

    # Current health index
    current_hi = health_series.iloc[-1]

    # Already at or past EOL
    if current_hi <= eol_threshold:
        return 0.0, "estimable"

    # Health is stable / healthy — no RUL estimation
    if current_hi >= hi_trigger:
        return float("nan"), "not_estimable"

    # Take last 'window' samples
    w = min(window, n)
    hi_w = health_series.iloc[-w:].values
    ts_w = timestamps_sec.iloc[-w:].values

    # Convert timestamps to minutes for slope
    ts_min = ts_w / 60.0

    # Need at least 5 points for meaningful regression
    if len(hi_w) < 5:
        return float("nan"), "not_estimable"

    slope, intercept, _, _, _ = linregress(ts_min, hi_w)

    # Slope >= 0 means health is stable or improving
    if slope >= -0.01:
        return float("nan"), "not_estimable"

    # Extrapolate time to reach EOL threshold
    rul_min = (eol_threshold - current_hi) / slope  # slope is negative, so rul is positive

    # Clamp to non-negative
    rul_min = max(0.0, rul_min)

    # Check against mission horizon
    if rul_min > max_rul_min:
        return max_rul_min, "beyond_horizon"

    return rul_min, "estimable"


def estimate_rul_series(
    df: pd.DataFrame,
    window: int = 20,
    eol_threshold: float = 20.0,
    mission_duration_hours: float = 8.0,
    hi_trigger: float = 85.0
) -> pd.DataFrame:
    """
    Computes rolling RUL estimation for each row.

    Args:
        df: DataFrame with 'health_index' and 'timestamp' columns.
        window: Regression window size.
        eol_threshold: EOL health threshold.
        mission_duration_hours: Mission duration for RUL horizon.
        hi_trigger: Health index trigger for RUL estimation.

    Returns:
        DataFrame with 'rul_est' (float) and 'rul_status' (str) columns.
    """
    if "health_index" not in df.columns:
        raise KeyError("DataFrame must contain 'health_index' column.")
    if "timestamp" not in df.columns:
        raise KeyError("DataFrame must contain 'timestamp' column.")

    n = len(df)
    rul_est = np.full(n, float("nan"))
    rul_status = np.full(n, "not_estimable", dtype=object)

    hi = df["health_index"]
    ts = df["timestamp"]

    for i in range(n):
        est, status = estimate_rul_point(
            hi.iloc[:i + 1],
            ts.iloc[:i + 1],
            window=window,
            eol_threshold=eol_threshold,
            mission_duration_hours=mission_duration_hours,
            hi_trigger=hi_trigger,
        )
        rul_est[i] = est
        rul_status[i] = status

    return pd.DataFrame({"rul_est": rul_est, "rul_status": rul_status})


def _self_test():
    """Self-test: validates RUL estimation logic."""
    # Case 1: Linearly decreasing health -> finite RUL
    n = 50
    ts = pd.Series(np.linspace(0, 600, n))  # 0-10 min in seconds
    hi = pd.Series(np.linspace(80, 30, n))  # 80 -> 30 over 10 min

    rul, status = estimate_rul_point(hi, ts, window=20, mission_duration_hours=8.0)
    assert not np.isnan(rul), f"Should be finite, got NaN"
    assert rul > 0, f"RUL should be positive, got {rul}"
    assert status == "estimable", f"Status should be estimable, got {status}"

    # Case 2: Flat/increasing health -> not estimable
    hi_flat = pd.Series(np.full(50, 90.0))
    rul_flat, status_flat = estimate_rul_point(hi_flat, ts, mission_duration_hours=8.0)
    assert np.isnan(rul_flat), "Flat health should give NaN RUL"
    assert status_flat == "not_estimable"

    # Case 3: Health at EOL -> RUL = 0
    hi_eol = pd.Series(np.linspace(50, 15, 50))
    rul_eol, status_eol = estimate_rul_point(hi_eol, ts, mission_duration_hours=8.0)
    assert rul_eol == 0.0, f"At EOL, RUL should be 0, got {rul_eol}"
    assert status_eol == "estimable"

    # Case 4: Very slow degradation -> beyond_horizon
    hi_slow = pd.Series(np.linspace(84.9, 84.0, 50))
    rul_slow, status_slow = estimate_rul_point(
        hi_slow, ts, window=20, mission_duration_hours=1.0  # short mission
    )
    # With mission=1h (60 min) and very slow decay, should hit horizon or not_estimable
    assert status_slow in ("beyond_horizon", "not_estimable"), f"Got {status_slow}"

    # Case 5: Configurable mission duration
    rul_6h, _ = estimate_rul_point(hi, ts, mission_duration_hours=6.0)
    rul_10h, _ = estimate_rul_point(hi, ts, mission_duration_hours=10.0)
    # Both should be finite and equal (same data, horizon just changes clamping)
    assert not np.isnan(rul_6h), "Should be finite for 6h mission"

    # Case 6: Insufficient data
    rul_short, status_short = estimate_rul_point(
        pd.Series([80.0, 75.0]), pd.Series([0.0, 1.0])
    )
    assert np.isnan(rul_short)
    assert status_short == "not_estimable"

    # Case 7: rul_est is always float, rul_status is always str
    assert isinstance(rul, float), "rul_est must be float"
    assert isinstance(status, str), "rul_status must be str"

    print("[PASS] rul_baseline.py self-test passed!")


if __name__ == "__main__":
    _self_test()
