# M1 Block — Architecture Diagram Content for M5

Hand this to M5 for the README block diagram. Everything below describes
what's **actually running** after the Day 6 integration pass, not what was
planned on Day 1.

---

## Data Flow (exact)

```
                         ┌─────────────────────────────────────────────────┐
                         │              CONTROL INPUTS                     │
                         │   throttle_cmd (0-100%), ambient_temp, dt       │
                         └──────────┬──────────────────┬───────────────────┘
                                    │                  │
                     (same inputs)  │                  │  (same inputs)
                                    ▼                  ▼
                  ┌─────────────────────┐   ┌──────────────────────────┐
                  │  REFERENCE MODEL    │   │  ACTUAL SOURCE           │
                  │  (EngineSimulator)  │   │  (pluggable)             │
                  │                     │   │                          │
                  │  Pure physics model │   │  One of:                 │
                  │  + sensor noise     │   │   • EngineSimulator      │
                  │                     │   │     (healthy baseline)   │
                  │  engine_maps.py     │   │   • M2 Fault Injector    │
                  │  dynamics.py        │   │     (live faulted stream)│
                  │                     │   │   • CsvReplaySource      │
                  │                     │   │     (mission-log replay) │
                  └────────┬────────────┘   └────────────┬─────────────┘
                           │                             │
                    predicted {}                   actual {}
                           │                             │
                           │  ┌──────────────────────┐   │
                           └──►  RESIDUAL ENGINE     ◄───┘
                              │  (residual.py)       │
                              │                      │
                              │  1. Subtract:        │
                              │     actual - predicted│
                              │     per channel      │
                              │                      │
                              │  2. Normalize:       │
                              │     ÷ operating range │
                              │     (cross-channel   │
                              │      comparable)     │
                              │                      │
                              │  3. EWMA smooth:     │
                              │     suppress noise   │
                              │     spikes           │
                              │                      │
                              │  4. Composite score: │
                              │     RMS of smoothed  │
                              │     residuals (0-1+) │
                              └──────────┬───────────┘
                                         │
                     ┌───────────────────┬┴──────────────────┐
                     ▼                   ▼                    ▼
           ┌──────────────────┐ ┌────────────────┐  ┌────────────────┐
           │  PER-TICK OUTPUT │ │  SIGNATURE()   │  │  COMPOSITE     │
           │  (for M4 dash)  │ │  (for M3 class)│  │  SCORE         │
           │                 │ │                │  │  (for M4 gauge)│
           │  {timestamp,    │ │ {feature_vector│  │                │
           │   residuals: {  │ │   {ch: val},   │  │  Single 0-1+  │
           │    ch: val,..}, │ │  dominant_chans│  │  severity num  │
           │   composite}    │ │  severity,     │  │                │
           │                 │ │  fault_detected│  │                │
           └──────────────────┘ └────────────────┘  └────────────────┘
```

---

## Schema at Each Boundary

**Predicted / Actual dicts** (10 fields — shared schema):
```
{timestamp, rpm, cht, egt, oil_pressure, oil_temp, fuel_flow,
 vibration_amplitude, vibration_freq, throttle_cmd}
```

**Residual tick output** (consumed by M4 every tick):
```
{timestamp, residuals: {rpm, cht, egt, oil_pressure, oil_temp,
 fuel_flow, vibration_amplitude, vibration_freq}, composite_score}
```

**Signature** (consumed by M3 on demand):
```
{feature_vector: {rpm, cht, egt, ...},    # fixed-length, all 8 channels
 dominant_channels: [(ch, val), ...],      # sorted by |magnitude|
 severity: float,                          # same as composite_score
 fault_detected: bool}                     # severity > threshold
```

---

## 3 Things That Are Easy to Get Wrong in the Diagram

### 1. The reference model gets the SAME control inputs, NOT the actual sensor data

This is the most common misunderstanding. The reference model is fed
`throttle_cmd` (the control input), not RPM or EGT (the sensor outputs).
It **independently predicts** what RPM and EGT should be. If you draw an
arrow from the actual sensor stream back into the reference model, the
diagram is wrong — that would make it a filter, not a twin.

**Correct:**  throttle_cmd → reference model → predicted RPM
**Wrong:**    actual RPM → reference model → predicted RPM

### 2. The residual is (actual − predicted), NOT a threshold on raw values

A traditional monitoring system fires an alarm when EGT > 900°C (fixed
threshold). This twin fires when EGT_actual − EGT_predicted > some
normalized threshold. The difference matters: if the physics model
predicts EGT=880°C at full throttle, then EGT_actual=885°C is fine (small
residual), but EGT_actual=885°C at idle (where predicted=650°C) is a
massive anomaly. The diagram should show TWO streams being compared, not
one stream being checked against a static limit.

### 3. The actual source is PLUGGABLE — not hardwired to one data path

The same DigitalTwin class handles three modes by swapping the actual
source:
  • Healthy baseline: second EngineSimulator (for testing)
  • Live faulted:     M2's fault injector (for demo)
  • Replay:           CsvReplaySource reading a mission-log CSV

The diagram should show the actual source as a switchable input, not as a
single box. This is what enables the "replay a past mission and re-analyze
it" use case that M4 needs for the mission-reliability score.

---

## Module Map (for the architecture block in the README)

```
src/twin_core/
├── engine_maps.py          # Pure steady-state physics (no noise, no state)
├── dynamics.py             # EngineSimulator: state + lag + noise
├── twin.py                 # DigitalTwin: two parallel paths
├── residual.py             # ResidualEngine: normalize, smooth, score, signature
├── replay.py               # CsvReplaySource + CSV I/O + replay_csv()
├── _dev_fault_stub.py      # [THROWAWAY] Dev fault injector (delete when M2 ready)
└── integration_test.py     # End-to-end schema validation
```
