"""Test script for OverheatingFault -- runs healthy signal values through the
fault over a 10-second window with the fault active from t=2s for 6s duration.

Prints CHT, EGT, and oil_temp_c alongside their healthy baselines, plus
verifies that RPM, vibration_g, fuel_flow_lph, and oil_pressure_kpa are
completely untouched.

Usage:
    python -m tests.test_overheating_fault      # from m3_telemetry/
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np

from generator.signal_models import healthy_sample
from generator.fault_injection import FaultManager, OverheatingFault


def main() -> None:
    # -- Configuration --------------------------------------------------------
    total_s = 10.0
    sample_rate_hz = 100.0
    throttle_pct = 70.0
    severity = 0.8
    fault_start = 2.0
    fault_dur = 6.0
    seed = 42

    dt = 1.0 / sample_rate_hz
    n_samples = int(total_s * sample_rate_hz)

    fault = OverheatingFault(
        severity=severity,
        start_time_s=fault_start,
        duration_s=fault_dur,
        seed=seed,
    )
    mgr = FaultManager([fault])

    # -- Collect data ---------------------------------------------------------
    times      = np.empty(n_samples)
    cht_h      = np.empty(n_samples)
    cht_f      = np.empty(n_samples)
    egt_h      = np.empty(n_samples)
    egt_f      = np.empty(n_samples)
    oil_t_h    = np.empty(n_samples)
    oil_t_f    = np.empty(n_samples)

    # Fields that must NOT change
    untouched_keys = ["rpm", "vibration_g", "fuel_flow_lph", "oil_pressure_kpa",
                      "throttle_pct", "ambient_temp_c"]
    untouched_ok = True

    np.random.seed(99)

    for i in range(n_samples):
        t = i * dt
        times[i] = t

        np.random.seed(99 + i)  # per-sample seed for repeatable healthy vals
        sample = healthy_sample(throttle_pct)

        faulted = mgr.apply_all(t, sample)

        cht_h[i]   = sample["cht_c"]
        cht_f[i]   = faulted["cht_c"]
        egt_h[i]   = sample["egt_c"]
        egt_f[i]   = faulted["egt_c"]
        oil_t_h[i] = sample["oil_temp_c"]
        oil_t_f[i] = faulted["oil_temp_c"]

        for k in untouched_keys:
            if sample[k] != faulted[k]:
                print(f"FAILURE: {k} altered at t={t:.2f}  "
                      f"{sample[k]} -> {faulted[k]}")
                untouched_ok = False

    # -- Untouched-field verdict ----------------------------------------------
    if untouched_ok:
        print("PASS: rpm, vibration_g, fuel_flow_lph, oil_pressure_kpa "
              "are completely untouched.\n")
    else:
        print("FAIL: some untouched fields were modified!\n")

    # -- Try to plot; fall back to text table ---------------------------------
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(3, 1, figsize=(14, 9), sharex=True)

        for ax, (h, f, label) in zip(axes, [
            (cht_h, cht_f, "CHT (deg C)"),
            (egt_h, egt_f, "EGT (deg C)"),
            (oil_t_h, oil_t_f, "Oil Temp (deg C)"),
        ]):
            ax.plot(times, h, color="#90caf9", alpha=0.5, lw=0.6,
                    label="healthy")
            ax.plot(times, f, color="#e53935", alpha=0.9, lw=0.8,
                    label="faulted")
            ax.set_ylabel(label)
            ax.legend(loc="upper left")
            ax.grid(True, alpha=0.3)
            # Mark fault window
            ax.axvspan(fault_start, fault_start + fault_dur,
                       alpha=0.08, color="red", label="_fault window")

        axes[0].set_title(
            f"OverheatingFault  severity={severity}  "
            f"window=[{fault_start}s, {fault_start + fault_dur}s]"
        )
        axes[-1].set_xlabel("Time (s)")
        plt.tight_layout()
        out_path = os.path.join(os.path.dirname(__file__),
                                "overheating_fault_plot.png")
        plt.savefig(out_path, dpi=150)
        print(f"[OK] Plot saved to {out_path}")

    except ImportError:
        # Text table at 10 Hz
        print(f"{'t(s)':>6s}  {'CHT_h':>7s}  {'CHT_f':>7s}  "
              f"{'EGT_h':>7s}  {'EGT_f':>7s}  "
              f"{'OIL_h':>7s}  {'OIL_f':>7s}  {'dCHT':>7s}")
        print("-" * 72)
        for i in range(0, n_samples, 10):
            d = cht_f[i] - cht_h[i]
            print(f"{times[i]:6.2f}  {cht_h[i]:7.1f}  {cht_f[i]:7.1f}  "
                  f"{egt_h[i]:7.1f}  {egt_f[i]:7.1f}  "
                  f"{oil_t_h[i]:7.1f}  {oil_t_f[i]:7.1f}  {d:+7.1f}")

    # -- Summary stats --------------------------------------------------------
    # Only look at the fault-active window
    mask = (times >= fault_start) & (times < fault_start + fault_dur)
    d_cht = cht_f[mask] - cht_h[mask]
    d_egt = egt_f[mask] - egt_h[mask]
    d_oil = oil_t_f[mask] - oil_t_h[mask]

    print(f"\n-- Summary (severity={severity}, "
          f"window=[{fault_start}s, {fault_start + fault_dur}s]) --")
    print(f"  CHT overshoot  : min={d_cht.min():+.1f}  "
          f"max={d_cht.max():+.1f} deg C")
    print(f"  EGT overshoot  : min={d_egt.min():+.1f}  "
          f"max={d_egt.max():+.1f} deg C")
    print(f"  Oil overshoot  : min={d_oil.min():+.1f}  "
          f"max={d_oil.max():+.1f} deg C")

    # Monotonicity check (ignoring noise): the *smoothed* delta should
    # be monotonically increasing during the fault window.
    # Use a 20-sample moving average to smooth out per-sample noise.
    kernel = np.ones(20) / 20
    smooth = np.convolve(d_cht, kernel, mode="valid")
    diffs = np.diff(smooth)
    mono_pct = 100.0 * np.sum(diffs >= -0.01) / len(diffs)
    print(f"  CHT ramp mono. : {mono_pct:.1f} % of smoothed steps are non-decreasing")

    if mono_pct > 95:
        print("  PASS: ramp is monotonically increasing (within noise).")
    else:
        print("  WARNING: ramp may not be monotonic -- inspect plot.")


if __name__ == "__main__":
    main()
