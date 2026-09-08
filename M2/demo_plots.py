"""
demo_plots.py — M2 Demo Visualizations (SIH26054)
Generates 6 publication-quality plots for hackathon demo.
"""

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches


# Consistent colour palette
COLOR_HEALTHY = "#2196F3"     # Blue
COLOR_DEGRADED = "#FF9800"    # Orange
COLOR_CRITICAL = "#F44336"    # Red
COLOR_EWMA = "#4CAF50"        # Green
COLOR_RUL = "#673AB7"         # Purple
COLOR_BAND = "#CE93D8"        # Light purple
COLOR_GREY = "#9E9E9E"        # Grey
COLOR_HORIZON = "#FF5722"     # Deep orange


def _time_min(df):
    """Convert timestamp seconds to minutes."""
    return df["timestamp"] / 60.0


def plot_residuals(df: pd.DataFrame, save_dir: str = "plots", dpi: int = 150):
    """P1: Residual signals — 4 key parameters as subplots."""
    fig, axes = plt.subplots(4, 1, figsize=(14, 10), sharex=True)
    t = _time_min(df)

    params = [
        ("res_rpm", "RPM Residual", "RPM"),
        ("res_cht", "CHT Residual", "deg C"),
        ("res_egt", "EGT Residual", "deg C"),
        ("res_vib", "Vibration Residual", "arb units"),
    ]

    for ax, (col, title, unit) in zip(axes, params):
        ax.plot(t, df[col], color=COLOR_HEALTHY, alpha=0.6, linewidth=0.5)
        ax.set_ylabel(f"{title}\n({unit})", fontsize=9)
        ax.axhline(0, color="grey", linestyle="--", alpha=0.5)
        ax.grid(True, alpha=0.3)

    axes[0].set_title("M2 Residual Signals (Actual - Predicted)", fontsize=14, fontweight="bold")
    axes[-1].set_xlabel("Mission Time (minutes)", fontsize=11)

    plt.tight_layout()
    os.makedirs(save_dir, exist_ok=True)
    plt.savefig(os.path.join(save_dir, "p1_residuals.png"), dpi=dpi, bbox_inches="tight")
    plt.close()


def plot_composite(df: pd.DataFrame, save_dir: str = "plots", dpi: int = 150):
    """P2: Composite degradation score + EWMA overlay."""
    fig, ax = plt.subplots(figsize=(14, 5))
    t = _time_min(df)

    ax.plot(t, df["composite_score"], color=COLOR_GREY, alpha=0.5, linewidth=0.5, label="Raw Composite")
    ax.plot(t, df["composite_ewma"], color=COLOR_EWMA, linewidth=2.0, label="EWMA Smoothed")
    ax.set_xlabel("Mission Time (minutes)", fontsize=11)
    ax.set_ylabel("Composite Degradation Score", fontsize=11)
    ax.set_title("M2 Composite Degradation Score", fontsize=14, fontweight="bold")
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    os.makedirs(save_dir, exist_ok=True)
    plt.savefig(os.path.join(save_dir, "p2_composite.png"), dpi=dpi, bbox_inches="tight")
    plt.close()


def plot_health_index(df: pd.DataFrame, save_dir: str = "plots", dpi: int = 150):
    """P3: Health Index (0-100) with coloured threshold bands."""
    fig, ax = plt.subplots(figsize=(14, 5))
    t = _time_min(df)

    # Threshold bands
    ax.axhspan(70, 100, color=COLOR_HEALTHY, alpha=0.08, label="Healthy (>=70)")
    ax.axhspan(40, 70, color=COLOR_DEGRADED, alpha=0.08, label="Degraded (40-70)")
    ax.axhspan(0, 40, color=COLOR_CRITICAL, alpha=0.08, label="Critical (<40)")

    # Threshold lines
    ax.axhline(70, color=COLOR_DEGRADED, linestyle="--", alpha=0.5)
    ax.axhline(40, color=COLOR_CRITICAL, linestyle="--", alpha=0.5)

    # Health index line
    ax.plot(t, df["health_index"], color="#1565C0", linewidth=1.5, label="Health Index")

    ax.set_xlabel("Mission Time (minutes)", fontsize=11)
    ax.set_ylabel("Health Index (0-100)", fontsize=11)
    ax.set_title("M2 Engine Health Index", fontsize=14, fontweight="bold")
    ax.set_ylim(-5, 105)
    ax.legend(loc="lower left", fontsize=9)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    os.makedirs(save_dir, exist_ok=True)
    plt.savefig(os.path.join(save_dir, "p3_health_index.png"), dpi=dpi, bbox_inches="tight")
    plt.close()


def plot_rul_uncertainty(
    df: pd.DataFrame,
    mission_duration_hours: float = 8.0,
    save_dir: str = "plots",
    dpi: int = 150
):
    """P4: RUL estimate + uncertainty band with status coloring."""
    fig, ax = plt.subplots(figsize=(14, 5))
    t = _time_min(df)
    max_rul_min = mission_duration_hours * 60.0

    # Background shading by rul_status
    for i in range(len(df)):
        status = df["rul_status"].iloc[i]
        if status == "not_estimable":
            ax.axvspan(t.iloc[i] - 0.03, t.iloc[i] + 0.03, color=COLOR_GREY, alpha=0.02)

    # Uncertainty band (where estimable or beyond_horizon)
    estimable_mask = df["rul_status"].isin(["estimable", "beyond_horizon"])
    if estimable_mask.any():
        t_est = t[estimable_mask]
        lo = df.loc[estimable_mask, "rul_lower"]
        up = df.loc[estimable_mask, "rul_upper"]
        est = df.loc[estimable_mask, "rul_est"]

        ax.fill_between(t_est, lo, up, color=COLOR_BAND, alpha=0.3, label="95% CI Band")
        ax.plot(t_est, est, color=COLOR_RUL, linewidth=1.5, label="RUL Estimate")

    # Beyond horizon marker
    bh_mask = df["rul_status"] == "beyond_horizon"
    if bh_mask.any():
        ax.axhline(max_rul_min, color=COLOR_HORIZON, linestyle=":", linewidth=1.5,
                    label=f"Mission Horizon ({mission_duration_hours}h)")

    ax.set_xlabel("Mission Time (minutes)", fontsize=11)
    ax.set_ylabel("RUL (minutes)", fontsize=11)
    ax.set_title("M2 Remaining Useful Life with Uncertainty", fontsize=14, fontweight="bold")
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    os.makedirs(save_dir, exist_ok=True)
    plt.savefig(os.path.join(save_dir, "p4_rul_uncertainty.png"), dpi=dpi, bbox_inches="tight")
    plt.close()


def plot_fault_timeline(df: pd.DataFrame, save_dir: str = "plots", dpi: int = 150):
    """P5: Fault label timeline — coloured segments."""
    fig, ax = plt.subplots(figsize=(14, 2.5))
    t = _time_min(df)

    fault_colors = {
        "healthy": COLOR_HEALTHY,
        "degraded": COLOR_DEGRADED,
        "misfire": COLOR_CRITICAL,
    }

    # Draw coloured spans
    prev_label = df["fault_label"].iloc[0]
    span_start = t.iloc[0]
    for i in range(1, len(df)):
        curr_label = df["fault_label"].iloc[i]
        if curr_label != prev_label or i == len(df) - 1:
            color = fault_colors.get(prev_label, COLOR_GREY)
            ax.axvspan(span_start, t.iloc[i], color=color, alpha=0.5)
            span_start = t.iloc[i]
            prev_label = curr_label

    # Legend
    patches = [mpatches.Patch(color=c, label=l, alpha=0.5) for l, c in fault_colors.items()]
    ax.legend(handles=patches, loc="upper right", fontsize=9)

    ax.set_xlabel("Mission Time (minutes)", fontsize=11)
    ax.set_title("M3 Fault Label Timeline", fontsize=14, fontweight="bold")
    ax.set_yticks([])
    ax.grid(True, axis="x", alpha=0.3)

    plt.tight_layout()
    os.makedirs(save_dir, exist_ok=True)
    plt.savefig(os.path.join(save_dir, "p5_fault_timeline.png"), dpi=dpi, bbox_inches="tight")
    plt.close()


def plot_rul_status_timeline(df: pd.DataFrame, save_dir: str = "plots", dpi: int = 150):
    """P6: RUL status as coloured timeline bands."""
    fig, ax = plt.subplots(figsize=(14, 2.5))
    t = _time_min(df)

    status_colors = {
        "not_estimable": COLOR_GREY,
        "beyond_horizon": COLOR_DEGRADED,
        "estimable": COLOR_RUL,
    }

    prev_status = df["rul_status"].iloc[0]
    span_start = t.iloc[0]
    for i in range(1, len(df)):
        curr_status = df["rul_status"].iloc[i]
        if curr_status != prev_status or i == len(df) - 1:
            color = status_colors.get(prev_status, COLOR_GREY)
            ax.axvspan(span_start, t.iloc[i], color=color, alpha=0.5)
            span_start = t.iloc[i]
            prev_status = curr_status

    patches = [mpatches.Patch(color=c, label=l, alpha=0.5) for l, c in status_colors.items()]
    ax.legend(handles=patches, loc="upper right", fontsize=9)

    ax.set_xlabel("Mission Time (minutes)", fontsize=11)
    ax.set_title("M2 RUL Status Timeline", fontsize=14, fontweight="bold")
    ax.set_yticks([])
    ax.grid(True, axis="x", alpha=0.3)

    plt.tight_layout()
    os.makedirs(save_dir, exist_ok=True)
    plt.savefig(os.path.join(save_dir, "p6_rul_status.png"), dpi=dpi, bbox_inches="tight")
    plt.close()


def plot_all(
    df: pd.DataFrame,
    mission_duration_hours: float = 8.0,
    save_dir: str = "plots",
    dpi: int = 150
):
    """Generate all 6 demo plots."""
    plot_residuals(df, save_dir, dpi)
    plot_composite(df, save_dir, dpi)
    plot_health_index(df, save_dir, dpi)
    plot_rul_uncertainty(df, mission_duration_hours, save_dir, dpi)
    plot_fault_timeline(df, save_dir, dpi)
    plot_rul_status_timeline(df, save_dir, dpi)


def _self_test():
    """Self-test: generates all plots from synthetic data."""
    from _dev_fault_stub import generate_mission_data
    from feature_builder import build_feature_table

    df_pred, df_act = generate_mission_data(duration_min=150.0)
    df_out = build_feature_table(df_pred, df_act, mission_duration_hours=8.0)

    plot_all(df_out, mission_duration_hours=8.0, save_dir="plots")

    expected_files = [
        "p1_residuals.png", "p2_composite.png", "p3_health_index.png",
        "p4_rul_uncertainty.png", "p5_fault_timeline.png", "p6_rul_status.png"
    ]
    for f in expected_files:
        path = os.path.join("plots", f)
        assert os.path.exists(path), f"Missing plot: {path}"
        size = os.path.getsize(path)
        assert size > 1000, f"Plot {f} seems too small: {size} bytes"

    print(f"  Generated {len(expected_files)} plots in plots/")
    print("[PASS] demo_plots.py self-test passed!")


if __name__ == "__main__":
    _self_test()
