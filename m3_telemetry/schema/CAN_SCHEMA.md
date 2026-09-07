# CAN Telemetry Schema — MALE UAV Aero Piston Engine

**Message ID pattern:** `ENG_TELEM_XX`
**Assumed sampling rate:** 10 Hz (one frame every 100 ms)

## Field Reference

| Field             | Unit          | Type  | Valid Range       | Description                                      |
|-------------------|---------------|-------|-------------------|--------------------------------------------------|
| `timestamp`       | s (relative)  | float | ≥ 0               | Relative time in seconds from start of simulation |
| `msg_id`          | —             | str   | non-empty         | CAN message identifier (e.g. `ENG_TELEM_01`)     |
| `rpm`             | rev/min       | float | 0 – 10 000        | Engine crankshaft speed                           |
| `cht`             | °C            | float | −40 – 500         | Cylinder Head Temperature                        |
| `egt`             | °C            | float | −40 – 1 000       | Exhaust Gas Temperature                          |
| `oil_pressure`    | PSI           | float | 0 – 150           | Engine oil pressure                              |
| `oil_temp`        | °C            | float | −40 – 250         | Engine oil temperature                           |
| `fuel_flow`       | L/h           | float | 0 – 200           | Fuel consumption rate                            |
| `vibration_amplitude` | g         | float | 0 – 50            | Vibration amplitude (accelerometer)              |
| `vibration_freq`  | Hz            | float | 0 – 1 000         | Vibration frequency                              |
| `throttle_cmd`    | %             | float | 0 – 100           | Throttle position percentage                     |

## Notes

- All temperature fields use **degrees Celsius**.
- `vibration_amplitude` is measured in **g-force** from the engine-mounted accelerometer.
- `oil_pressure` uses **PSI**.
- The valid ranges represent hard limits enforced by the Pydantic schema (`telemetry_schema.py`). Operational "normal" bands will be narrower and are defined in the fault-detection layer (M4).
