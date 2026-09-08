"""
ewma.py — M2 Exponentially Weighted Moving Average Smoothing (SIH26054)
Reduces high-frequency sensor noise from residuals and degradation scores.
"""

import pandas as pd
import numpy as np


def apply_ewma_series(series: pd.Series, span: float = 15.0) -> pd.Series:
    """
    Applies EWMA smoothing to a single Series.

    Args:
        series: Input 1D data.
        span:   Decay span (span = 2/alpha - 1). Default 15 samples.

    Returns:
        Smoothed Series (same length).
    """
    return series.ewm(span=span, adjust=False).mean()


def apply_ewma_dataframe(
    df: pd.DataFrame,
    columns: list = None,
    span: float = 15.0,
    suffix: str = "_ewma"
) -> pd.DataFrame:
    """
    Applies EWMA to specified columns and appends smoothed columns.

    Args:
        df:      Input DataFrame.
        columns: Columns to smooth. If None, all numeric non-timestamp columns.
        span:    Decay span.
        suffix:  Suffix for smoothed column names.

    Returns:
        DataFrame with original + smoothed columns appended.
    """
    out = df.copy()
    if columns is None:
        columns = [
            c for c in df.columns
            if pd.api.types.is_numeric_dtype(df[c]) and c != "timestamp"
        ]

    for col in columns:
        if col in df.columns:
            out[f"{col}{suffix}"] = apply_ewma_series(df[col], span=span)

    return out


def _self_test():
    """Self-test: validates EWMA reduces variance."""
    rng = np.random.default_rng(42)
    raw = pd.Series(np.sin(np.linspace(0, 10, 200)) + rng.normal(0, 0.3, 200))
    smoothed = apply_ewma_series(raw, span=10)

    assert len(smoothed) == len(raw), "Length mismatch"
    assert smoothed.std() < raw.std(), "EWMA should reduce variance"

    # DataFrame test
    df = pd.DataFrame({"timestamp": range(50), "val": rng.normal(0, 1, 50)})
    df_out = apply_ewma_dataframe(df, span=5)
    assert "val_ewma" in df_out.columns, "Should add _ewma column"
    assert df_out["val_ewma"].std() < df_out["val"].std(), "EWMA should reduce variance"

    print("[PASS] ewma.py self-test passed!")


if __name__ == "__main__":
    _self_test()
