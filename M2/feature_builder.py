"""
feature_builder.py — M2 Feature Engineering & Prognostics Pipeline (SIH26054)
Consumes M1 Residual inputs (res_* columns), normalizes them, and computes:
- Anomaly composite score + EWMA
- Health Index (0–100%) & ISO 13381-1 Severity Levels
- Remaining Useful Life (RUL) with confidence intervals (95% CI)
- Engineered feature set for M4 downstream models.
"""

import json
import os
import pandas as pd
import numpy as np

from normalization import normalize_residuals
from ewma import apply_ewma_series, apply_ewma_dataframe
from composite_score import compute_composite_score
from health_index import compute_health_index, compute_health_status, compute_severity_level, VALID_SEVERITY_LEVELS
from rul_uncertainty import add_rul_columns


# Required input residual columns from M1
REQUIRED_RESIDUAL_COLS = [
    "res_rpm", "res_cht", "res_egt", "res_oil_p", "res_oil_t", "res_fuel", "res_vib"
]

# Required output columns in standard order
REQUIRED_COLUMNS = [
    "timestamp",
    "res_rpm", "res_cht", "res_egt", "res_oil_p", "res_oil_t", "res_fuel", "res_vib",
    "composite_score", "composite_ewma",
    "health_index", "health_status", "severity_level",
    "rul_est", "rul_lower", "rul_upper", "rul_status",
    "health_slope",
    "res_cht_ewma", "res_egt_ewma", "res_vib_std_w",
    "fault_label",
]

NUMERIC_RUL_COLS = ["rul_est", "rul_lower", "rul_upper"]
VALID_RUL_STATUSES = {"estimable", "not_estimable", "beyond_horizon"}
VALID_HEALTH_STATUSES = {"healthy", "degraded", "critical"}


def build_feature_table(
    df_res: pd.DataFrame,
    mission_duration_hours: float = 8.0,
    ewma_span: float = 15.0,
    rul_window: int = 20,
    health_k: float = 0.5,
    eol_threshold: float = 20.0,
    hi_trigger: float = 85.0,
    ci: float = 0.95
) -> pd.DataFrame:
    """
    Full M2 pipeline consuming M1 residuals directly:
    M1 residuals -> normalize -> EWMA -> composite score -> Health Index -> RUL uncertainty -> features.

    Args:
        df_res:                 DataFrame from M1 containing 'timestamp' and all 'res_*' columns.
        mission_duration_hours: Operator-set mission duration (hours).
        ewma_span:              EWMA span for smoothing.
        rul_window:             Sliding window for RUL regression.
        health_k:               Exponential decay constant for health index.
        eol_threshold:          Health index at end-of-life.
        hi_trigger:             Health index below which RUL is estimated.
        ci:                     Confidence interval for RUL bands.

    Returns:
        DataFrame with all 22 M2 feature columns.
    """
    if mission_duration_hours <= 0:
        raise ValueError(f"mission_duration_hours must be > 0, got {mission_duration_hours}")

    if "timestamp" not in df_res.columns:
        raise ValueError("df_res must contain a 'timestamp' column.")

    missing_res = [c for c in REQUIRED_RESIDUAL_COLS if c not in df_res.columns]
    if missing_res:
        raise ValueError(f"df_res is missing required residual columns: {missing_res}")

    # Step 1: Normalize M1 residuals by allowable tolerance bounds
    norm_df = normalize_residuals(df_res)

    # Step 2: Composite degradation score
    composite = compute_composite_score(norm_df)

    # Build working DataFrame
    out = pd.DataFrame()
    out["timestamp"] = df_res["timestamp"].values

    # Pass through raw M1 residuals
    for col in REQUIRED_RESIDUAL_COLS:
        out[col] = df_res[col].values

    # Composite score + EWMA
    out["composite_score"] = composite.values
    out["composite_ewma"] = apply_ewma_series(composite, span=ewma_span).values

    # Step 3: Health index, status & ISO severity classification
    out["health_index"] = compute_health_index(out["composite_score"], k=health_k)
    out["health_status"] = compute_health_status(out["health_index"])
    out["severity_level"] = compute_severity_level(out["health_index"])

    # Step 4: RUL with uncertainty bands & mission horizon bounding
    out = add_rul_columns(
        out,
        window=rul_window,
        eol_threshold=eol_threshold,
        mission_duration_hours=mission_duration_hours,
        hi_trigger=hi_trigger,
        ci=ci,
    )

    # Step 5: Engineered features for downstream diagnostics
    # Health slope: rolling linear slope over window
    hi_series = out["health_index"]
    ts_min = out["timestamp"] / 60.0
    slopes = np.full(len(out), float("nan"))
    w = rul_window
    for i in range(w, len(out)):
        hi_w = hi_series.iloc[i - w:i].values
        ts_w = ts_min.iloc[i - w:i].values
        if len(ts_w) >= 2 and (ts_w[-1] - ts_w[0]) > 0:
            from scipy.stats import linregress
            slope, _, _, _, _ = linregress(ts_w, hi_w)
            slopes[i] = slope
    out["health_slope"] = slopes

    # EWMA of critical thermal residuals
    out["res_cht_ewma"] = apply_ewma_series(pd.Series(out["res_cht"].values), span=ewma_span).values
    out["res_egt_ewma"] = apply_ewma_series(pd.Series(out["res_egt"].values), span=ewma_span).values

    # Rolling std of vibration residual (window=10)
    out["res_vib_std_w"] = pd.Series(out["res_vib"].values).rolling(10, min_periods=1).std().values

    # Fault label pass-through
    if "fault_label" in df_res.columns:
        out["fault_label"] = df_res["fault_label"].values
    else:
        out["fault_label"] = "unknown"

    # Reorder columns to match standard schema
    out = out[REQUIRED_COLUMNS]

    return out


def validate_m2_output(df: pd.DataFrame) -> None:
    """
    Validates M2 output schema. Raises ValueError on violations.

    Checks:
    - All required columns present
    - health_index in [0, 100]
    - rul_lower <= rul_est <= rul_upper (where not NaN)
    - rul_status in valid set
    - health_status in valid set
    - Numeric RUL columns are float dtype (no strings)
    """
    # Check required columns
    missing = set(REQUIRED_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # health_index bounds
    hi = df["health_index"]
    if hi.min() < -0.01 or hi.max() > 100.01:
        raise ValueError(f"health_index out of [0,100]: min={hi.min()}, max={hi.max()}")

    # RUL numeric type check
    for col in NUMERIC_RUL_COLS:
        if not pd.api.types.is_float_dtype(df[col]):
            raise ValueError(f"Column '{col}' must be float dtype, got {df[col].dtype}")

    # RUL ordering check (where estimable)
    mask = df["rul_status"] == "estimable"
    if mask.any():
        sub = df.loc[mask]
        violations = sub["rul_lower"] > sub["rul_est"] + 0.001
        if violations.any():
            raise ValueError("rul_lower > rul_est in some rows")
        violations = sub["rul_est"] > sub["rul_upper"] + 0.001
        if violations.any():
            raise ValueError("rul_est > rul_upper in some rows")

    # rul_status valid values
    invalid_rul = set(df["rul_status"].unique()) - VALID_RUL_STATUSES
    if invalid_rul:
        raise ValueError(f"Invalid rul_status values: {invalid_rul}")

    # health_status valid values
    invalid_hs = set(df["health_status"].unique()) - VALID_HEALTH_STATUSES
    if invalid_hs:
        raise ValueError(f"Invalid health_status values: {invalid_hs}")

    # severity_level valid values
    invalid_sv = set(df["severity_level"].unique()) - VALID_SEVERITY_LEVELS
    if invalid_sv:
        raise ValueError(f"Invalid severity_level values: {invalid_sv}")


def get_metadata(mission_duration_hours: float = 8.0, **kwargs) -> dict:
    """Returns M2 metadata dict for export."""
    return {
        "module": "M2",
        "version": "1.0",
        "mission_duration_hours": mission_duration_hours,
        "max_rul_min": mission_duration_hours * 60.0,
        "eol_threshold": kwargs.get("eol_threshold", 20.0),
        "health_decay_k": kwargs.get("health_k", 0.5),
        "rul_ci": kwargs.get("ci", 0.95),
        "rul_unit": "minutes",
        "timestamp_unit": "seconds_from_mission_start",
    }


def export_csv(df: pd.DataFrame, path: str, float_precision: int = 4) -> None:
    """Exports M2 feature table to CSV."""
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    df.to_csv(path, index=False, float_format=f"%.{float_precision}f")


def export_json(df: pd.DataFrame, path: str, metadata: dict = None) -> None:
    """
    Exports M2 feature table to JSON with metadata header.
    """
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    output = {
        "metadata": metadata or {},
        "data": json.loads(df.to_json(orient="records", double_precision=4)),
    }
    with open(path, "w") as f:
        json.dump(output, f, indent=2)


def _self_test():
    """Self-test: builds feature table from synthetic M1 residuals and validates."""
    from _dev_fault_stub import generate_m1_residuals

    df_res = generate_m1_residuals(duration_min=150.0)

    # Build with default 8h mission
    df_out = build_feature_table(df_res, mission_duration_hours=8.0)

    # Schema validation
    validate_m2_output(df_out)

    # Column count
    assert len(df_out.columns) == 22, f"Expected 22 columns, got {len(df_out.columns)}"

    # Check all required columns
    assert list(df_out.columns) == REQUIRED_COLUMNS, "Column order mismatch"

    # RUL dtype checks
    for col in NUMERIC_RUL_COLS:
        assert pd.api.types.is_float_dtype(df_out[col]), f"{col} must be float"

    # rul_status is str
    assert df_out["rul_status"].dtype == object, "rul_status must be object/str"

    # fault_label preserved
    assert set(df_out["fault_label"].unique()) == {"healthy", "degraded", "misfire"}

    # Mission duration validation
    try:
        build_feature_table(df_res, mission_duration_hours=0)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass

    # Export test
    export_csv(df_out, "data/m2_test_output.csv")
    meta = get_metadata(mission_duration_hours=8.0)
    export_json(df_out, "data/m2_test_output.json", metadata=meta)
    assert os.path.exists("data/m2_test_output.csv")
    assert os.path.exists("data/m2_test_output.json")

    # Verify JSON metadata
    with open("data/m2_test_output.json") as f:
        j = json.load(f)
    assert j["metadata"]["mission_duration_hours"] == 8.0
    assert j["metadata"]["max_rul_min"] == 480.0

    # Cleanup test files
    os.remove("data/m2_test_output.csv")
    os.remove("data/m2_test_output.json")

    print(f"  Rows: {len(df_out)}, Columns: {len(df_out.columns)}")
    print(f"  RUL statuses: {df_out['rul_status'].value_counts().to_dict()}")
    print(f"  Health statuses: {df_out['health_status'].value_counts().to_dict()}")
    print("[PASS] feature_builder.py self-test passed!")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="M2 Feature Builder (SIH26054)")
    parser.add_argument("--hours", type=float, default=None, help="Mission duration in hours (e.g. 4.0, 7.5, 12)")
    parser.add_argument("--res", type=str, default="data/m1_residual_sample.csv", help="Path to M1 residual CSV")
    parser.add_argument("--out", type=str, default=None, help="Output CSV path")
    args = parser.parse_args()

    if args.hours is not None:
        from _dev_fault_stub import generate_m1_residuals
        if os.path.exists(args.res):
            df_res = pd.read_csv(args.res)
        else:
            print(f"Residual file '{args.res}' not found; generating synthetic M1 residual data...")
            df_res = generate_m1_residuals()

        out_csv = args.out or f"data/m2_output_{args.hours:.1f}h.csv"
        df_out = build_feature_table(df_res, mission_duration_hours=args.hours)
        validate_m2_output(df_out)
        export_csv(df_out, out_csv)
        meta = get_metadata(mission_duration_hours=args.hours)
        out_json = out_csv.rsplit(".", 1)[0] + ".json"
        export_json(df_out, out_json, metadata=meta)
        print(f"[SUCCESS] Built feature table for {args.hours}h mission (horizon = {args.hours*60:.0f} min)")
        print(f"  Exported CSV: {out_csv}")
        print(f"  Exported JSON: {out_json}")
        print(f"  RUL status counts: {df_out['rul_status'].value_counts().to_dict()}")
    else:
        _self_test()
