# M2 — Prognostics & Feature Engineering Module
### DRDO MALE UAV Digital Twin · SIH 2026 · Problem Code SIH26054

---

## Overview

**M2** is the Prognostics and Feature Engineering module in the DRDO MALE UAV Digital Twin pipeline. It sits between **M1 (Physics Simulator)** and **M4 (Diagnostic ML Model)**, consuming M1's residual outputs and producing a rich 22-column feature table with health metrics, severity classification, and Remaining Useful Life (RUL) estimates.

```
M1 (Physics Simulator)
        │
        │  res_rpm, res_cht, res_egt, res_oil_p,
        │  res_oil_t, res_fuel, res_vib
        ▼
  ┌─────────────────────────────┐
  │        M2 Pipeline          │
  │  1. Normalize residuals     │
  │  2. EWMA smoothing          │
  │  3. Composite anomaly score │
  │  4. Health Index (0–100%)   │
  │  5. ISO Severity levels     │
  │  6. RUL + 95% CI bands      │
  │  7. Engineered features     │
  └─────────────────────────────┘
        │
        │  22-column feature table
        ▼
M4 (Diagnostic ML Model / Dashboard)
```

---

## Interface Contract

### ✅ M2 INPUT — From M1

M2 expects a `pd.DataFrame` with the following columns. **M1 computes these; M2 never computes residuals itself.**

| Column | Unit | Description |
|---|---|---|
| `timestamp` | seconds | Time from mission start |
| `res_rpm` | RPM | Actual − Predicted RPM |
| `res_cht` | °C | Actual − Predicted Cylinder Head Temp |
| `res_egt` | °C | Actual − Predicted Exhaust Gas Temp |
| `res_oil_p` | bar | Actual − Predicted Oil Pressure |
| `res_oil_t` | °C | Actual − Predicted Oil Temperature |
| `res_fuel` | kg/h | Actual − Predicted Fuel Flow |
| `res_vib` | arb | Actual − Predicted Vibration Amplitude |
| `fault_label` | str *(optional)* | Ground truth fault label if available |

### ✅ M2 OUTPUT — To M4

M2 produces a 22-column feature table (schema validated before export):

| Column | Type | Description |
|---|---|---|
| `timestamp` | float | Seconds from mission start |
| `res_rpm` … `res_vib` | float ×7 | Raw M1 residuals (pass-through) |
| `composite_score` | float | Weighted RMS anomaly score D(t) |
| `composite_ewma` | float | EWMA-smoothed composite score |
| `health_index` | float [0–100] | Engine health % (100 = perfect) |
| `health_status` | str | `healthy` / `degraded` / `critical` |
| `severity_level` | str | `NORMAL` / `ADVISORY` / `WARNING` / `CRITICAL_RTB` |
| `rul_est` | float (min) | Point RUL estimate |
| `rul_lower` | float (min) | Pessimistic 95% CI bound |
| `rul_upper` | float (min) | Optimistic 95% CI bound |
| `rul_status` | str | `estimable` / `not_estimable` / `beyond_horizon` |
| `health_slope` | float | Rolling health index trend (per minute) |
| `res_cht_ewma` | float | EWMA of CHT residual |
| `res_egt_ewma` | float | EWMA of EGT residual |
| `res_vib_std_w` | float | Rolling std of vibration residual (window=10) |
| `fault_label` | str | Passed through from M1 |

---

## File Structure

```
RUL-SIH/
├── feature_builder.py      # 🔑 Main M2 pipeline orchestrator
├── normalization.py        # Residual normalization by tolerance bounds
├── ewma.py                 # Exponentially Weighted Moving Average filter
├── composite_score.py      # Weighted RMS composite degradation score
├── health_index.py         # Health Index (0–100%) + ISO severity levels
├── rul_baseline.py         # Slope-based deterministic RUL estimator
├── rul_uncertainty.py      # 95% CI RUL bands (t-distribution regression)
├── demo_plots.py           # 6 publication-quality visualization plots
├── run_custom_mission.py   # CLI runner — enter any mission duration
├── test_m2_pipeline.py     # Full smoke test suite
├── _dev_fault_stub.py      # M1 input adapter (real + synthetic fallback)
├── m1_real_data.py         # M1's real FaultedSimulator (from M1 team)
└── data/
    ├── m1_residual_sample.csv    # Sample M1 residual input
    └── m2_output_<Xh>.csv/json  # M2 feature table outputs
```

---

## How to Run

### Run with any custom mission duration
```bash
python run_custom_mission.py            # interactive prompt
python run_custom_mission.py 7.5        # CLI: 7.5-hour mission
```

### Run smoke test
```bash
python test_m2_pipeline.py             # interactive prompt
python test_m2_pipeline.py --hours 6   # CLI: 6-hour mission
```

### Run individual module self-tests
```bash
python normalization.py
python composite_score.py
python health_index.py
python rul_uncertainty.py
python feature_builder.py
```

---

## Algorithm Summary

### 1. Normalization
Each residual is divided by its physics-based tolerance bound:
```
norm_res_i(t) = res_i(t) / bound_i
```
Bounds: ±150 RPM, ±20°C CHT, ±40°C EGT, ±0.8 bar oil, ±15°C oil_t, ±2.0 kg/h fuel, ±0.35 vib

### 2. Composite Degradation Score
Weighted Root Mean Square across all normalized residuals:
```
D(t) = √( Σ wᵢ · norm_res_i(t)² )
```
Weights (by criticality): oil_p=0.25, CHT=0.20, EGT=0.15, vib=0.15, oil_t=0.10, RPM=0.10, fuel=0.05

### 3. Health Index
Exponential decay mapping: HI(t) = 100 · exp(−k · D(t)), k=0.5
- HI ≥ 70 → `healthy`
- 40 ≤ HI < 70 → `degraded`
- HI < 40 → `critical`

### 4. ISO Severity Levels (Aerospace Standard)
- HI > 85 → **NORMAL** — no action required
- 70 < HI ≤ 85 → **ADVISORY** — monitor closely
- 40 < HI ≤ 70 → **WARNING** — plan maintenance
- HI ≤ 40 → **CRITICAL_RTB** — Return to Base immediately

### 5. RUL Estimation (95% CI)
Linear regression of HI over sliding window (20 samples):
```
RUL_est = (HI_eol − HI_current) / slope
```
Confidence bounds via t-distribution on slope standard error. All values clamped to `[0, mission_hours × 60]`.

---

## M1 Integration

M2 is designed to accept residuals from M1's `twin_core` pipeline:

```python
# When twin_core is installed (M1's package):
from _dev_fault_stub import generate_m1_residuals
df_res = generate_m1_residuals()   # Uses M1's real FaultedSimulator

# M2 pipeline:
from feature_builder import build_feature_table
df_out = build_feature_table(df_res, mission_duration_hours=8.0)
```

If `twin_core` is not installed, the stub **automatically falls back** to synthetic residuals with the same schema so M2 can run independently.

---

## Fault Types Supported (from M1)

| Fault | Dominant Residual Channels |
|---|---|
| `misfire` | res_rpm ↓, res_vib ↑, res_egt ↓ |
| `injector_fault` | res_fuel ↓, res_egt ↑, res_rpm ↓ |
| `overheating` | res_cht ↑↑, res_egt ↑↑, res_oil_t ↑ |
| `oil_pressure_drop` | res_oil_p ↓↓, res_oil_t ↑ |
| `vibration_spike` | res_vib ↑↑ |

---

## Team

**Member 2 — M2 Prognostics & Feature Engineering**
*DRDO MALE UAV Digital Twin · SIH 2026 · Problem SIH26054*
