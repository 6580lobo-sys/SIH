"""Test script for MisfireFault — runs healthy signal values through the
fault at 100 Hz for 5 seconds and plots RPM + vibration_g to visualise dips.

Usage:
    python -m tests.test_misfire_fault          # from m3_telemetry/
"""

from __future__ import annotations

import sys
import os

# Ensure the project root is on sys.path when run as a script
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np

from generator.signal_models import healthy_sample
from generator.fault_injection import FaultManager, MisfireFault


def main() -> None:
    # ── Configuration ───────────────────────────────────────────────────
    duration_s = 5.0
    sample_rate_hz = 100.0
    throttle_pct = 70.0          # constant throttle for a clean comparison
    severity = 0.7
    seed = 42

    dt = 1.0 / sample_rate_hz
    n_samples = int(duration_s * sample_rate_hz)

    fault = MisfireFault(
        severity=severity,
        start_time_s=0.0,
        duration_s=duration_s,
        seed=seed,
    )
    mgr = FaultManager([fault])

    # ── Generate data ───────────────────────────────────────────────────
    times = np.empty(n_samples)
    rpm_healthy = np.empty(n_samples)
    rpm_faulted = np.empty(n_samples)
    vib_healthy = np.empty(n_samples)
    vib_faulted = np.empty(n_samples)

    # Fix numpy global seed so healthy_sample noise is reproducible
    np.random.seed(99)

    for i in range(n_samples):
        t = i * dt
        times[i] = t

        sample = healthy_sample(throttle_pct)
        rpm_healthy[i] = sample["rpm"]
        vib_healthy[i] = sample["vibration_g"]

        faulted = mgr.apply_all(t, sample)
        rpm_faulted[i] = faulted["rpm"]
        vib_faulted[i] = faulted["vibration_g"]

    # ── Try to plot (matplotlib); fall back to text table ───────────────
    try:
        import matplotlib
        matplotlib.use("Agg")  # non-interactive backend
        import matplotlib.pyplot as plt

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 7), sharex=True)

        # RPM subplot
        ax1.plot(times, rpm_healthy, color="#90caf9", alpha=0.5,
                 linewidth=0.6, label="healthy RPM")
        ax1.plot(times, rpm_faulted, color="#e53935", alpha=0.9,
                 linewidth=0.8, label="faulted RPM")
        ax1.set_ylabel("RPM (rev/min)")
        ax1.set_title(f"MisfireFault  severity={severity}  seed={seed}")
        ax1.legend(loc="upper right")
        ax1.grid(True, alpha=0.3)

        # Vibration subplot
        ax2.plot(times, vib_healthy, color="#90caf9", alpha=0.5,
                 linewidth=0.6, label="healthy vib")
        ax2.plot(times, vib_faulted, color="#e53935", alpha=0.9,
                 linewidth=0.8, label="faulted vib")
        ax2.set_ylabel("Vibration (g)")
        ax2.set_xlabel("Time (s)")
        ax2.legend(loc="upper right")
        ax2.grid(True, alpha=0.3)

        plt.tight_layout()
        out_path = os.path.join(os.path.dirname(__file__), "misfire_fault_plot.png")
        plt.savefig(out_path, dpi=150)
        print(f"[OK] Plot saved to {out_path}")

    except ImportError:
        # Fallback: print a text table at 10 Hz (every 10th sample)
        print(f"{'t (s)':>7s}  {'RPM_h':>8s}  {'RPM_f':>8s}  "
              f"{'VIB_h':>7s}  {'VIB_f':>7s}  {'delta_rpm':>9s}")
        print("-" * 60)
        for i in range(0, n_samples, 10):
            d_rpm = rpm_faulted[i] - rpm_healthy[i]
            print(
                f"{times[i]:7.2f}  {rpm_healthy[i]:8.1f}  {rpm_faulted[i]:8.1f}  "
                f"{vib_healthy[i]:7.3f}  {vib_faulted[i]:7.3f}  {d_rpm:+9.1f}"
            )

    # ── Summary stats ───────────────────────────────────────────────────
    dips = rpm_faulted < (rpm_healthy - 50)  # >50 rpm drop = a "dip"
    n_dip_samples = int(np.sum(dips))
    pct_dip = 100.0 * n_dip_samples / n_samples

    print(f"\n-- Summary (severity={severity}) --")
    print(f"  Total samples     : {n_samples}")
    print(f"  Misfire events    : {len(fault._events)}")
    print(f"  Samples in a dip  : {n_dip_samples} ({pct_dip:.1f} %)")
    print(f"  Max RPM drop      : {np.min(rpm_faulted - rpm_healthy):.1f} rev/min")
    print(f"  Max vib spike     : {np.max(vib_faulted - vib_healthy):.3f} g")


if __name__ == "__main__":
    main()
