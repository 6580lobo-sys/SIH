"""
test_m2_pipeline.py — M2 End-to-End Smoke Test (SIH26054)
Validates the complete M2 pipeline with a user-specified mission duration.
Usage:
    python test_m2_pipeline.py --hours <float>
    python test_m2_pipeline.py          (will prompt for input)
"""

import os
import json
import argparse
import numpy as np
import pandas as pd

from _dev_fault_stub import generate_m1_residuals
from feature_builder import build_feature_table, validate_m2_output, export_csv, export_json, get_metadata
from demo_plots import plot_all


def run_smoke_test(mission_duration_hours: float):
    """
    Full end-to-end smoke test for M2 pipeline consuming M1 residual inputs.

    1. Ingest M1 residual data
    2. Run full M2 pipeline
    3. Validate schema
    4. Check column dtypes
    5. Assert RUL status correctness & bounds
    6. Export CSV + JSON
    7. Print summary table
    """
    print("=" * 60)
    print(f"  M2 PIPELINE SMOKE TEST (mission={mission_duration_hours}h)")
    print("=" * 60)

    # Step 1: Generate/load M1 residual data
    res_path = "data/m1_residual_sample.csv"
    print("\n[1/7] Ingesting M1 residual data...")
    if os.path.exists(res_path):
        df_res = pd.read_csv(res_path)
    else:
        df_res = generate_m1_residuals(duration_min=150.0)
    print(f"      Samples: {len(df_res)}")

    # Step 2: Run full M2 pipeline on M1 residuals
    print("[2/7] Running M2 prognostics pipeline...")
    df_out = build_feature_table(
        df_res,
        mission_duration_hours=mission_duration_hours
    )
    print(f"      Output shape: {df_out.shape}")

    # Step 3: Validate schema
    print("[3/7] Validating schema...")
    validate_m2_output(df_out)
    print("      Schema valid!")

    # Step 4: Column dtype checks
    print("[4/7] Checking column dtypes...")
    for col in ["rul_est", "rul_lower", "rul_upper"]:
        assert pd.api.types.is_float_dtype(df_out[col]), f"{col} must be float"
    assert df_out["rul_status"].dtype == object, "rul_status must be str"
    assert df_out["health_status"].dtype == object, "health_status must be str"
    print("      All dtypes correct!")

    # Step 5: RUL status & bounds checks
    print("[5/7] Checking RUL status values & bounds...")
    rul_statuses = set(df_out["rul_status"].unique())
    valid = {"estimable", "not_estimable", "beyond_horizon"}
    assert rul_statuses.issubset(valid), f"Invalid rul_status: {rul_statuses - valid}"

    max_rul_min = mission_duration_hours * 60.0
    finite_rul = df_out["rul_est"].dropna()
    if len(finite_rul) > 0:
        assert finite_rul.max() <= max_rul_min + 0.01, \
            f"rul_est exceeds mission cap: {finite_rul.max():.2f} > {max_rul_min}"

    est_mask = df_out["rul_status"] == "estimable"
    if est_mask.any():
        sub = df_out.loc[est_mask]
        assert (sub["rul_lower"] <= sub["rul_est"] + 0.01).all(), "rul_lower > rul_est"
        assert (sub["rul_est"] <= sub["rul_upper"] + 0.01).all(), "rul_est > rul_upper"

    ne_mask = df_out["rul_status"] == "not_estimable"
    if ne_mask.any():
        assert df_out.loc[ne_mask, "rul_est"].isna().all(), "rul_est should be NaN when not_estimable"
    print("      RUL status checks passed!")

    # Step 6: Export
    print("[6/7] Exporting...")
    os.makedirs("data", exist_ok=True)
    csv_path = f"data/m2_output_{mission_duration_hours}h.csv"
    json_path = f"data/m2_output_{mission_duration_hours}h.json"
    export_csv(df_out, csv_path)
    meta = get_metadata(mission_duration_hours=mission_duration_hours)
    export_json(df_out, json_path, metadata=meta)
    assert os.path.exists(csv_path), f"CSV not created: {csv_path}"
    assert os.path.exists(json_path), f"JSON not created: {json_path}"

    with open(json_path) as f:
        j = json.load(f)
    assert j["metadata"]["mission_duration_hours"] == mission_duration_hours
    assert j["metadata"]["max_rul_min"] == max_rul_min
    print(f"      Saved: {csv_path}, {json_path}")

    # Step 7: Summary table
    print("\n[7/7] SUMMARY TABLE:")
    print("-" * 50)
    for col in df_out.columns:
        if pd.api.types.is_numeric_dtype(df_out[col]):
            s = df_out[col]
            print(f"  {col:20s} | mean={s.mean():10.3f} | std={s.std():10.3f} | "
                  f"min={s.min():10.3f} | max={s.max():10.3f}")
        else:
            vals = df_out[col].value_counts().to_dict()
            print(f"  {col:20s} | {vals}")
    print("-" * 50)

    print(f"\n  RUL statuses:    {df_out['rul_status'].value_counts().to_dict()}")
    print(f"  Health statuses: {df_out['health_status'].value_counts().to_dict()}")
    print(f"  Mission horizon: {mission_duration_hours}h ({max_rul_min:.0f} min)")

    # Step 8: Generate plots
    print("\n[8/8] Generating plots...")
    plot_all(df_out, mission_duration_hours=mission_duration_hours, save_dir="plots")
    expected_plots = [
        "p1_residuals.png", "p2_composite.png", "p3_health_index.png",
        "p4_rul_uncertainty.png", "p5_fault_timeline.png", "p6_rul_status.png"
    ]
    for pf in expected_plots:
        assert os.path.exists(os.path.join("plots", pf)), f"Missing plot: {pf}"
    print(f"      Generated {len(expected_plots)} plots in plots/")

    print("\n" + "=" * 60)
    print(f"  [PASS] PIPELINE PASSED FOR {mission_duration_hours}h MISSION!")
    print("=" * 60)

    return df_out


def main():
    parser = argparse.ArgumentParser(description="M2 Pipeline Smoke Test (SIH26054)")
    parser.add_argument(
        "--hours", type=float, default=None,
        help="Mission duration in hours (e.g. 4.5, 7, 12.5)"
    )
    args = parser.parse_args()

    if args.hours is not None:
        mission_hours = args.hours
    else:
        try:
            val = input("\nEnter planned mission duration in hours (e.g. 4, 6.5, 8, 12) [default: 8.0]: ").strip()
            mission_hours = float(val) if val else 8.0
        except (ValueError, EOFError):
            mission_hours = 8.0

    if mission_hours <= 0:
        print("[ERROR] Mission duration must be greater than 0 hours.")
        return

    run_smoke_test(mission_duration_hours=mission_hours)


if __name__ == "__main__":
    main()
