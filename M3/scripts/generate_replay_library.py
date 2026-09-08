"""Generate a curated replay library of labelled telemetry CSVs.

Produces 8 CSVs covering healthy baselines under different environments /
throttle profiles, single-fault scenarios at standard conditions, and one
combined "stress" scenario.  A ``manifest.csv`` is written alongside the
data files for downstream tooling to discover and iterate over them.

Usage::

    python scripts/generate_replay_library.py        # from m3_telemetry/
"""

from __future__ import annotations

import csv
import os
import sys
import time

# Ensure the project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from generator.fault_injection import (
    FaultManager,
    InjectorFault,
    MisfireFault,
    OilPressureDropFault,
    OverheatingFault,
    VibrationSpikeFault,
)
from publisher.csv_sink import CsvSink
from publisher.streaming_harness import TelemetryPublisher


# ── Configuration ───────────────────────────────────────────────────────────

DURATION_S = 30.0
RATE_HZ    = 10.0
SEED       = 42
OUT_DIR    = os.path.join(os.path.dirname(__file__), "..", "data", "replay_library")

# Each scenario: (filename, environment, throttle_mode, fault_or_None)
SCENARIOS: list[tuple[str, str, str, object | None]] = [
    # ── Healthy baselines ────────────────────────────────────────────
    (
        "healthy_standard_day_smooth.csv",
        "standard_day", "smooth", None,
    ),
    (
        "healthy_hot_day_rapid_transient.csv",
        "hot_day", "rapid_transient", None,
    ),
    (
        "healthy_high_altitude_idle_to_cruise.csv",
        "high_altitude", "idle_to_cruise", None,
    ),

    # ── Single-fault runs (standard_day + rapid_transient) ───────────
    (
        "fault_misfire_standard.csv",
        "standard_day", "rapid_transient",
        MisfireFault(severity=0.7, start_time_s=10.0, duration_s=10.0, seed=SEED),
    ),
    (
        "fault_overheating_standard.csv",
        "standard_day", "rapid_transient",
        OverheatingFault(severity=0.7, start_time_s=10.0, duration_s=10.0, seed=SEED),
    ),
    (
        "fault_oil_pressure_drop_standard.csv",
        "standard_day", "rapid_transient",
        OilPressureDropFault(
            severity=0.7, mode="gradual",
            start_time_s=10.0, duration_s=10.0, seed=SEED,
        ),
    ),
    (
        "fault_injector_standard.csv",
        "standard_day", "rapid_transient",
        InjectorFault(severity=0.7, start_time_s=10.0, duration_s=10.0, seed=SEED),
    ),
    (
        "fault_vibration_spike_standard.csv",
        "standard_day", "rapid_transient",
        VibrationSpikeFault(severity=0.7, pattern="intermittent", start_time_s=10.0, duration_s=10.0, seed=SEED),
    ),

    # ── Multi-fault runs (training/test data) ────────────────────────
    (
        "multi_overheat_oildrop_standard.csv",
        "standard_day", "rapid_transient",
        [
            OverheatingFault(start_time_s=5.0, duration_s=15.0, severity=0.8, seed=SEED),
            OilPressureDropFault(start_time_s=12.0, duration_s=6.0, mode="gradual", severity=0.8, seed=SEED)
        ]
    ),
    (
        "multi_misfire_vibspike_standard.csv",
        "standard_day", "rapid_transient",
        [
            MisfireFault(start_time_s=5.0, duration_s=10.0, severity=0.8, seed=SEED),
            VibrationSpikeFault(pattern="intermittent", start_time_s=10.0, duration_s=10.0, severity=0.8, seed=SEED)
        ]
    ),

    # ── Stress combo ─────────────────────────────────────────────────
    (
        "fault_overheating_hot_and_high_stress.csv",
        "hot_and_high", "rapid_transient",
        OverheatingFault(severity=0.7, start_time_s=15.0, duration_s=10.0, seed=SEED),
    ),
]


# ── Generation ──────────────────────────────────────────────────────────────

def generate_one(
    filename: str,
    environment: str,
    throttle_mode: str,
    fault: object | None,
) -> tuple[str, int]:
    """Run the harness for one scenario, return (path, row_count)."""
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, filename)

    if isinstance(fault, list):
        mgr = FaultManager(fault)
    elif fault is not None:
        mgr = FaultManager([fault])
    else:
        mgr = FaultManager()

    sink = CsvSink(path)
    sink.open()

    pub = TelemetryPublisher(
        rate_hz=RATE_HZ,
        publish_cb=sink,
        fault_manager=mgr,
        environment_name=environment,
        throttle_mode=throttle_mode,
    )

    # Fast-forward: disable wall-clock sleep for batch generation
    # and mock time.time() so timestamps increment by exactly RATE_HZ
    original_sleep = time.sleep
    original_time = time.time
    
    sim_time = time.time()
    
    def _mock_sleep(seconds):
        pass
        
    def _mock_time():
        nonlocal sim_time
        sim_time += (1.0 / RATE_HZ)
        return sim_time

    time.sleep = _mock_sleep
    time.time = _mock_time
    
    try:
        pub.run(duration_s=DURATION_S)
    finally:
        time.sleep = original_sleep
        time.time = original_time
        sink.close()

    # Count rows
    with open(path, newline="", encoding="utf-8") as f:
        row_count = sum(1 for _ in csv.reader(f)) - 1  # minus header

    return path, row_count


def write_manifest(rows: list[dict]) -> str:
    """Write manifest.csv and return its path."""
    manifest_path = os.path.join(OUT_DIR, "manifest.csv")
    fieldnames = ["filename", "environment", "throttle_mode", "fault", "rows", "category"]
    with open(manifest_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return manifest_path


# ── Main ────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 78)
    print("  Replay Library Generator")
    print(f"  Duration: {DURATION_S}s | Rate: {RATE_HZ} Hz | "
          f"Output: {os.path.abspath(OUT_DIR)}")
    print("=" * 78)

    manifest_rows: list[dict] = []
    wall_start = time.perf_counter()

    for filename, env, throttle, fault in SCENARIOS:
        if isinstance(fault, list):
            fault_name = ",".join(f.name for f in fault)
        else:
            fault_name = fault.name if fault is not None else "none"
        t0 = time.perf_counter()
        print(f"\n  [{fault_name:<28s}] {filename} ...", end=" ", flush=True)

        path, row_count = generate_one(filename, env, throttle, fault)
        dt = time.perf_counter() - t0
        print(f"done ({dt:.2f}s, {row_count} rows)")

        manifest_rows.append({
            "filename": filename,
            "environment": env,
            "throttle_mode": throttle,
            "fault": fault_name,
            "rows": row_count,
            "category": "training/test data",
        })

    # ── Add Demo Scenarios (already generated by run_scenario.py) ────
    demo_dir = os.path.join(OUT_DIR, "..", "demo")
    demo_scenarios = [
        ("demo_healthy.csv", "standard_day", "smooth", "none"),
        ("demo_overheating.csv", "hot_and_high", "rapid_transient", "overheating"),
        ("demo_stress.csv", "standard_day", "rapid_transient", "misfire,vibration_spike"),
    ]
    for filename, env, throttle, fault_name in demo_scenarios:
        path = os.path.join(demo_dir, filename)
        if os.path.exists(path):
            with open(path, newline="", encoding="utf-8") as f:
                row_count = sum(1 for _ in csv.reader(f)) - 1
            manifest_rows.append({
                "filename": f"../demo/{filename}",
                "environment": env,
                "throttle_mode": throttle,
                "fault": fault_name,
                "rows": row_count,
                "category": "official demo scenarios",
            })

    wall_total = time.perf_counter() - wall_start

    # ── Manifest ────────────────────────────────────────────────────
    manifest_path = write_manifest(manifest_rows)

    # ── Summary table ───────────────────────────────────────────────
    print("\n" + "=" * 78)
    print("  Manifest")
    print("=" * 78)

    hdr = (f"{'Filename':<48s}  {'Environment':<16s}  "
           f"{'Throttle':<18s}  {'Fault':<20s}  {'Category':<25s}  {'Rows':>5s}")
    print(hdr)
    print("-" * len(hdr))

    for r in manifest_rows:
        print(f"{r['filename']:<48s}  {r['environment']:<16s}  "
              f"{r['throttle_mode']:<18s}  {r['fault']:<20s}  {r['category']:<25s}  {r['rows']:5d}")

    print(f"\nTotal wall time: {wall_total:.2f}s")
    print(f"Manifest saved:  {os.path.abspath(manifest_path)}")
    print(f"Data directory:  {os.path.abspath(OUT_DIR)}")


if __name__ == "__main__":
    main()
