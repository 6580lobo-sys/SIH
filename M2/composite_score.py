"""
composite_score.py — M2 Composite Degradation Score (SIH26054)
Aggregates normalized residuals into a single severity indicator.
D(t) = sqrt( sum( w_i * norm_res_i(t)^2 ) )
"""

import pandas as pd
import numpy as np


# Weights prioritize parameters most critical to piston engine health
DEFAULT_WEIGHTS: dict = {
    "norm_res_oil_p": 0.25,   # Oil pressure: vital engine life parameter
    "norm_res_cht":   0.20,   # CHT: cylinder thermal stress
    "norm_res_egt":   0.15,   # EGT: combustion efficiency / misfire indicator
    "norm_res_vib":   0.15,   # Vibration: mechanical / bearing wear
    "norm_res_oil_t": 0.10,   # Oil temperature: cooling / friction
    "norm_res_rpm":   0.10,   # RPM: governor usually compensates until severe failure
    "norm_res_fuel":  0.05,   # Fuel flow: secondary indicator
}


def compute_composite_score(
    norm_df: pd.DataFrame,
    weights: dict = None
) -> pd.Series:
    """
    Computes weighted root-mean-square composite degradation score.

    Args:
        norm_df: DataFrame with norm_res_* columns.
        weights: {col_name: weight}. Must sum to 1.0. Defaults to DEFAULT_WEIGHTS.

    Returns:
        Series of composite degradation scores (>= 0, higher = worse).
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS

    # Validate weights sum to 1.0
    w_sum = sum(weights.values())
    if not np.isclose(w_sum, 1.0, atol=1e-6):
        raise ValueError(f"Weights must sum to 1.0, got {w_sum:.6f}")

    n = len(norm_df)
    score = np.zeros(n)

    for col, w in weights.items():
        if col in norm_df.columns:
            score += w * (norm_df[col].values ** 2)
        # If column missing, that weight contributes 0 (graceful degradation)

    return pd.Series(np.sqrt(score), name="composite_score")


def _self_test():
    """Self-test: validates composite score computation."""
    # Case 1: All zeros → composite = 0
    df_zero = pd.DataFrame({col: [0.0] for col in DEFAULT_WEIGHTS})
    score_zero = compute_composite_score(df_zero)
    assert np.isclose(score_zero.iloc[0], 0.0), "All zeros should give composite=0"

    # Case 2: Single deviation
    df_single = pd.DataFrame({col: [0.0] for col in DEFAULT_WEIGHTS})
    df_single["norm_res_oil_p"] = [2.0]
    score_single = compute_composite_score(df_single)
    expected = np.sqrt(0.25 * 4.0)  # sqrt(w_oil_p * 2^2) = sqrt(1.0) = 1.0
    assert np.isclose(score_single.iloc[0], expected), f"Expected {expected}, got {score_single.iloc[0]}"

    # Case 3: Invalid weights
    try:
        compute_composite_score(df_zero, weights={"a": 0.5})
        assert False, "Should have raised ValueError"
    except ValueError:
        pass

    print("[PASS] composite_score.py self-test passed!")


if __name__ == "__main__":
    _self_test()
