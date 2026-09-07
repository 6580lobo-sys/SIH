"""Test script for OilPressureDropFault -- runs both 'sudden' and 'gradual'
modes over a 10-second window with the fault active from t=2s for 5s, and
prints oil_pressure_kpa and oil_temp_c side by side to confirm the two
modes look visually distinct.

Usage:
    python -m tests.test_oil_pressure_fault      # from m3_telemetry/
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np

from generator.signal_models import healthy_sample
from generator.fault_injection import FaultManager, OilPressureDropFault


def run_mode(mode: str, severity: float, fault_start: float,
             fault_dur: float, total_s: float, dt: float,
             seed: int) -> tuple:
    """Return (times, oilp_h, oilp_f, oilt_h, oilt_f) arrays for one mode."""
    n = int(total_s / dt)
    fault = OilPressureDropFault(
        severity=severity, mode=mode,
        start_time_s=fault_start, duration_s=fault_dur, seed=seed,
    )
    mgr = FaultManager([fault])

    times    = np.empty(n)
    oilp_h   = np.empty(n)
    oilp_f   = np.empty(n)
    oilt_h   = np.empty(n)
    oilt_f   = np.empty(n)

    untouched_keys = ["rpm", "cht_c", "egt_c", "vibration_g",
                      "fuel_flow_lph", "throttle_pct", "ambient_temp_c"]
    untouched_ok = True

    for i in range(n):
        t = i * dt
        times[i] = t

        np.random.seed(99 + i)
        sample = healthy_sample(throttle_pct=70.0)
        faulted = mgr.apply_all(t, sample)

        oilp_h[i] = sample["oil_pressure_kpa"]
        oilp_f[i] = faulted["oil_pressure_kpa"]
        oilt_h[i] = sample["oil_temp_c"]
        oilt_f[i] = faulted["oil_temp_c"]

        for k in untouched_keys:
            if sample[k] != faulted[k]:
                print(f"FAILURE [{mode}]: {k} altered at t={t:.2f}")
                untouched_ok = False

    if untouched_ok:
        print(f"PASS [{mode}]: rpm, cht, egt, vibration, fuel_flow untouched.")
    return times, oilp_h, oilp_f, oilt_h, oilt_f


def main() -> None:
    # -- Configuration --------------------------------------------------------
    total_s     = 10.0
    dt          = 0.01        # 100 Hz
    severity    = 0.8
    fault_start = 2.0
    fault_dur   = 5.0
    seed        = 42

    # -- Run both modes -------------------------------------------------------
    t_s, sp_h, sp_f, st_h, st_f = run_mode(
        "sudden", severity, fault_start, fault_dur, total_s, dt, seed)
    t_g, gp_h, gp_f, gt_h, gt_f = run_mode(
        "gradual", severity, fault_start, fault_dur, total_s, dt, seed)

    # -- Try to plot; fall back to text table ---------------------------------
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 2, figsize=(16, 9), sharex=True)

        for col, (mode, t, p_h, p_f, ot_h, ot_f) in enumerate([
            ("SUDDEN", t_s, sp_h, sp_f, st_h, st_f),
            ("GRADUAL", t_g, gp_h, gp_f, gt_h, gt_f),
        ]):
            # Oil pressure
            ax = axes[0, col]
            ax.plot(t, p_h, color="#90caf9", alpha=0.5, lw=0.6, label="healthy")
            ax.plot(t, p_f, color="#e53935", alpha=0.9, lw=0.8, label="faulted")
            ax.set_ylabel("Oil Pressure (kPa)")
            ax.set_title(f"{mode} mode  (severity={severity})")
            ax.legend(loc="upper right")
            ax.grid(True, alpha=0.3)
            ax.axvspan(fault_start, fault_start + fault_dur,
                       alpha=0.08, color="red")

            # Oil temp
            ax = axes[1, col]
            ax.plot(t, ot_h, color="#90caf9", alpha=0.5, lw=0.6, label="healthy")
            ax.plot(t, ot_f, color="#ff7043", alpha=0.9, lw=0.8, label="faulted")
            ax.set_ylabel("Oil Temp (deg C)")
            ax.set_xlabel("Time (s)")
            ax.legend(loc="upper right")
            ax.grid(True, alpha=0.3)
            ax.axvspan(fault_start, fault_start + fault_dur,
                       alpha=0.08, color="red")

        plt.tight_layout()
        out = os.path.join(os.path.dirname(__file__),
                           "oil_pressure_fault_plot.png")
        plt.savefig(out, dpi=150)
        print(f"\n[OK] Plot saved to {out}")

    except ImportError:
        # Text table at 10 Hz (every 10th sample)
        step = 10
        print(f"\n{'t(s)':>5s}  |  {'---- SUDDEN ----':^30s}  |  {'---- GRADUAL ---':^30s}")
        print(f"{'':>5s}  |  {'OilP_h':>7s}  {'OilP_f':>7s}  {'OilT_h':>7s}  {'OilT_f':>7s}"
              f"  |  {'OilP_h':>7s}  {'OilP_f':>7s}  {'OilT_h':>7s}  {'OilT_f':>7s}")
        print("-" * 82)

        n = int(total_s / dt)
        for i in range(0, n, step):
            print(f"{t_s[i]:5.1f}  |  "
                  f"{sp_h[i]:7.1f}  {sp_f[i]:7.1f}  {st_h[i]:7.1f}  {st_f[i]:7.1f}  |  "
                  f"{gp_h[i]:7.1f}  {gp_f[i]:7.1f}  {gt_h[i]:7.1f}  {gt_f[i]:7.1f}")

    # -- Summary stats --------------------------------------------------------
    mask = (t_s >= fault_start) & (t_s < fault_start + fault_dur)

    for mode, p_h, p_f, ot_h, ot_f in [
        ("SUDDEN",  sp_h, sp_f, st_h, st_f),
        ("GRADUAL", gp_h, gp_f, gt_h, gt_f),
    ]:
        dp = p_f[mask] - p_h[mask]
        dt_oil = ot_f[mask] - ot_h[mask]
        print(f"\n-- {mode} (severity={severity}, "
              f"window=[{fault_start}s, {fault_start + fault_dur}s]) --")
        print(f"  Pressure drop  : min={dp.min():+.1f}  max={dp.max():+.1f} kPa")
        print(f"  Oil temp rise  : min={dt_oil.min():+.1f}  "
              f"max={dt_oil.max():+.1f} deg C")

        # Check that sudden reaches its floor much faster than gradual
        # by looking at what fraction of the drop happens in the first 0.5 s
        early_mask = (t_s >= fault_start) & (t_s < fault_start + 0.5)
        early_drop_pct = 0.0
        if np.any(early_mask) and dp.min() < -1:
            early_dp = p_f[early_mask] - p_h[early_mask]
            early_drop_pct = 100.0 * early_dp.min() / dp.min()
        print(f"  Drop in first 0.5s: {early_drop_pct:.0f}% of total")


if __name__ == "__main__":
    main()
