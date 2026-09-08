"""Test script for InjectorFault -- runs healthy signal values through
the fault over a 10-second window with the fault active from t=2s,
prints fuel_flow_lph, rpm, and egt_c together to confirm they move
in a physically consistent way (lean-running: fuel down, rpm sags,
egt rises).

Usage:
    python -m tests.test_injector_fault      # from m3_telemetry/
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np

from generator.signal_models import healthy_sample
from generator.fault_injection import FaultManager, InjectorFault


def main() -> None:
    # -- Configuration --------------------------------------------------------
    total_s     = 10.0
    dt          = 0.01        # 100 Hz
    severity    = 0.7
    fault_start = 2.0
    seed        = 42

    n_samples = int(total_s / dt)

    fault = InjectorFault(
        severity=severity,
        start_time_s=fault_start,
        duration_s=None,          # active until end
        seed=seed,
    )
    mgr = FaultManager([fault])

    # -- Collect data ---------------------------------------------------------
    times   = np.empty(n_samples)
    fuel_h  = np.empty(n_samples)
    fuel_f  = np.empty(n_samples)
    rpm_h   = np.empty(n_samples)
    rpm_f   = np.empty(n_samples)
    egt_h   = np.empty(n_samples)
    egt_f   = np.empty(n_samples)

    untouched_keys = ["cht_c", "oil_pressure_kpa", "oil_temp_c", "vibration_g",
                      "throttle_pct", "ambient_temp_c"]
    untouched_ok = True

    for i in range(n_samples):
        t = i * dt
        times[i] = t

        np.random.seed(99 + i)
        sample = healthy_sample(throttle_pct=70.0)
        faulted = mgr.apply_all(t, sample)

        fuel_h[i] = sample["fuel_flow_lph"]
        fuel_f[i] = faulted["fuel_flow_lph"]
        rpm_h[i]  = sample["rpm"]
        rpm_f[i]  = faulted["rpm"]
        egt_h[i]  = sample["egt_c"]
        egt_f[i]  = faulted["egt_c"]

        for k in untouched_keys:
            if sample[k] != faulted[k]:
                print(f"FAILURE: {k} altered at t={t:.2f}")
                untouched_ok = False

    if untouched_ok:
        print("PASS: cht, oil_pressure, oil_temp, vibration untouched.\n")
    else:
        print("FAIL: some untouched fields were modified!\n")

    # -- Try to plot; fall back to text table ---------------------------------
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)

        for ax, (h, f, ylabel, color_f) in zip(axes, [
            (fuel_h, fuel_f, "Fuel Flow (L/h)", "#e53935"),
            (rpm_h,  rpm_f,  "RPM (rev/min)",   "#ff7043"),
            (egt_h,  egt_f,  "EGT (deg C)",     "#ab47bc"),
        ]):
            ax.plot(times, h, color="#90caf9", alpha=0.5, lw=0.6,
                    label="healthy")
            ax.plot(times, f, color=color_f, alpha=0.9, lw=0.7,
                    label="faulted")
            ax.set_ylabel(ylabel)
            ax.legend(loc="upper right")
            ax.grid(True, alpha=0.3)
            ax.axvline(fault_start, color="gray", ls="--", lw=0.8,
                       label="_fault start")

        axes[0].set_title(
            f"InjectorFault (lean-running)  severity={severity}  "
            f"start={fault_start}s"
        )
        axes[-1].set_xlabel("Time (s)")
        plt.tight_layout()
        out = os.path.join(os.path.dirname(__file__),
                           "injector_fault_plot.png")
        plt.savefig(out, dpi=150)
        print(f"[OK] Plot saved to {out}")

    except ImportError:
        # Text table at 10 Hz
        step = 10
        print(f"{'t(s)':>5s}  {'Fuel_h':>7s}  {'Fuel_f':>7s}  "
              f"{'RPM_h':>7s}  {'RPM_f':>7s}  "
              f"{'EGT_h':>7s}  {'EGT_f':>7s}")
        print("-" * 60)
        for i in range(0, n_samples, step):
            print(f"{times[i]:5.1f}  {fuel_h[i]:7.2f}  {fuel_f[i]:7.2f}  "
                  f"{rpm_h[i]:7.1f}  {rpm_f[i]:7.1f}  "
                  f"{egt_h[i]:7.1f}  {egt_f[i]:7.1f}")

    # -- Summary stats (fault-active window only) -----------------------------
    mask = times >= fault_start
    d_fuel = fuel_f[mask] - fuel_h[mask]
    d_rpm  = rpm_f[mask]  - rpm_h[mask]
    d_egt  = egt_f[mask]  - egt_h[mask]

    print(f"\n-- Summary (severity={severity}, start={fault_start}s) --")
    print(f"  Fuel flow delta : mean={d_fuel.mean():+.2f}  "
          f"min={d_fuel.min():+.2f}  max={d_fuel.max():+.2f} L/h")
    print(f"  RPM delta       : mean={d_rpm.mean():+.1f}  "
          f"min={d_rpm.min():+.1f}  max={d_rpm.max():+.1f} rev/min")
    print(f"  EGT delta       : mean={d_egt.mean():+.1f}  "
          f"min={d_egt.min():+.1f}  max={d_egt.max():+.1f} deg C")

    # -- Physical consistency checks ------------------------------------------
    checks_ok = True

    # 1) Fuel should be lower on average
    if d_fuel.mean() >= 0:
        print("  FAIL: fuel_flow should be lower on average!")
        checks_ok = False

    # 2) RPM should sag on average
    if d_rpm.mean() >= 0:
        print("  FAIL: rpm should sag on average!")
        checks_ok = False

    # 3) EGT should rise on average (lean burns hotter)
    if d_egt.mean() <= 0:
        print("  FAIL: egt should rise on average (lean mixture)!")
        checks_ok = False

    if checks_ok:
        print("  PASS: fuel DOWN, rpm DOWN, egt UP -- "
              "physically consistent lean-running signature.")


if __name__ == "__main__":
    main()
