"""
rul_uncertainty.py — M2 RUL Uncertainty Bands (SIH26054)
Computes 95% confidence interval on RUL using regression slope standard error.

Pessimistic (shorter RUL): steeper slope = slope - t95 * stderr
Optimistic (longer RUL):  shallower slope = slope + t95 * stderr

Fallback: +/-25% bands when window < 10 samples.
"""

import pandas as pd
import numpy as np
from scipy.stats import linregress, t as t_dist


def estimate_rul_with_uncertainty(
    health_series: pd.Series,
    timestamps_sec: pd.Series,
    window: int = 20,
    eol_threshold: float = 20.0,
    mission_duration_hours: float = 8.0,
    hi_trigger: float = 85.0,
    ci: float = 0.95
) -> tuple:
    """
    Estimates RUL with uncertainty bounds.

    Args:
        health_series:          Series of health_index values.
        timestamps_sec:         Series of timestamps in seconds.
        window:                 Regression window size.
        eol_threshold:          Health index at end-of-life.
        mission_duration_hours: Operator-set mission duration.
        hi_trigger:             Only estimate when HI < this.
        ci:                     Confidence level for bands (default 0.95).

    Returns:
        (rul_est, rul_lower, rul_upper, rul_status):
          All floats in minutes. NaN when not_estimable.
    """
    nan3 = (float("nan"), float("nan"), float("nan"), "not_estimable")
    max_rul_min = mission_duration_hours * 60.0
    n = len(health_series)

    if n < 5:
        return nan3

    current_hi = health_series.iloc[-1]

    if current_hi <= eol_threshold:
        return (0.0, 0.0, 0.0, "estimable")

    if current_hi >= hi_trigger:
        return nan3

    w = min(window, n)
    hi_w = health_series.iloc[-w:].values
    ts_w = timestamps_sec.iloc[-w:].values
    ts_min = ts_w / 60.0

    if len(hi_w) < 5:
        return nan3

    slope, intercept, r_value, p_value, stderr = linregress(ts_min, hi_w)

    # Stable or improving
    if slope >= -0.01:
        return nan3

    # Point RUL estimate
    rul_est = (eol_threshold - current_hi) / slope
    rul_est = max(0.0, rul_est)

    # Uncertainty bands
    use_fallback = (w < 10) or (stderr <= 0) or np.isnan(stderr)

    if use_fallback:
        # Fallback: +/- 25%
        rul_lower = rul_est * 0.75
        rul_upper = rul_est * 1.25
    else:
        # t-distribution critical value for 95% CI
        dof = max(w - 2, 1)
        t_crit = t_dist.ppf(1.0 - (1.0 - ci) / 2.0, dof)

        slope_pessimistic = slope - t_crit * stderr  # more negative = steeper
        slope_optimistic = slope + t_crit * stderr   # less negative = shallower

        # Pessimistic bound (shorter RUL — steeper slope)
        if slope_pessimistic < -0.001:
            rul_lower = max(0.0, (eol_threshold - current_hi) / slope_pessimistic)
        else:
            rul_lower = rul_est * 0.75  # fallback

        # Optimistic bound (longer RUL — shallower slope)
        if slope_optimistic < -0.001:
            rul_upper = max(0.0, (eol_threshold - current_hi) / slope_optimistic)
        else:
            rul_upper = max_rul_min  # very shallow slope → beyond horizon

    # Clamp all to [0, max_rul_min]
    rul_est = np.clip(rul_est, 0.0, max_rul_min)
    rul_lower = np.clip(rul_lower, 0.0, max_rul_min)
    rul_upper = np.clip(rul_upper, 0.0, max_rul_min)

    # Ensure ordering: lower <= est <= upper
    rul_lower = min(rul_lower, rul_est)
    rul_upper = max(rul_upper, rul_est)

    # Determine status
    if rul_est >= max_rul_min:
        rul_status = "beyond_horizon"
    else:
        rul_status = "estimable"

    return (float(rul_est), float(rul_lower), float(rul_upper), rul_status)


def add_rul_columns(
    df: pd.DataFrame,
    window: int = 20,
    eol_threshold: float = 20.0,
    mission_duration_hours: float = 8.0,
    hi_trigger: float = 85.0,
    ci: float = 0.95
) -> pd.DataFrame:
    """
    Adds rul_est, rul_lower, rul_upper (float), and rul_status (str) columns.

    Args:
        df: DataFrame with 'health_index' and 'timestamp' columns.

    Returns:
        DataFrame with RUL columns added.
    """
    if "health_index" not in df.columns:
        raise KeyError("DataFrame must contain 'health_index' column.")
    if "timestamp" not in df.columns:
        raise KeyError("DataFrame must contain 'timestamp' column.")

    n = len(df)
    rul_est = np.full(n, float("nan"))
    rul_lower = np.full(n, float("nan"))
    rul_upper = np.full(n, float("nan"))
    rul_status = np.full(n, "not_estimable", dtype=object)

    hi = df["health_index"]
    ts = df["timestamp"]

    for i in range(n):
        est, lo, hi_val, status = estimate_rul_with_uncertainty(
            hi.iloc[:i + 1],
            ts.iloc[:i + 1],
            window=window,
            eol_threshold=eol_threshold,
            mission_duration_hours=mission_duration_hours,
            hi_trigger=hi_trigger,
            ci=ci,
        )
        rul_est[i] = est
        rul_lower[i] = lo
        rul_upper[i] = hi_val
        rul_status[i] = status

    out = df.copy()
    out["rul_est"] = rul_est
    out["rul_lower"] = rul_lower
    out["rul_upper"] = rul_upper
    out["rul_status"] = rul_status
    return out


def _self_test():
    """Self-test: validates RUL uncertainty bounds."""
    n = 50
    ts = pd.Series(np.linspace(0, 600, n))  # 10 min
    hi = pd.Series(np.linspace(80, 30, n))  # degrading

    est, lo, up, status = estimate_rul_with_uncertainty(
        hi, ts, window=20, mission_duration_hours=8.0
    )

    # Basic checks
    assert not np.isnan(est), "RUL should be finite"
    assert not np.isnan(lo), "Lower bound should be finite"
    assert not np.isnan(up), "Upper bound should be finite"
    assert lo <= est <= up, f"Must have lower <= est <= upper: {lo} <= {est} <= {up}"
    assert status == "estimable", f"Expected estimable, got {status}"

    # Not estimable cases
    hi_flat = pd.Series(np.full(50, 90.0))
    _, _, _, status_flat = estimate_rul_with_uncertainty(hi_flat, ts)
    assert status_flat == "not_estimable"

    # EOL case
    hi_eol = pd.Series(np.linspace(50, 15, 50))
    est_eol, lo_eol, up_eol, status_eol = estimate_rul_with_uncertainty(hi_eol, ts)
    assert est_eol == 0.0
    assert lo_eol == 0.0
    assert up_eol == 0.0
    assert status_eol == "estimable"

    # Configurable mission horizon
    est_6, lo_6, up_6, st_6 = estimate_rul_with_uncertainty(
        hi, ts, mission_duration_hours=6.0
    )
    est_10, lo_10, up_10, st_10 = estimate_rul_with_uncertainty(
        hi, ts, mission_duration_hours=10.0
    )
    # Both should clamp differently if RUL exceeds horizon
    assert up_6 <= 360.0, f"6h mission: upper should be <= 360, got {up_6}"
    assert up_10 <= 600.0, f"10h mission: upper should be <= 600, got {up_10}"

    # All NaN when not estimable
    _, lo_ne, up_ne, _ = estimate_rul_with_uncertainty(hi_flat, ts)
    assert np.isnan(lo_ne) and np.isnan(up_ne), "Both bands NaN when not estimable"

    # Type checks
    assert isinstance(est, float), "rul_est must be float"
    assert isinstance(lo, float), "rul_lower must be float"
    assert isinstance(up, float), "rul_upper must be float"
    assert isinstance(status, str), "rul_status must be str"

    print("[PASS] rul_uncertainty.py self-test passed!")


if __name__ == "__main__":
    _self_test()
