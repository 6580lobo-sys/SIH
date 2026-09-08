"""
health_index.py — M2 Health Index (SIH26054)
Maps composite degradation score to Health Index (0-100, higher = healthier).
HI(t) = 100 * exp(-k * D(t))

Thresholds:
  HI >= 70  -> "healthy"
  40 <= HI < 70 -> "degraded"
  HI < 40  -> "critical"

ISO Severity Classification (Aerospace Maintenance Alert Levels):
  HI > 85   -> "NORMAL"         — Healthy flight, no action required
  70 < HI <= 85 -> "ADVISORY"   — Early degradation detected, monitor closely
  40 < HI <= 70 -> "WARNING"    — Significant degradation, plan maintenance
  HI <= 40  -> "CRITICAL_RTB"   — Return to base immediately
"""

import pandas as pd
import numpy as np


# Health status thresholds
HEALTHY_THRESHOLD = 70.0
DEGRADED_THRESHOLD = 40.0

# ISO Severity thresholds (aerospace standard alert levels)
SEVERITY_NORMAL_THRESHOLD = 85.0      # HI > 85
SEVERITY_ADVISORY_THRESHOLD = 70.0    # 70 < HI <= 85
SEVERITY_WARNING_THRESHOLD = 40.0     # 40 < HI <= 70
# Below 40 -> CRITICAL_RTB

VALID_SEVERITY_LEVELS = {"NORMAL", "ADVISORY", "WARNING", "CRITICAL_RTB"}


def compute_health_index(composite_score, k: float = 0.5):
    """
    Maps composite degradation score to health index [0, 100].

    Args:
        composite_score: float or pd.Series of composite scores (>= 0).
        k: Exponential decay constant (default 0.5).

    Returns:
        float or pd.Series of health index values, clamped to [0, 100].
    """
    hi = 100.0 * np.exp(-k * np.abs(composite_score))
    if isinstance(hi, pd.Series):
        return hi.clip(0.0, 100.0)
    return float(np.clip(hi, 0.0, 100.0))


def compute_health_status(health_index):
    """
    Derives health status string from health index.

    Args:
        health_index: float or pd.Series.

    Returns:
        str or pd.Series of {"healthy", "degraded", "critical"}.
    """
    if isinstance(health_index, pd.Series):
        return pd.Series(
            np.where(
                health_index >= HEALTHY_THRESHOLD, "healthy",
                np.where(health_index >= DEGRADED_THRESHOLD, "degraded", "critical")
            ),
            index=health_index.index,
            name="health_status"
        )
    if health_index >= HEALTHY_THRESHOLD:
        return "healthy"
    elif health_index >= DEGRADED_THRESHOLD:
        return "degraded"
    else:
        return "critical"


def compute_severity_level(health_index):
    """
    Maps health index to ISO-style aerospace maintenance severity levels.

    Classification:
        HI > 85   -> NORMAL         — Healthy flight, no action required
        70 < HI <= 85 -> ADVISORY   — Early degradation detected, monitor closely
        40 < HI <= 70 -> WARNING    — Significant degradation, plan maintenance
        HI <= 40  -> CRITICAL_RTB   — Return to base immediately

    Args:
        health_index: float or pd.Series of health index values [0, 100].

    Returns:
        str or pd.Series of {"NORMAL", "ADVISORY", "WARNING", "CRITICAL_RTB"}.
    """
    if isinstance(health_index, pd.Series):
        return pd.Series(
            np.where(
                health_index > SEVERITY_NORMAL_THRESHOLD, "NORMAL",
                np.where(
                    health_index > SEVERITY_ADVISORY_THRESHOLD, "ADVISORY",
                    np.where(
                        health_index > SEVERITY_WARNING_THRESHOLD, "WARNING",
                        "CRITICAL_RTB"
                    )
                )
            ),
            index=health_index.index,
            name="severity_level"
        )
    if health_index > SEVERITY_NORMAL_THRESHOLD:
        return "NORMAL"
    elif health_index > SEVERITY_ADVISORY_THRESHOLD:
        return "ADVISORY"
    elif health_index > SEVERITY_WARNING_THRESHOLD:
        return "WARNING"
    else:
        return "CRITICAL_RTB"


def add_health_columns(df: pd.DataFrame, k: float = 0.5) -> pd.DataFrame:
    """
    Adds health_index, health_status, and severity_level columns to a DataFrame.
    Requires 'composite_score' column to exist.

    Args:
        df: DataFrame with 'composite_score' column.
        k:  Exponential decay constant.

    Returns:
        DataFrame with added health_index, health_status, and severity_level columns.
    """
    if "composite_score" not in df.columns:
        raise KeyError("DataFrame must contain 'composite_score' column.")

    out = df.copy()
    out["health_index"] = compute_health_index(df["composite_score"], k=k)
    out["health_status"] = compute_health_status(out["health_index"])
    out["severity_level"] = compute_severity_level(out["health_index"])
    return out


def _self_test():
    """Self-test: validates health index mapping, status thresholds, and severity levels."""
    # Scalar tests
    assert np.isclose(compute_health_index(0.0), 100.0), "D=0 -> HI=100"
    hi_25 = compute_health_index(2.5)
    assert 20.0 <= hi_25 <= 35.0, f"D=2.5 -> HI should be in [20,35], got {hi_25}"
    assert compute_health_index(0.0) == 100.0

    # Status tests
    assert compute_health_status(90.0) == "healthy"
    assert compute_health_status(70.0) == "healthy"
    assert compute_health_status(50.0) == "degraded"
    assert compute_health_status(40.0) == "degraded"
    assert compute_health_status(39.9) == "critical"
    assert compute_health_status(0.0) == "critical"

    # Severity level scalar tests
    assert compute_severity_level(95.0) == "NORMAL"
    assert compute_severity_level(86.0) == "NORMAL"
    assert compute_severity_level(85.0) == "ADVISORY"     # boundary: 85 is NOT > 85
    assert compute_severity_level(75.0) == "ADVISORY"
    assert compute_severity_level(70.0) == "WARNING"       # boundary: 70 is NOT > 70
    assert compute_severity_level(50.0) == "WARNING"
    assert compute_severity_level(40.0) == "CRITICAL_RTB"  # boundary: 40 is NOT > 40
    assert compute_severity_level(20.0) == "CRITICAL_RTB"
    assert compute_severity_level(0.0) == "CRITICAL_RTB"

    # Vectorized test
    scores = pd.Series([0.0, 0.5, 1.0, 2.0, 3.0, 5.0])
    hi = compute_health_index(scores)
    assert len(hi) == 6
    assert hi.iloc[0] == 100.0
    assert all(0 <= v <= 100 for v in hi)
    assert hi.is_monotonic_decreasing, "Health should decrease as degradation increases"

    status = compute_health_status(hi)
    assert set(status.unique()).issubset({"healthy", "degraded", "critical"})

    # Severity vectorized test
    severity = compute_severity_level(hi)
    assert set(severity.unique()).issubset(VALID_SEVERITY_LEVELS)
    assert severity.iloc[0] == "NORMAL"  # HI=100 -> NORMAL

    # DataFrame test
    df = pd.DataFrame({"composite_score": [0.0, 0.5, 1.5, 3.0]})
    df_out = add_health_columns(df)
    assert "health_index" in df_out.columns
    assert "health_status" in df_out.columns
    assert "severity_level" in df_out.columns
    assert df_out["health_index"].iloc[0] == 100.0
    assert df_out["severity_level"].iloc[0] == "NORMAL"

    print(f"  Severity distribution: {severity.value_counts().to_dict()}")
    print("[PASS] health_index.py self-test passed!")


if __name__ == "__main__":
    _self_test()

