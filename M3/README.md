# m3_telemetry

This module owns the telemetry schema definition, streaming, and fault injection for the SIH26054 DRDO digital twin project.

## Telemetry Schema

The canonical schema for the engine CAN bus telemetry frames is defined in [`schema/CAN_SCHEMA.md`](file:///schema/CAN_SCHEMA.md). It outlines the physical units, ranges, and data types for all sensors. 

The Python equivalent used for runtime validation is defined via Pydantic in [`schema/telemetry_schema.py`](file:///schema/telemetry_schema.py).

## Live Streaming / Fault Injection

You can stream synthetic engine telemetry to stdout (or a CSV) using the `streaming_harness.py` script. The harness uses a physical engine model that couples altitude and ambient temperature to the sensor outputs.

**Basic Run:**
```bash
python -m publisher.streaming_harness --duration 10 --rate 10
```

**Environment & Throttle Profiles:**
Change the environmental conditions (affects RPM, CHT, EGT, Fuel Flow) and the pilot's throttle behavior:
```bash
python -m publisher.streaming_harness --duration 30 --rate 10 \
    --environment hot_and_high --throttle-mode rapid_transient
```
*Available Environments:* `standard_day`, `hot_day`, `high_altitude`, `hot_and_high`
*Available Throttle Modes:* `smooth`, `rapid_transient`, `idle_to_cruise`

**Fault Injection:**
Inject faults dynamically at specific times. Format is `<fault_type>:<start_s>:<duration_s>:<severity>`. Faults physically modify the baseline sensor values.
```bash
python -m publisher.streaming_harness --duration 30 --rate 10 \
    --inject overheating:10:10:0.7 \
    --inject misfire:15::0.9 \
    --output-csv run_data.csv
```
*Available Faults:* `misfire`, `overheating`, `oil_drop_sudden`, `oil_drop_gradual`, `injector`, `vibration_spike`, `noop`

## Replay Library

A curated, labeled dataset of 30-second telemetry runs is available in [`data/replay_library/`](file:///data/replay_library/). A machine-readable `manifest.csv` is also provided for automated iteration. The `manifest.csv` explicitly categorizes the CSVs as either `training/test data` or `official demo scenarios`.

### Training & Test Data

| Filename | Env / Throttle | Fault | Window | Intended Use |
| :--- | :--- | :--- | :--- | :--- |
| `healthy_standard_day_smooth.csv` | Standard / Smooth | *None* | N/A | Baseline normal operation testing. |
| `healthy_hot_day_rapid_transient.csv` | Hot / Rapid Burst | *None* | N/A | High thermal baseline testing; helps avoid false-positive anomaly detections. |
| `healthy_high_altitude_idle_to_cruise.csv` | High Alt / Idle-to-Cruise | *None* | N/A | Baseline takeoff/climb sequence. |
| `fault_misfire_standard.csv` | Standard / Rapid Burst | Misfire | `[10s, 20s)` | Test anomaly detector on high-frequency RPM/vibration chatter. |
| `fault_overheating_standard.csv` | Standard / Rapid Burst | Overheating | `[10s, 20s)` | Test anomaly detector on slow thermal runaway & recovery tails. |
| `fault_oil_pressure_drop_standard.csv` | Standard / Rapid Burst | Oil Drop (Gradual)| `[10s, 20s)` | Test anomaly detector on gradual pressure loss (e.g. leak). |
| `fault_injector_standard.csv` | Standard / Rapid Burst | Injector | `[10s, 20s)` | Test anomaly detector on asymmetric Fuel Flow / EGT drops. |
| `fault_vibration_spike_standard.csv` | Standard / Rapid Burst | Vibration Spike | `[10s, 20s)` | Test anomaly detector on mechanical bearing faults independent of RPM dips. |
| `multi_overheat_oildrop_standard.csv` | Standard / Rapid Burst | Overheat + Oil Drop | `[5s, 20s)` & `[12s, 18s)` | Test robust handling of compounding physical faults. |
| `multi_misfire_vibspike_standard.csv` | Standard / Rapid Burst | Misfire + Vib Spike | `[5s, 15s)` & `[10s, 20s)` | Test separation of coupled vibration-inducing faults. |
| `fault_overheating_hot_and_high_stress.csv` | Hot+High / Rapid Burst | Overheating | `[15s, 25s)` | Complex edge-case: fault compounded by extreme environment and pilot throttle burst. |

### Official Demo Scenarios

These scenarios are located in `data/demo/` and are intended to be run live using `scripts/run_scenario.py --live-print` during stage presentations. They are included in the manifest for convenience.

| Filename | Env / Throttle | Fault | Window | Intended Use |
| :--- | :--- | :--- | :--- | :--- |
| `../demo/demo_healthy.csv` | Standard / Smooth | *None* | N/A | Stage baseline visual. |
| `../demo/demo_overheating.csv` | Hot+High / Rapid Burst | Overheating | `[10s, 25s)` | Primary live demo: obvious runaway during extreme envelope operation. |
| `../demo/demo_stress.csv` | Standard / Rapid Burst | Misfire + Vib Spike | `[5s, 15s)` & `[10s, 20s)` | Stress-test demo: sharp overlapping faults. |

> **Note:** To regenerate the library and update the manifest, run `python scripts/generate_replay_library.py`.

## Integration (M6 Orchestrator)

M6 or other subsystems should consume M3 via the clean programmatic API located in `m3_telemetry.publisher.api`. Do not instantiate `TelemetryPublisher` directly.

**Basic Usage:**
```python
from m3_telemetry.publisher.api import create_publisher, start_stream

# 1. Create the publisher
pub = create_publisher(environment="standard_day", throttle_mode="smooth")

# 2. Define a callback
def my_callback(msg, active_faults):
    print(f"Time: {msg.timestamp}s | RPM: {msg.rpm} | Fault: {active_faults}")

# 3. Start the stream (blocking call, usually run in a background thread)
start_stream(pub, my_callback, duration_s=60.0)
```

**Asynchronous Fault Injection:**
M6 can inject faults dynamically mid-stream by accessing the `fault_manager`:
```python
from m3_telemetry.generator.fault_injection import MisfireFault

# Inject misfire to start at simulation time 10.0s for 5.0s
pub.fault_manager.add(MisfireFault(start_time_s=10.0, duration_s=5.0, severity=0.8))
```

## Known Limitations

While this telemetry generator is built to provide robust data streams for downstream M1/M2/M4 systems, it is a mock data generator and carries the following limitations:
* **Simplified Physical Coupling:** The physics model relies on basic first-order linear responses and transfer functions to simulate thermal and mechanical inertia. It does not run a full Navier-Stokes thermodynamic engine cycle simulation.
* **Artificial Noise Model:** Sensor noise is modeled as uniform Gaussian jitter. Real-world sensor degradation, CAN bus packet loss, or non-linear vibrational harmonics are not fully simulated.
* **Deterministic Bounds:** The normal "healthy" operating bounds are heavily constrained to prevent straying into anomalous ranges accidentally. Real engines exhibit significantly more chaotic drift over long flights.
