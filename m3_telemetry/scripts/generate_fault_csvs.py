"""Generate one CSV per fault type using the streaming harness.

Runs the ``TelemetryPublisher`` for 30 seconds at 10 Hz with each fault
active from t=10 s to t=20 s at severity=0.7.  Outputs are saved under
``data/`` and a summary table is printed at the end.

Usage::

    python scripts/generate_fault_csvs.py        # from m3_telemetry/
"""

from __future__ import annotations

import csv
import os
import sys
import time

# Ensure the project root is on sys.path so imports work when run as a script
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from generator.fault_injection import (
    FaultManager,
    InjectorFault,
    MisfireFault,
    OilPressureDropFault,
    OverheatingFault,
)
from publisher.csv_sink import CsvSink
from publisher.streaming_harness import TelemetryPublisher


# ── Configuration ───────────────────────────────────────────────────────────

DURATION_S  = 30.0
RATE_HZ     = 10.0
FAULT_START = 10.0
FAULT_DUR   = 10.0
SEVERITY    = 0.7
SEED        = 42
DATA_DIR    = os.path.join(os.path.dirname(__file__), "..", "data")

# Each entry: (filename, FaultScenario instance, primary sensor to report)
SCENARIOS = [
    (
        "fault_misfire_01.csv",
        MisfireFault(
            severity=SEVERITY,
            start_time_s=FAULT_START,
            duration_s=FAULT_DUR,
            seed=SEED,
        ),
        "rpm",
    ),
    (
        "fault_overheating_01.csv",
        OverheatingFault(
            severity=SEVERITY,
            start_time_s=FAULT_START,
            duration_s=FAULT_DUR,
            seed=SEED,
        ),
        "cht",
    ),
    (
        "fault_oil_pressure_drop_01.csv",
        OilPressureDropFault(
            severity=SEVERITY,
            mode="gradual",
            start_time_s=FAULT_START,
            duration_s=FAULT_DUR,
            seed=SEED,
        ),
        "oil_pressure",
    ),
    (
        "fault_injector_01.csv",
        InjectorFault(
            severity=SEVERITY,
            start_time_s=FAULT_START,
            duration_s=FAULT_DUR,
            seed=SEED,
        ),
        "fuel_flow",
    ),
]


# ── Generate ────────────────────────────────────────────────────────────────

def generate_one(filename: str, fault, csv_dir: str) -> str:
    """Run the harness with one fault and return the full output path."""
    os.makedirs(csv_dir, exist_ok=True)
    path = os.path.join(csv_dir, filename)

    mgr = FaultManager([fault])
    sink = CsvSink(path)
    sink.open()

    pub = TelemetryPublisher(
        rate_hz=RATE_HZ,
        publish_cb=sink,
        fault_manager=mgr,
    )

    # Disable wall-clock sleep for fast batch generation by monkeypatching time.sleep
    original_sleep = time.sleep
    time.sleep = lambda _: None

    try:
        pub.run(duration_s=DURATION_S)
    finally:
        time.sleep = original_sleep
        sink.close()

    return path


def summarise(path: str, primary_sensor: str, fault_start: float,
              fault_end: float, rate_hz: float) -> dict:
    """Read the CSV and return stats for the summary table."""
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    row_count = len(rows)

    # Rows in the fault window: [fault_start, fault_end) at the given rate
    start_row = int(fault_start * rate_hz)
    end_row   = int(fault_end * rate_hz)
    fault_rows = rows[start_row:end_row]

    vals = [float(r[primary_sensor]) for r in fault_rows]
    healthy_rows = rows[:start_row]
    healthy_vals = [float(r[primary_sensor]) for r in healthy_rows]

    return {
        "file": os.path.basename(path),
        "rows": row_count,
        "sensor": primary_sensor,
        "healthy_mean": sum(healthy_vals) / len(healthy_vals) if healthy_vals else 0,
        "fault_min": min(vals) if vals else 0,
        "fault_max": max(vals) if vals else 0,
        "fault_mean": sum(vals) / len(vals) if vals else 0,
    }


def main() -> None:
    print("=" * 72)
    print("  Generating fault CSVs")
    print(f"  Duration: {DURATION_S}s | Rate: {RATE_HZ} Hz | "
          f"Fault window: [{FAULT_START}s, {FAULT_START + FAULT_DUR}s)")
    print(f"  Severity: {SEVERITY} | Output dir: {os.path.abspath(DATA_DIR)}")
    print("=" * 72)

    results = []
    wall_start = time.perf_counter()

    for filename, fault, sensor in SCENARIOS:
        t0 = time.perf_counter()
        print(f"\n  [{fault.name}] generating {filename} ...", end=" ", flush=True)
        path = generate_one(filename, fault, DATA_DIR)
        dt = time.perf_counter() - t0
        print(f"done ({dt:.2f}s)")

        stats = summarise(path, sensor, FAULT_START,
                          FAULT_START + FAULT_DUR, RATE_HZ)
        results.append(stats)

    wall_total = time.perf_counter() - wall_start

    # ── Summary table ───────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("  Summary")
    print("=" * 72)

    hdr = (f"{'Filename':<35s}  {'Rows':>5s}  {'Sensor':<20s}  "
           f"{'Healthy':>8s}  {'Min':>8s}  {'Max':>8s}  {'Mean':>8s}")
    print(hdr)
    print("-" * len(hdr))

    for r in results:
        print(f"{r['file']:<35s}  {r['rows']:5d}  {r['sensor']:<20s}  "
              f"{r['healthy_mean']:8.1f}  {r['fault_min']:8.1f}  "
              f"{r['fault_max']:8.1f}  {r['fault_mean']:8.1f}")

    print(f"\nTotal wall time: {wall_total:.2f}s")
    print(f"Files written to: {os.path.abspath(DATA_DIR)}")


if __name__ == "__main__":
    main()
