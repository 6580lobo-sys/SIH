"""
normalization.py — M2 Residual Normalization (SIH26054)
Scales residuals by parameter-specific nominal tolerance bounds
so different units (RPM, degC, bar, etc.) become comparable.
"""

import pandas as pd
import numpy as np


# Nominal allowable deviation bounds for UAV aero-piston engines (healthy operation)
DEFAULT_BOUNDS: dict = {
    "res_rpm":   150.0,    # +/- 150 RPM
    "res_cht":    20.0,    # +/- 20 degC
    "res_egt":    40.0,    # +/- 40 degC
    "res_oil_p":   0.8,   # +/- 0.8 bar
    "res_oil_t":  15.0,   # +/- 15 degC
    "res_fuel":    2.0,    # +/- 2.0 kg/h
    "res_vib":     0.35,   # +/- 0.35 arb units
}


def normalize_residuals(
    res_df: pd.DataFrame,
    bounds: dict = None,
    clip_value: float = 10.0
) -> pd.DataFrame:
    """
    Normalizes each residual by dividing by its tolerance bound.
    Sign is preserved. Output columns are named 'norm_res_*'.

    Args:
        res_df:     DataFrame with res_* columns.
        bounds:     {col_name: bound_value}. Defaults to DEFAULT_BOUNDS.
        clip_value: Max absolute normalized value (prevents outlier explosion).

    Returns:
        DataFrame with timestamp, norm_res_* columns, and fault_label if present.
    """
    if bounds is None:
        bounds = DEFAULT_BOUNDS

    norm_df = pd.DataFrame(index=res_df.index)

    if "timestamp" in res_df.columns:
        norm_df["timestamp"] = res_df["timestamp"].values

    for col, bound in bounds.items():
        if col in res_df.columns:
            norm_col = col.replace("res_", "norm_res_")
            vals = res_df[col].values / bound
            if clip_value is not None:
                vals = np.clip(vals, -clip_value, clip_value)
            norm_df[norm_col] = vals

    if "fault_label" in res_df.columns:
        norm_df["fault_label"] = res_df["fault_label"].values

    return norm_df


def _self_test():
    """Self-test: validates normalization scaling and clipping."""
    df = pd.DataFrame({
        "timestamp": [0.0, 1.0, 2.0],
        "res_cht":   [20.0, -40.0, 300.0],    # 300 should clip after norm
        "res_oil_p": [-0.8, -1.6, 0.0],
        "fault_label": ["healthy", "degraded", "healthy"]
    })

    norm = normalize_residuals(df)

    assert np.isclose(norm["norm_res_cht"].iloc[0], 1.0), "20/20 should be 1.0"
    assert np.isclose(norm["norm_res_cht"].iloc[1], -2.0), "-40/20 should be -2.0"
    assert np.isclose(norm["norm_res_cht"].iloc[2], 10.0), "300/20=15 should clip to 10"
    assert np.isclose(norm["norm_res_oil_p"].iloc[0], -1.0), "-0.8/0.8 should be -1.0"
    assert "fault_label" in norm.columns, "fault_label must pass through"

    print("[PASS] normalization.py self-test passed!")


if __name__ == "__main__":
    _self_test()
