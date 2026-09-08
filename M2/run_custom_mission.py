"""
run_custom_mission.py — Interactive M2 Mission Runner (SIH26054)

Consumes M1 Residual inputs, calculates complete 22-column feature table,
clamps RUL dynamically to max_rul_min = hours * 60,
and saves the output CSV, JSON, and updated visualization plots.
"""

import sys
import os
import pandas as pd
from feature_builder import build_feature_table, validate_m2_output, export_csv, export_json, get_metadata
from demo_plots import plot_all
from _dev_fault_stub import generate_m1_residuals, save_sample_data


def main():
    print("=" * 65)
    print("      DRDO MALE UAV — M2 PROGNOSTICS MISSION RUNNER")
    print("=" * 65)

    # 1. Ask user for mission duration or accept as CLI argument
    if len(sys.argv) > 1:
        try:
            mission_hours = float(sys.argv[1])
        except ValueError:
            print(f"[ERROR] Invalid argument: {sys.argv[1]}. Must be a number.")
            sys.exit(1)
    else:
        try:
            val = input("\nEnter planned mission duration in hours (e.g. 4, 6.5, 8, 12) [default: 8.0]: ").strip()
            mission_hours = float(val) if val else 8.0
        except (ValueError, EOFError):
            mission_hours = 8.0

    if mission_hours <= 0:
        print("[ERROR] Mission duration must be greater than 0 hours.")
        sys.exit(1)

    max_rul_min = mission_hours * 60.0
    print(f"\n--> Configured Mission Duration: {mission_hours} hours")
    print(f"--> Dynamic RUL Horizon (Cap):  {max_rul_min:.0f} minutes")

    # 2. Check for M1 residual input or generate synthetic
    res_path = "data/m1_residual_sample.csv"
    if os.path.exists(res_path):
        print(f"\nLoading M1 residual data from '{res_path}'...")
        df_res = pd.read_csv(res_path)
    else:
        print("\nM1 residual sample not found; generating synthetic M1 residuals...")
        df_res = generate_m1_residuals()
        save_sample_data()

    # 3. Build features with chosen mission duration
    print(f"Executing M2 pipeline with horizon = {max_rul_min:.0f} min...")
    df_out = build_feature_table(df_res, mission_duration_hours=mission_hours)
    validate_m2_output(df_out)

    # 4. Save results
    out_csv = f"data/m2_output_{mission_hours:.1f}h.csv"
    out_json = f"data/m2_output_{mission_hours:.1f}h.json"
    export_csv(df_out, out_csv)
    meta = get_metadata(mission_duration_hours=mission_hours)
    export_json(df_out, out_json, metadata=meta)

    # 5. Generate plots
    print("Updating plots in plots/ directory...")
    plot_all(df_out, mission_duration_hours=mission_hours, save_dir="plots")

    # 6. Display summary
    print("\n" + "=" * 65)
    print("                     EXECUTION RESULTS")
    print("=" * 65)
    print(f"  * Total Data Points:       {len(df_out):,}")
    print(f"  * Max RUL Bound (Cap):     {max_rul_min:.0f} min")
    print(f"  * RUL Status Breakdown:")
    for status, count in df_out["rul_status"].value_counts().items():
        pct = (count / len(df_out)) * 100
        print(f"      - {status:15s}: {count:6d} ({pct:5.1f}%)")
    
    print(f"\n  * Output Files Created:")
    print(f"      - CSV:   {out_csv}")
    print(f"      - JSON:  {out_json}")
    print(f"      - Plots: plots/*.png")
    print("=" * 65)
    print("Done! Check the 'plots' and 'data' folders to view your results.")


if __name__ == "__main__":
    main()
