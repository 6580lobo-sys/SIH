"""
orchestrator.py -- M6 Simulation Orchestrator
==============================================

Wires M1 (DigitalTwin + ResidualEngine) -> M2 (Prognostics / Feature Engineering)
-> M3 (TelemetryPublisher / load_replay_csv) and exposes a clean
subscription/API surface for M4 (ML) and M5 (dashboard).

Architecture
------------
  M3 TelemetryPublisher  --->  tick_loop  --->  M1TwinAdapter
  (or CSV replay)                |               (DigitalTwin + ResidualEngine)
                                 v
                       M2PrognosticsAdapter
                       normalize -> composite -> HI -> severity -> RUL -> features
                                 |
                       TelemetryFrame  (M3 + M1 + M2 combined, 22 M2 columns)
                                 |
                       subscriber callbacks  --->  M4 / M5

M2 output columns carried in every TelemetryFrame (22 columns):
  timestamp, res_rpm, res_cht, res_egt, res_oil_p, res_oil_t, res_fuel, res_vib,
  composite_score, composite_ewma, health_index, health_status, severity_level,
  rul_est, rul_lower, rul_upper, rul_status, health_slope,
  res_cht_ewma, res_egt_ewma, res_vib_std_w, fault_label

CONTRACT FLAGS -- search "WARNING CONTRACT" for renegotiation points.
"""

from __future__ import annotations

import collections
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Deque, Dict, List, Optional

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Path setup -- make M1, M2, and M3 importable regardless of cwd
# ---------------------------------------------------------------------------

_HERE      = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)          # .../SIH
_M1_SRC    = os.path.join(_REPO_ROOT, "M1", "src")
_M2_SRC    = os.path.join(_REPO_ROOT, "M2")
_M3_SRC    = os.path.join(_REPO_ROOT, "m3_telemetry")

for _p in (_M1_SRC, _M2_SRC, _M3_SRC):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# M1 imports
from twin_core.twin     import DigitalTwin    # noqa: E402
from twin_core.residual import ResidualEngine  # noqa: E402

# M2 imports  (SIH/M2/*.py)
from normalization   import normalize_residuals                 # noqa: E402
from ewma            import apply_ewma_series                   # noqa: E402
from composite_score import compute_composite_score             # noqa: E402
from health_index    import (                                   # noqa: E402
    compute_health_index,
    compute_health_status,
    compute_severity_level,
)
from rul_uncertainty import estimate_rul_with_uncertainty        # noqa: E402

# M3 imports
from schema.telemetry_schema     import EngineTelemetryMessage  # noqa: E402
from publisher.api               import load_replay_csv          # noqa: E402
from publisher.streaming_harness import TelemetryPublisher       # noqa: E402
from generator.fault_injection   import (                        # noqa: E402
    FaultManager,
    FaultScenario,
    MisfireFault,
    OverheatingFault,
    OilPressureDropFault,
    InjectorFault,
    VibrationSpikeFault,
    NoOpFault,
)

__all__ = [
    "Orchestrator", "TelemetryFrame", "M1TwinAdapter", "M2PrognosticsAdapter",
    "MisfireFault", "OverheatingFault", "OilPressureDropFault",
    "InjectorFault", "VibrationSpikeFault", "NoOpFault",
]


# ---------------------------------------------------------------------------
# M1 -> M2 channel name mapping
# Canonical source: M2/_dev_fault_stub.py :: M1_TO_M2_CHANNEL_MAP
#
# M1 ResidualEngine.update() residual keys:
#   "rpm", "cht", "egt", "oil_pressure", "oil_temp", "fuel_flow",
#   "vibration_amplitude"
#
# M2 normalize_residuals() / build_feature_table() expects:
#   "res_rpm", "res_cht", "res_egt", "res_oil_p", "res_oil_t",
#   "res_fuel", "res_vib"
# ---------------------------------------------------------------------------

M1_TO_M2_CHANNEL_MAP: Dict[str, str] = {
    "rpm":                 "res_rpm",
    "cht":                 "res_cht",
    "egt":                 "res_egt",
    "oil_pressure":        "res_oil_p",
    "oil_temp":            "res_oil_t",
    "fuel_flow":           "res_fuel",
    "vibration_amplitude": "res_vib",
}

M2_RESIDUAL_COLS: List[str] = list(M1_TO_M2_CHANNEL_MAP.values())


# ---------------------------------------------------------------------------
# TelemetryFrame -- carries all 22 M2 output columns + M3 sensor fields
# ---------------------------------------------------------------------------

@dataclass
class TelemetryFrame:
    """One processed tick: raw M3 telemetry + M1 residuals + M2 prognostics.

    M3 fields
    ---------
    timestamp           float   seconds from simulation start
    msg_id              str     CAN message identifier
    rpm                 float   rev/min
    cht                 float   degC  (Cylinder Head Temp)
    egt                 float   degC  (Exhaust Gas Temp)
    oil_pressure        float   PSI
    oil_temp            float   degC
    fuel_flow           float   L/hr
    vibration_amplitude float   g
    vibration_freq      float   Hz
    throttle_cmd        float   0-100 %

    M1 residuals (renamed to M2 schema, per M2/_dev_fault_stub.py)
    ---------------------------------------------------------------
    res_rpm     float   RPM  residual  (actual - predicted)
    res_cht     float   degC residual
    res_egt     float   degC residual
    res_oil_p   float   bar  residual  (WARNING: M3 sends PSI; M1 in PSI)
    res_oil_t   float   degC residual
    res_fuel    float   L/hr residual
    res_vib     float   g    residual

    M2 prognostics (all 22 M2 feature columns per feature_builder.py)
    ------------------------------------------------------------------
    composite_score  float  Weighted RMS anomaly score D(t) >= 0
    composite_ewma   float  EWMA-smoothed composite score
    health_index     float  Engine health % [0-100]  (100 = perfect)
    health_status    str    "healthy" / "degraded" / "critical"
    severity_level   str    "NORMAL" / "ADVISORY" / "WARNING" / "CRITICAL_RTB"
    rul_est          float  Point RUL estimate (minutes)
    rul_lower        float  Pessimistic 95 pct CI bound (minutes)
    rul_upper        float  Optimistic  95 pct CI bound (minutes)
    rul_status       str    "estimable" / "not_estimable" / "beyond_horizon"
    health_slope     float  Rolling HI trend (pct/min)
    res_cht_ewma     float  EWMA of CHT residual
    res_egt_ewma     float  EWMA of EGT residual
    res_vib_std_w    float  Rolling std of vibration residual (window=10)

    Ground truth
    ------------
    fault_label      str    tag from M3 ("healthy" / fault names)
    """

    # M3 telemetry
    timestamp:           float
    msg_id:              str
    rpm:                 float
    cht:                 float
    egt:                 float
    oil_pressure:        float
    oil_temp:            float
    fuel_flow:           float
    vibration_amplitude: float
    vibration_freq:      float
    throttle_cmd:        float

    # M1 residuals (M2-named)
    res_rpm:   float = 0.0
    res_cht:   float = 0.0
    res_egt:   float = 0.0
    res_oil_p: float = 0.0
    res_oil_t: float = 0.0
    res_fuel:  float = 0.0
    res_vib:   float = 0.0

    # M2 prognostics
    composite_score: float = 0.0
    composite_ewma:  float = 0.0
    health_index:    float = 100.0
    health_status:   str   = "healthy"
    severity_level:  str   = "NORMAL"
    rul_est:         float = float("nan")
    rul_lower:       float = float("nan")
    rul_upper:       float = float("nan")
    rul_status:      str   = "not_estimable"
    health_slope:    float = float("nan")
    res_cht_ewma:    float = 0.0
    res_egt_ewma:    float = 0.0
    res_vib_std_w:   float = 0.0

    # Ground truth
    fault_label: str = "healthy"

    # Legacy residuals dict -- kept for backward compat with any M4/M5 code
    # that reads frame.residuals[channel]
    residuals: Dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_m3_m1_m2(
        cls,
        msg:          "EngineTelemetryMessage",
        m1_residuals: Dict[str, float],
        m2_row:       dict,
        fault_label:  str = "healthy",
    ) -> "TelemetryFrame":
        """Assemble a frame from M3 msg, M1 residuals (M2 naming), M2 row."""
        return cls(
            timestamp           = msg.timestamp,
            msg_id              = msg.msg_id,
            rpm                 = msg.rpm,
            cht                 = msg.cht,
            egt                 = msg.egt,
            oil_pressure        = msg.oil_pressure,
            oil_temp            = msg.oil_temp,
            fuel_flow           = msg.fuel_flow,
            vibration_amplitude = msg.vibration_amplitude,
            vibration_freq      = msg.vibration_freq,
            throttle_cmd        = msg.throttle_cmd,
            res_rpm   = m1_residuals.get("res_rpm",   0.0),
            res_cht   = m1_residuals.get("res_cht",   0.0),
            res_egt   = m1_residuals.get("res_egt",   0.0),
            res_oil_p = m1_residuals.get("res_oil_p", 0.0),
            res_oil_t = m1_residuals.get("res_oil_t", 0.0),
            res_fuel  = m1_residuals.get("res_fuel",  0.0),
            res_vib   = m1_residuals.get("res_vib",   0.0),
            composite_score = float(m2_row.get("composite_score",  0.0)),
            composite_ewma  = float(m2_row.get("composite_ewma",   0.0)),
            health_index    = float(m2_row.get("health_index",     100.0)),
            health_status   = str(m2_row.get("health_status",      "healthy")),
            severity_level  = str(m2_row.get("severity_level",     "NORMAL")),
            rul_est         = float(m2_row.get("rul_est",          float("nan"))),
            rul_lower       = float(m2_row.get("rul_lower",        float("nan"))),
            rul_upper       = float(m2_row.get("rul_upper",        float("nan"))),
            rul_status      = str(m2_row.get("rul_status",         "not_estimable")),
            health_slope    = float(m2_row.get("health_slope",     float("nan"))),
            res_cht_ewma    = float(m2_row.get("res_cht_ewma",     0.0)),
            res_egt_ewma    = float(m2_row.get("res_egt_ewma",     0.0)),
            res_vib_std_w   = float(m2_row.get("res_vib_std_w",   0.0)),
            fault_label     = fault_label,
            residuals       = m1_residuals,
        )

    def as_dict(self) -> dict:
        """Flat dict for M4 feature extraction / M5 plotting.

        Includes all 22 M2 output columns plus M3 sensor fields.
        """
        return {
            "timestamp":           self.timestamp,
            "msg_id":              self.msg_id,
            "rpm":                 self.rpm,
            "cht":                 self.cht,
            "egt":                 self.egt,
            "oil_pressure":        self.oil_pressure,
            "oil_temp":            self.oil_temp,
            "fuel_flow":           self.fuel_flow,
            "vibration_amplitude": self.vibration_amplitude,
            "vibration_freq":      self.vibration_freq,
            "throttle_cmd":        self.throttle_cmd,
            "res_rpm":             self.res_rpm,
            "res_cht":             self.res_cht,
            "res_egt":             self.res_egt,
            "res_oil_p":           self.res_oil_p,
            "res_oil_t":           self.res_oil_t,
            "res_fuel":            self.res_fuel,
            "res_vib":             self.res_vib,
            "composite_score":     self.composite_score,
            "composite_ewma":      self.composite_ewma,
            "health_index":        self.health_index,
            "health_status":       self.health_status,
            "severity_level":      self.severity_level,
            "rul_est":             self.rul_est,
            "rul_lower":           self.rul_lower,
            "rul_upper":           self.rul_upper,
            "rul_status":          self.rul_status,
            "health_slope":        self.health_slope,
            "res_cht_ewma":        self.res_cht_ewma,
            "res_egt_ewma":        self.res_egt_ewma,
            "res_vib_std_w":       self.res_vib_std_w,
            "fault_label":         self.fault_label,
        }


# ---------------------------------------------------------------------------
# M1TwinAdapter
# ---------------------------------------------------------------------------

_IDLE_ACTUAL: dict = {
    "timestamp": 0.0, "rpm": 1400.0, "cht": 90.0, "egt": 600.0,
    "oil_pressure": 20.0, "oil_temp": 50.0, "fuel_flow": 2.0,
    "vibration_amplitude": 0.02, "vibration_freq": 25.0,
    "throttle_cmd": 0.0,
}


class M1TwinAdapter:
    """Thin adapter around DigitalTwin + ResidualEngine.

    M1 interface (twin.py / residual.py)
    -------------------------------------
    DigitalTwin(actual_source, ambient_temp, ref_seed)
    DigitalTwin.step(throttle_cmd, dt)
        -> {"predicted": dict, "actual": dict}
        Keys: timestamp, rpm, cht, egt, oil_pressure, oil_temp,
              fuel_flow, vibration_amplitude, vibration_freq, throttle_cmd

    ResidualEngine.update(pair)
        -> {"timestamp": f, "residuals": {ch: f}, "composite_score": f}
        residuals keys: rpm, cht, egt, oil_pressure, oil_temp,
                        fuel_flow, vibration_amplitude

    ResidualEngine.signature(threshold=0.03)
        -> {"feature_vector", "dominant_channels", "severity", "fault_detected"}

    ResidualEngine.reset() -> resets EWMA to zero

    WARNING CONTRACT (M1 -- DigitalTwin):
      step() calls actual_source() internally.  We inject M3 frames via
      a shared variable updated before each twin.step() call.
      Renegotiate: add actual_override kwarg to DigitalTwin.step().

    WARNING CONTRACT (M1 -- DigitalTwin):
      No reset() on DigitalTwin; internal state persists across runs.
      Renegotiate: add DigitalTwin.reset() to restore t=0 idle state.
    """

    def __init__(
        self,
        ambient_temp: float = 25.0,
        ref_seed:     int   = 42,
        ewma_alpha:   float = 0.10,
    ) -> None:
        self._latest_m3_actual: Optional[dict] = None
        self._twin = DigitalTwin(
            actual_source=self._m3_bridge,
            ambient_temp=ambient_temp,
            ref_seed=ref_seed,
        )
        self._residual_eng = ResidualEngine(ewma_alpha=ewma_alpha)

    def _m3_bridge(self, throttle_cmd: float, dt: float) -> dict:
        """Bridge: return latest M3 frame as M1-shaped dict (args ignored).

        WARNING CONTRACT (M1/M3): Same pattern as M1 CsvReplaySource.step().
        """
        return self._latest_m3_actual if self._latest_m3_actual else _IDLE_ACTUAL

    @staticmethod
    def _msg_to_m1_dict(msg: "EngineTelemetryMessage") -> dict:
        """Map M3 Pydantic model -> M1 dict (field names match 1-to-1).

        WARNING CONTRACT (M1/M3 -- vibration_amplitude SCALE MISMATCH):
          M1 NOMINAL_RANGE["vibration_amplitude"] = 0.05 g span.
          M3 vibration_amplitude range = 0-50 g.
          Residuals ~20-80x oversized, dominate composite_score.
          Renegotiate: align scale on M1 or M3 side.
        """
        return {
            "timestamp":           msg.timestamp,
            "rpm":                 msg.rpm,
            "cht":                 msg.cht,
            "egt":                 msg.egt,
            "oil_pressure":        msg.oil_pressure,
            "oil_temp":            msg.oil_temp,
            "fuel_flow":           msg.fuel_flow,
            "vibration_amplitude": msg.vibration_amplitude,
            "vibration_freq":      msg.vibration_freq,
            "throttle_cmd":        msg.throttle_cmd,
        }

    def step(self, msg: "EngineTelemetryMessage", dt: float) -> Dict[str, float]:
        """Advance M1 one tick; return residuals keyed with M2 column names.

        Returns dict: {res_rpm, res_cht, res_egt, res_oil_p,
                       res_oil_t, res_fuel, res_vib}
        """
        self._latest_m3_actual = self._msg_to_m1_dict(msg)
        pair    = self._twin.step(msg.throttle_cmd, dt)
        raw_out = self._residual_eng.update(pair)

        # Remap M1 residual keys -> M2 naming convention
        return {
            m2_col: raw_out["residuals"].get(m1_key, 0.0)
            for m1_key, m2_col in M1_TO_M2_CHANNEL_MAP.items()
        }

    def signature(self, threshold: float = 0.03) -> dict:
        """Residual signature -- primary input for M4 fault classifier."""
        return self._residual_eng.signature(threshold=threshold)

    def reset(self) -> None:
        """Reset EWMA state and clear cached M3 actual."""
        self._residual_eng.reset()
        self._latest_m3_actual = None


# ---------------------------------------------------------------------------
# M2PrognosticsAdapter -- streaming M2 pipeline over a rolling residual buffer
# ---------------------------------------------------------------------------

class M2PrognosticsAdapter:
    """Runs M2's full prognostics pipeline in streaming (tick-by-tick) mode.

    M2's build_feature_table() is batch-oriented; this adapter maintains a
    rolling deque of residual rows and re-runs all M2 steps on each tick,
    returning the LAST row of the output table as a plain dict.

    M2 algorithm steps (matching feature_builder.build_feature_table):
      1.  normalize_residuals()       res_* -> norm_res_* (tolerance-scaled)
      2.  compute_composite_score()   weighted RMS of norm_res_*
      3.  apply_ewma_series()         EWMA of composite score
      4.  compute_health_index()      HI(t) = 100 * exp(-k * D(t))
      5.  compute_health_status()     "healthy" / "degraded" / "critical"
      6.  compute_severity_level()    ISO: NORMAL/ADVISORY/WARNING/CRITICAL_RTB
      7.  estimate_rul_with_uncertainty()  linear regression slope, 95% CI
      8.  health_slope                rolling linregress of HI vs time
      9.  res_cht_ewma, res_egt_ewma  EWMA of individual thermal residuals
      10. res_vib_std_w               rolling std of vibration residual

    Parameters
    ----------
    mission_duration_hours : float  M2 default 8.0
    buffer_maxlen          : int    Rolling buffer size (default 200 ~ 20s @ 10Hz)
    ewma_span              : float  M2 default 15.0
    rul_window             : int    M2 default 20  (regression window samples)
    health_k               : float  M2 default 0.5 (HI decay constant)
    eol_threshold          : float  M2 default 20.0 (HI at end-of-life)
    hi_trigger             : float  M2 default 85.0 (start RUL estimate below this)
    ci                     : float  M2 default 0.95 (confidence interval)
    """

    def __init__(
        self,
        mission_duration_hours: float = 8.0,
        buffer_maxlen:          int   = 200,
        ewma_span:              float = 15.0,
        rul_window:             int   = 20,
        health_k:               float = 0.5,
        eol_threshold:          float = 20.0,
        hi_trigger:             float = 85.0,
        ci:                     float = 0.95,
    ) -> None:
        self._mission_hours = mission_duration_hours
        self._ewma_span     = ewma_span
        self._rul_window    = rul_window
        self._health_k      = health_k
        self._eol_threshold = eol_threshold
        self._hi_trigger    = hi_trigger
        self._ci            = ci
        self._buf: Deque[dict] = collections.deque(maxlen=buffer_maxlen)

    def update(
        self,
        timestamp:    float,
        m2_residuals: Dict[str, float],
        fault_label:  str = "healthy",
    ) -> dict:
        """Append one residual row; run M2 pipeline; return last row as dict."""
        row = {"timestamp": timestamp, "fault_label": fault_label}
        row.update(m2_residuals)
        self._buf.append(row)

        df_res = pd.DataFrame(list(self._buf))

        # Step 1: Normalize
        norm_df = normalize_residuals(df_res)

        # Step 2: Composite score + EWMA
        composite = compute_composite_score(norm_df)

        out = pd.DataFrame()
        out["timestamp"] = df_res["timestamp"].values
        for col in M2_RESIDUAL_COLS:
            out[col] = df_res[col].values if col in df_res.columns else 0.0

        out["composite_score"] = composite.values
        out["composite_ewma"]  = apply_ewma_series(composite, span=self._ewma_span).values

        # Step 3: Health index + ISO severity
        out["health_index"]  = compute_health_index(out["composite_score"], k=self._health_k)
        out["health_status"]  = compute_health_status(out["health_index"])
        out["severity_level"] = compute_severity_level(out["health_index"])

        # Step 4: RUL with 95% CI (compute only for the current tick)
        n = len(out)
        rul_est_arr    = np.full(n, float("nan"))
        rul_lower_arr  = np.full(n, float("nan"))
        rul_upper_arr  = np.full(n, float("nan"))
        rul_status_arr = np.full(n, "not_estimable", dtype=object)

        est, lo, up, status = estimate_rul_with_uncertainty(
            out["health_index"],
            out["timestamp"],
            window                 = self._rul_window,
            eol_threshold          = self._eol_threshold,
            mission_duration_hours = self._mission_hours,
            hi_trigger             = self._hi_trigger,
            ci                     = self._ci,
        )
        rul_est_arr[-1]    = est
        rul_lower_arr[-1]  = lo
        rul_upper_arr[-1]  = up
        rul_status_arr[-1] = status

        out["rul_est"]    = rul_est_arr
        out["rul_lower"]  = rul_lower_arr
        out["rul_upper"]  = rul_upper_arr
        out["rul_status"] = rul_status_arr

        # Step 5: Engineered features
        slopes = np.full(n, float("nan"))
        w = self._rul_window
        if n >= w:
            hi_w   = out["health_index"].iloc[-w:].values
            ts_min = out["timestamp"].iloc[-w:].values / 60.0
            if (ts_min[-1] - ts_min[0]) > 0:
                from scipy.stats import linregress
                slope_val, *_ = linregress(ts_min, hi_w)
                slopes[-1] = slope_val
        out["health_slope"] = slopes

        out["res_cht_ewma"]  = apply_ewma_series(
            pd.Series(out["res_cht"].values), span=self._ewma_span).values
        out["res_egt_ewma"]  = apply_ewma_series(
            pd.Series(out["res_egt"].values), span=self._ewma_span).values
        out["res_vib_std_w"] = (
            pd.Series(out["res_vib"].values).rolling(10, min_periods=1).std().values)

        out["fault_label"] = (
            df_res["fault_label"].values
            if "fault_label" in df_res.columns else "unknown")

        last = out.iloc[-1]
        return {col: last[col] for col in out.columns}

    def reset(self) -> None:
        """Clear the rolling residual buffer."""
        self._buf.clear()


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

SubscriberCallback = Callable[["TelemetryFrame"], None]


class Orchestrator:
    """Central coordinator for the UAV engine digital twin system (M6).

    Data flow per tick
    ------------------
    M3 frame
      -> M1TwinAdapter.step()            # physics twin + residual engine
      -> m2_residuals (M2-named dict)
      -> M2PrognosticsAdapter.update()   # normalize, HI, severity, RUL, features
      -> m2_row (22-column dict)
      -> TelemetryFrame.from_m3_m1_m2()
      -> subscriber callbacks (M4 / M5)

    Parameters
    ----------
    twin_adapter           : M1TwinAdapter | None
    prognostics_adapter    : M2PrognosticsAdapter | None
    rate_hz                : float  target live tick rate (default 10 Hz)
    history_maxlen         : int    rolling frame buffer size
    environment            : str    M3 env: "standard_day"|"hot_day"|"high_altitude"
    throttle_mode          : str    M3 throttle: "smooth"|"idle_only"|"takeoff"|...
    mission_duration_hours : float  forwarded to M2 RUL estimator (default 8.0)
    """

    def __init__(
        self,
        twin_adapter:           Optional[M1TwinAdapter]        = None,
        prognostics_adapter:    Optional[M2PrognosticsAdapter] = None,
        rate_hz:                float = 10.0,
        history_maxlen:         int   = 1000,
        environment:            str   = "standard_day",
        throttle_mode:          str   = "smooth",
        mission_duration_hours: float = 8.0,
    ) -> None:
        self._adapter       = twin_adapter or M1TwinAdapter()
        self._m2            = prognostics_adapter or M2PrognosticsAdapter(
            mission_duration_hours=mission_duration_hours
        )
        self._rate_hz       = rate_hz
        self._environment   = environment
        self._throttle_mode = throttle_mode

        self._fault_manager = FaultManager()
        self._subscribers:  List[SubscriberCallback] = []
        self._history: Deque[TelemetryFrame] = collections.deque(maxlen=history_maxlen)
        self._latest: Optional[TelemetryFrame] = None

        self._running    = False
        self._thread: Optional[threading.Thread] = None
        self._tick_count = 0
        self._start_wall: Optional[float] = None
        self._lock = threading.Lock()

    # -- Subscriber management --------------------------------------------

    def subscribe(self, callback: SubscriberCallback) -> None:
        """Register a callback  (frame: TelemetryFrame) -> None."""
        with self._lock:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: SubscriberCallback) -> None:
        """Remove a previously registered callback."""
        with self._lock:
            try:
                self._subscribers.remove(callback)
            except ValueError:
                pass

    # -- Fault management -------------------------------------------------

    def inject_fault(self, scenario: FaultScenario) -> None:
        """Register a M3 fault scenario.

        Available: MisfireFault, OverheatingFault, OilPressureDropFault,
                   InjectorFault, VibrationSpikeFault, NoOpFault
        severity: 0.0 (mild) -> 1.0 (severe)
        """
        self._fault_manager.add(scenario)

    def clear_faults(self) -> None:
        """Remove all registered fault scenarios.

        WARNING CONTRACT (M3 -- FaultManager):
          clear() has no reset_clock(). Re-inject faults from t=0 for new runs.
          Renegotiate: add FaultManager.reset_time(offset).
        """
        self._fault_manager.clear()

    # -- Lifecycle --------------------------------------------------------

    def start(
        self,
        duration_s: Optional[float] = None,
        replay_csv: Optional[str]   = None,
        blocking:   bool            = False,
    ) -> None:
        """Start the orchestrator tick loop.

        duration_s : None = run until stop().
        replay_csv : path to M3 CSV -> replay mode (as-fast-as-possible).
        blocking   : True = block caller; False = background daemon thread.
        """
        if self._running:
            raise RuntimeError("Orchestrator already running -- call stop() first.")

        self._running    = True
        self._start_wall = time.perf_counter()
        self._tick_count = 0

        if replay_csv:
            fn     = self._run_replay_loop
            kwargs = {"csv_path": replay_csv, "duration_s": duration_s}
        else:
            fn     = self._run_live_loop
            kwargs = {"duration_s": duration_s}

        if blocking:
            fn(**kwargs)
        else:
            self._thread = threading.Thread(target=fn, kwargs=kwargs, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """Signal the tick loop to stop and join the thread."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        self._thread = None

    def reset(self) -> None:
        """Stop, clear history, reset M1 EWMA state and M2 rolling buffer."""
        self.stop()
        with self._lock:
            self._history.clear()
            self._latest     = None
            self._tick_count = 0
            self._start_wall = None
        self._adapter.reset()
        self._m2.reset()

    # -- Data access ------------------------------------------------------

    def get_latest(self) -> Optional[TelemetryFrame]:
        """Most recent TelemetryFrame, or None if not yet started."""
        with self._lock:
            return self._latest

    def get_history(self, n: int = 100) -> List[TelemetryFrame]:
        """Last n TelemetryFrames, oldest first."""
        with self._lock:
            frames = list(self._history)
        return frames[-n:] if n < len(frames) else frames

    def get_status(self) -> dict:
        """Snapshot of orchestrator + M2 prognostics health."""
        latest = self.get_latest()
        wall   = time.perf_counter() - self._start_wall if self._start_wall else 0.0
        return {
            "running":          self._running,
            "tick_count":       self._tick_count,
            "wall_time_s":      round(wall, 3),
            "achieved_rate_hz": round(self._tick_count / wall, 2) if wall > 0 else 0.0,
            "latest_timestamp": latest.timestamp     if latest else None,
            # M1
            "composite_score":  latest.composite_score if latest else None,
            # M2
            "health_index":     latest.health_index    if latest else None,
            "health_status":    latest.health_status   if latest else None,
            "severity_level":   latest.severity_level  if latest else None,
            "rul_est_min":      latest.rul_est          if latest else None,
            "rul_status":       latest.rul_status       if latest else None,
            # Ground truth
            "fault_label":      latest.fault_label      if latest else None,
            "subscriber_count": len(self._subscribers),
            "history_len":      len(self._history),
            "active_faults": [
                s.name for s in self._fault_manager.active_scenarios(
                    latest.timestamp if latest else 0.0
                )
            ],
        }

    # -- Internal helpers -------------------------------------------------

    def _process_frame(
        self,
        msg:         "EngineTelemetryMessage",
        fault_label: str,
        dt:          float,
    ) -> TelemetryFrame:
        """M1 tick -> M2 prognostics -> TelemetryFrame -> subscriber dispatch."""

        # M1: advance physics twin; get residuals renamed to M2 schema
        m2_residuals = self._adapter.step(msg, dt)

        # M2: streaming prognostics pipeline
        m2_row = self._m2.update(
            timestamp    = msg.timestamp,
            m2_residuals = m2_residuals,
            fault_label  = fault_label,
        )

        frame = TelemetryFrame.from_m3_m1_m2(msg, m2_residuals, m2_row, fault_label)

        with self._lock:
            self._latest = frame
            self._history.append(frame)
            self._tick_count += 1
            callbacks = list(self._subscribers)

        for cb in callbacks:
            try:
                cb(frame)
            except Exception as exc:
                print(f"[orchestrator] subscriber raised: {exc}", file=sys.stderr)

        return frame

    # -- Tick loops -------------------------------------------------------

    def _run_live_loop(self, duration_s: Optional[float] = None) -> None:
        """Live streaming via M3 TelemetryPublisher.

        WARNING CONTRACT (M3 -- TelemetryPublisher):
          run() is blocking; no step-at-a-time API.
          Renegotiate: expose generator/coroutine so M6 owns the tick loop.
        """
        prev_ts: Optional[float] = None
        default_dt = 1.0 / self._rate_hz

        def _cb(msg: "EngineTelemetryMessage", fault_label: str) -> None:
            nonlocal prev_ts
            if not self._running:
                return
            dt = (msg.timestamp - prev_ts) if prev_ts is not None else default_dt
            prev_ts = msg.timestamp
            self._process_frame(msg, fault_label, max(dt, 1e-6))

        publisher = TelemetryPublisher(
            rate_hz          = self._rate_hz,
            publish_cb       = _cb,
            fault_manager    = self._fault_manager,
            environment_name = self._environment,
            throttle_mode    = self._throttle_mode,
        )
        publisher.run(duration_s=duration_s if duration_s is not None else 86400.0)
        self._running = False

    def _run_replay_loop(
        self,
        csv_path:   str,
        duration_s: Optional[float] = None,
    ) -> None:
        """Replay mode: iterate frames from a saved M3 CSV.

        WARNING CONTRACT (M3 -- load_replay_csv):
          fault_label is stripped; all replayed frames arrive as "healthy".
          Renegotiate: yield (msg, label) tuples to preserve ground-truth labels.
        """
        prev_ts: Optional[float] = None
        default_dt = 1.0 / self._rate_hz

        for msg in load_replay_csv(csv_path):
            if not self._running:
                break
            if duration_s is not None and msg.timestamp > duration_s:
                break
            dt = (msg.timestamp - prev_ts) if prev_ts is not None else default_dt
            prev_ts = msg.timestamp
            # WARNING: fault_label lost in replay -- see CONTRACT above
            self._process_frame(msg, fault_label="healthy", dt=max(dt, 1e-6))

        self._running = False


# ---------------------------------------------------------------------------
# __main__ -- end-to-end integration smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    print("=" * 70)
    print("M6 Orchestrator -- End-to-End Integration Smoke Test")
    print("Wiring: M1 (DigitalTwin + ResidualEngine)")
    print("      + M2 (Prognostics / Feature Engineering)")
    print("      + M3 (TelemetryPublisher)")
    print("=" * 70)

    adapter = M1TwinAdapter(ambient_temp=25.0, ref_seed=42, ewma_alpha=0.10)
    m2_prog = M2PrognosticsAdapter(mission_duration_hours=8.0)
    orch = Orchestrator(
        twin_adapter           = adapter,
        prognostics_adapter    = m2_prog,
        rate_hz                = 10.0,
        history_maxlen         = 500,
        environment            = "standard_day",
        throttle_mode          = "smooth",
        mission_duration_hours = 8.0,
    )

    orch.inject_fault(OverheatingFault(severity=0.8, start_time_s=5.0, duration_s=20.0))

    def m4_callback(frame: TelemetryFrame) -> None:
        """M4 stub: anomaly detector input."""
        if frame.composite_score > 0.03:
            sig  = adapter.signature()
            top  = sig["dominant_channels"][:2]
            tops = ", ".join(f"{ch}={v:+.4f}" for ch, v in top)
            print(
                f"  [M4] t={frame.timestamp:5.1f}s  "
                f"score={frame.composite_score:.4f}  "
                f"HI={frame.health_index:5.1f}%  "
                f"sev={frame.severity_level:<12s}  "
                f"RUL={frame.rul_est:.1f}min ({frame.rul_status})  "
                f"label={frame.fault_label!r:<20s}  "
                f"dominant=[{tops}]"
            )

    _tick = [0]

    def m5_callback(frame: TelemetryFrame) -> None:
        """M5 stub: dashboard update."""
        _tick[0] += 1
        if _tick[0] % 20 == 0:    # every 2 s at 10 Hz
            print(
                f"  [M5] t={frame.timestamp:5.1f}s  "
                f"RPM={frame.rpm:6.0f}  "
                f"CHT={frame.cht:5.1f}C  "
                f"EGT={frame.egt:5.1f}C  "
                f"OilP={frame.oil_pressure:5.1f}psi  "
                f"HI={frame.health_index:5.1f}%  "
                f"sev={frame.severity_level:<12s}  "
                f"RUL~={frame.rul_est:.1f}min"
            )

    orch.subscribe(m4_callback)
    orch.subscribe(m5_callback)

    print("\n[orch] Live run: 30 s  |  overheating fault activates at t=5 s\n")
    orch.start(duration_s=30.0, blocking=True)

    status = orch.get_status()
    print("\n" + "=" * 70)
    print("Run complete -- orchestrator status:")
    for k, v in status.items():
        print(f"  {k:<24}: {v}")

    sig = adapter.signature()
    print("\nFinal M1 residual signature:")
    print(f"  severity       : {sig['severity']:.6f}")
    print(f"  fault_detected : {sig['fault_detected']}")
    print(f"  dominant       : {sig['dominant_channels'][:3]}")

    latest = orch.get_latest()
    if latest:
        print(f"\nFinal M2 prognostics (t={latest.timestamp:.1f}s):")
        print(f"  health_index   : {latest.health_index:.2f}%")
        print(f"  health_status  : {latest.health_status}")
        print(f"  severity_level : {latest.severity_level}")
        print(f"  rul_est        : {latest.rul_est:.1f} min")
        print(f"  rul_lower      : {latest.rul_lower:.1f} min")
        print(f"  rul_upper      : {latest.rul_upper:.1f} min")
        print(f"  rul_status     : {latest.rul_status}")
        print(f"  health_slope   : {latest.health_slope:.4f} pct/min")
        print(f"  composite_ewma : {latest.composite_ewma:.6f}")

    _replay = os.path.join(
        _REPO_ROOT, "m3_telemetry", "data", "replay_library",
        "fault_overheating_standard.csv",
    )
    if os.path.exists(_replay):
        print(f"\n[orch] Replay mode -- {os.path.basename(_replay)}")
        orch.reset()
        _tick[0] = 0
        orch.start(replay_csv=_replay, blocking=True)
        rs = orch.get_status()
        print(f"[orch] Replayed {rs['tick_count']} frames")
        latest = orch.get_latest()
        if latest:
            print(f"[orch] Final composite_score = {latest.composite_score:.6f}")
            print(f"[orch] Final health_index    = {latest.health_index:.2f}%")
            print(f"[orch] Final severity_level  = {latest.severity_level}")
    else:
        print("\n[orch] Replay CSV not found -- skipping.")
        print("       Expected: m3_telemetry/data/replay_library/")

    print("\nDone.")
