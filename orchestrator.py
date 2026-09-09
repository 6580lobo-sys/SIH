"""
orchestrator.py -- Comprehensive M1-M6 System Orchestrator
==========================================================
Integrates:
  - M1: Physics Digital Twin + Residual Engine (m3_fault_source coupled)
  - M2: Prognostics, Health Index, ISO-13381 RUL with 95% Confidence Intervals
  - M3: Telemetry Publisher, Flight Scenarios & Real Physical Fault Injection
  - M4: Real ML Models (Isolation Forest Anomaly Detector + Random Forest Multi-class Classifier + Explainability)
  - M5 / Frontend: Live telemetry stream, Scenario Manager, and Live Reliability Probe Sandbox.
"""

from __future__ import annotations

import collections
import copy
import math
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Deque, Dict, List, Optional, Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Path setup -- resolves repository roots accurately
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
if os.path.exists(os.path.join(_HERE, "M1")):
    _REPO_ROOT = _HERE
else:
    _REPO_ROOT = os.path.dirname(_HERE)

_M1_SRC = os.path.join(_REPO_ROOT, "M1", "src")
_M2_SRC = os.path.join(_REPO_ROOT, "M2")
_M3_SRC = os.path.join(_REPO_ROOT, "M3")
if not os.path.exists(_M3_SRC):
    _M3_SRC = os.path.join(_REPO_ROOT, "m3_telemetry")
_M4_DIR = os.path.join(_REPO_ROOT, "M4", "ml")
_M4_SRC = os.path.join(_M4_DIR, "src")

for _p in (_M1_SRC, _M2_SRC, _M3_SRC, _M4_DIR, _M4_SRC):
    if os.path.exists(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

# M1 imports
from twin_core.twin import DigitalTwin
from twin_core.residual import ResidualEngine

# M2 imports
from normalization import normalize_residuals
from ewma import apply_ewma_series
from composite_score import compute_composite_score
from health_index import (
    compute_health_index,
    compute_health_status,
    compute_severity_level,
)
from rul_uncertainty import estimate_rul_with_uncertainty

# M3 imports
from schema.telemetry_schema import EngineTelemetryMessage
from publisher.api import load_replay_csv
from publisher.streaming_harness import TelemetryPublisher
from generator.fault_injection import (
    FaultManager,
    FaultScenario,
    MisfireFault,
    OverheatingFault,
    OilPressureDropFault,
    InjectorFault,
    VibrationSpikeFault,
    NoOpFault,
)

# Concrete M3 fault extensions
try:
    from twin_core.m3_fault_source import (
        FuelMixtureDriftFault,
        CoolingBaffleFault,
        EngineOverspeedFault,
    )
except ImportError:
    FuelMixtureDriftFault = None
    CoolingBaffleFault = None
    EngineOverspeedFault = None

# M4 ML imports
_M4_AVAILABLE = False
try:
    from src.predict import predict_engine_health
    _M4_AVAILABLE = True
except Exception as _m4_err:
    print(f"[orchestrator] Notice: M4 ML model auto-load notice: {_m4_err}", file=sys.stderr)


# ---------------------------------------------------------------------------
# M1 -> M2 channel name mapping
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
# TelemetryFrame -- Combines M3, M1, M2, and M4 ML outputs
# ---------------------------------------------------------------------------

@dataclass
class TelemetryFrame:
    """One processed tick containing:
      - Raw M3 telemetry (sensor values, RPM, temperatures, pressures)
      - M1 physics residuals (actual - predicted by Digital Twin)
      - M2 prognostics (Health Index, ISO severity, RUL with 95% CI)
      - M4 ML model predictions (Isolation Forest score, RFC probabilities, SHAP explainability)
      - Ground-truth fault tags
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

    # M4 Machine Learning Predictions
    ml_anomaly:       bool = False
    ml_anomaly_score: float = 0.0
    ml_fault_type:    str  = "healthy"
    ml_confidence:    float = 0.0
    ml_health_state:  str  = "normal"
    ml_severity:      int  = 0
    ml_probabilities: Dict[str, float] = field(default_factory=dict)
    ml_top_features:  List[str]        = field(default_factory=list)
    ml_explanation:   str              = ""

    # Ground truth
    fault_label: str = "healthy"
    residuals:   Dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_m3_m1_m2_m4(
        cls,
        msg:          "EngineTelemetryMessage",
        m1_residuals: Dict[str, float],
        m2_row:       dict,
        m4_result:    Optional[dict] = None,
        fault_label:  str = "healthy",
    ) -> "TelemetryFrame":
        frame = cls(
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

        if m4_result:
            frame.ml_anomaly       = bool(m4_result.get("is_anomaly", False))
            frame.ml_anomaly_score = float(m4_result.get("anomaly_score", 0.0))
            frame.ml_fault_type    = str(m4_result.get("fault_type", "healthy"))
            frame.ml_confidence    = float(m4_result.get("confidence", 0.0))
            frame.ml_health_state  = str(m4_result.get("health_state", "normal"))
            frame.ml_severity      = int(m4_result.get("severity", 0))
            frame.ml_probabilities = dict(m4_result.get("probabilities", {}))
            frame.ml_top_features  = list(m4_result.get("top_features", []))
            frame.ml_explanation   = str(m4_result.get("explanation", ""))

        return frame

    def as_dict(self) -> dict:
        """Flat dictionary representation for JSON serialization & dashboard consumption."""
        def _clean_num(val, default=0.0):
            if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))):
                return default
            return val

        return {
            "timestamp":           _clean_num(self.timestamp),
            "msg_id":              self.msg_id,
            "rpm":                 _clean_num(self.rpm, 2400.0),
            "cht":                 _clean_num(self.cht, 167.0),
            "egt":                 _clean_num(self.egt, 610.0),
            "oil_pressure":        _clean_num(self.oil_pressure, 45.0),
            "oil_temp":            _clean_num(self.oil_temp, 94.0),
            "fuel_flow":           _clean_num(self.fuel_flow, 21.0),
            "vibration_amplitude": _clean_num(self.vibration_amplitude, 0.08),
            "vibration_freq":      _clean_num(self.vibration_freq, 36.0),
            "throttle_cmd":        _clean_num(self.throttle_cmd, 65.0),
            "res_rpm":             _clean_num(self.res_rpm),
            "res_cht":             _clean_num(self.res_cht),
            "res_egt":             _clean_num(self.res_egt),
            "res_oil_p":           _clean_num(self.res_oil_p),
            "res_oil_t":           _clean_num(self.res_oil_t),
            "res_fuel":            _clean_num(self.res_fuel),
            "res_vib":             _clean_num(self.res_vib),
            "composite_score":     _clean_num(self.composite_score),
            "composite_ewma":      _clean_num(self.composite_ewma),
            "health_index":        _clean_num(self.health_index, 100.0),
            "health_status":       self.health_status,
            "severity_level":      self.severity_level,
            "rul_est":             _clean_num(self.rul_est, 0.0),
            "rul_lower":           _clean_num(self.rul_lower, 0.0),
            "rul_upper":           _clean_num(self.rul_upper, 0.0),
            "rul_status":          self.rul_status,
            "health_slope":        _clean_num(self.health_slope, 0.0),
            "res_cht_ewma":        _clean_num(self.res_cht_ewma),
            "res_egt_ewma":        _clean_num(self.res_egt_ewma),
            "res_vib_std_w":       _clean_num(self.res_vib_std_w),
            "ml_anomaly":          self.ml_anomaly,
            "ml_anomaly_score":    _clean_num(self.ml_anomaly_score),
            "ml_fault_type":       self.ml_fault_type,
            "ml_confidence":       _clean_num(self.ml_confidence),
            "ml_health_state":     self.ml_health_state,
            "ml_severity":         self.ml_severity,
            "ml_probabilities":    self.ml_probabilities,
            "ml_top_features":     self.ml_top_features,
            "ml_explanation":      self.ml_explanation,
            "fault_label":         self.fault_label,
        }


# ---------------------------------------------------------------------------
# M1 Twin Adapter
# ---------------------------------------------------------------------------

_IDLE_ACTUAL: dict = {
    "timestamp": 0.0, "rpm": 1400.0, "cht": 90.0, "egt": 600.0,
    "oil_pressure": 20.0, "oil_temp": 50.0, "fuel_flow": 2.0,
    "vibration_amplitude": 0.02, "vibration_freq": 25.0,
    "throttle_cmd": 0.0,
}

class M1TwinAdapter:
    """Thin adapter around DigitalTwin + ResidualEngine."""

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
        return self._latest_m3_actual if self._latest_m3_actual else _IDLE_ACTUAL

    @staticmethod
    def _msg_to_m1_dict(msg: "EngineTelemetryMessage") -> dict:
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
        self._latest_m3_actual = self._msg_to_m1_dict(msg)
        pair = self._twin.step(msg.throttle_cmd, dt)
        self._residual_eng.update(pair)
        pred = pair["predicted"]
        act = pair["actual"]
        return {
            "res_rpm": act["rpm"] - pred["rpm"],
            "res_cht": act["cht"] - pred["cht"],
            "res_egt": act["egt"] - pred["egt"],
            "res_oil_p": (act["oil_pressure"] - pred["oil_pressure"]) * 0.0689476,
            "res_oil_t": act["oil_temp"] - pred["oil_temp"],
            "res_fuel": act["fuel_flow"] - pred["fuel_flow"],
            "res_vib": act["vibration_amplitude"] - pred["vibration_amplitude"],
        }

    def signature(self, threshold: float = 0.03) -> dict:
        return self._residual_eng.signature(threshold=threshold)

    def reset(self) -> None:
        self._residual_eng.reset()
        self._twin = DigitalTwin(
            actual_source=self._m3_bridge,
            ambient_temp=25.0,
            ref_seed=42,
        )
        self._latest_m3_actual = None


# ---------------------------------------------------------------------------
# M2 Prognostics Adapter
# ---------------------------------------------------------------------------

class M2PrognosticsAdapter:
    """Runs M2's streaming prognostics pipeline with linear regression RUL."""

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
        row = {"timestamp": timestamp, "fault_label": fault_label}
        row.update(m2_residuals)
        self._buf.append(row)

        df_res = pd.DataFrame(list(self._buf))
        norm_df = normalize_residuals(df_res)
        composite = compute_composite_score(norm_df)

        out = pd.DataFrame()
        out["timestamp"] = df_res["timestamp"].values
        for col in M2_RESIDUAL_COLS:
            out[col] = df_res[col].values if col in df_res.columns else 0.0

        out["composite_score"] = composite.values
        out["composite_ewma"]  = apply_ewma_series(composite, span=self._ewma_span).values

        out["health_index"]  = compute_health_index(out["composite_score"], k=self._health_k)
        out["health_status"]  = compute_health_status(out["health_index"])
        out["severity_level"] = compute_severity_level(out["health_index"])

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
        self._buf.clear()


# ---------------------------------------------------------------------------
# M4 Machine Learning Adapter
# ---------------------------------------------------------------------------

class M4MachineLearningAdapter:
    """Bridges telemetry and residual frames to M4's Isolation Forest and
    Random Forest multi-class classifiers. Maintains a rolling 30-frame window.
    """

    def __init__(self, window_size: int = 30) -> None:
        self._window_size = window_size
        self._window_buffer: Deque[dict] = collections.deque(maxlen=window_size)
        self._last_result: Optional[dict] = None
        self._lock = threading.Lock()

    def update(self, frame_dict: dict) -> Optional[dict]:
        """Update window with latest tick and run inference."""
        if not _M4_AVAILABLE:
            return None

        # Build row matching M4 ML training schema
        row = {
            "timestamp": frame_dict.get("timestamp", 0.0),
            "rpm": frame_dict.get("rpm", 2400.0),
            "throttle": frame_dict.get("throttle_cmd", 65.0),
            "oil_pressure": frame_dict.get("oil_pressure", 45.0),
            "oil_temp": frame_dict.get("oil_temp", 80.0),
            "cht": frame_dict.get("cht", 175.0),
            "egt": frame_dict.get("egt", 740.0),
            "manifold_pressure": 28.5,
            "vibration": frame_dict.get("vibration_amplitude", 0.02),
            "fuel_flow": frame_dict.get("fuel_flow", 24.0),
            "ambient_temp": 25.0,
            "altitude": 5000.0,
            "mission_phase": "cruise",
            "residual_rpm": frame_dict.get("res_rpm", 0.0),
            "residual_oil_pressure": frame_dict.get("res_oil_p", 0.0),
            "residual_oil_temp": frame_dict.get("res_oil_t", 0.0),
            "residual_cht": frame_dict.get("res_cht", 0.0),
            "residual_egt": frame_dict.get("res_egt", 0.0),
            "residual_manifold_pressure": 0.0,
            "residual_vibration": frame_dict.get("res_vib", 0.0),
            "residual_fuel_flow": frame_dict.get("res_fuel", 0.0),
            "health_index": frame_dict.get("health_index", 100.0),
            "baseline_rul": frame_dict.get("rul_est", 480.0) if not np.isnan(frame_dict.get("rul_est", float("nan"))) else 480.0,
        }

        with self._lock:
            self._window_buffer.append(row)
            # Replicate initial rows if window not yet full
            if len(self._window_buffer) < self._window_size:
                fill_count = self._window_size - len(self._window_buffer)
                buf_list = [self._window_buffer[0]] * fill_count + list(self._window_buffer)
            else:
                buf_list = list(self._window_buffer)

        try:
            window_df = pd.DataFrame(buf_list)
            res = predict_engine_health(window_df)
            self._last_result = res
            return res
        except Exception as exc:
            return None

    def evaluate_manual_sample(self, sample: dict) -> dict:
        """Run ML prediction on an explicit user-provided sensor state."""
        if not _M4_AVAILABLE:
            return {
                "is_anomaly": False,
                "anomaly_score": 0.0,
                "fault_type": "healthy",
                "confidence": 0.99,
                "health_state": "normal",
                "severity": 0,
                "probabilities": {"healthy": 0.99},
                "top_features": [],
                "explanation": "M4 ML module unavailable.",
            }

        rows = []
        for i in range(self._window_size):
            rows.append({
                "timestamp": float(i),
                "rpm": sample.get("rpm", 2400.0),
                "throttle": sample.get("throttle", 65.0),
                "oil_pressure": sample.get("oil_pressure", 45.0),
                "oil_temp": sample.get("oil_temp", 80.0),
                "cht": sample.get("cht", 175.0),
                "egt": sample.get("egt", 740.0),
                "manifold_pressure": sample.get("manifold_pressure", 28.5),
                "vibration": sample.get("vibration", 0.02),
                "fuel_flow": sample.get("fuel_flow", 24.0),
                "ambient_temp": sample.get("ambient_temp", 25.0),
                "altitude": sample.get("altitude", 5000.0),
                "mission_phase": sample.get("mission_phase", "cruise"),
                "residual_rpm": sample.get("residual_rpm", 0.0),
                "residual_oil_pressure": sample.get("residual_oil_pressure", 0.0),
                "residual_oil_temp": sample.get("residual_oil_temp", 0.0),
                "residual_cht": sample.get("residual_cht", 0.0),
                "residual_egt": sample.get("residual_egt", 0.0),
                "residual_manifold_pressure": 0.0,
                "residual_vibration": sample.get("residual_vibration", 0.0),
                "residual_fuel_flow": sample.get("residual_fuel_flow", 0.0),
                "health_index": sample.get("health_index", 100.0),
                "baseline_rul": sample.get("baseline_rul", 480.0),
            })
        window_df = pd.DataFrame(rows)
        return predict_engine_health(window_df)

    def reset(self) -> None:
        with self._lock:
            self._window_buffer.clear()
            self._last_result = None


# ---------------------------------------------------------------------------
# Continuous Scenario Fault Generators for Real-Time GCS Operation
# ---------------------------------------------------------------------------

class ContinuousScenarioFault(FaultScenario):
    """Base class for active GCS scenario faults that persist until cleared."""

    def __init__(self, name: str, start_time_s: float = 0.0) -> None:
        super().__init__(name=name, start_time_s=start_time_s, duration_s=86400.0)

    def is_active(self, t_s: float) -> bool:
        return t_s >= self.start_time_s

    def ramp(self, elapsed_s: float, tau: float = 0.8) -> float:
        """Smooth exponential ramp reaching ~95% in 2-3 seconds."""
        if elapsed_s <= 0:
            return 0.0
        return 1.0 - math.exp(-elapsed_s / tau)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r}, start={self.start_time_s:.1f}s)"


class ContinuousOverheatingFault(ContinuousScenarioFault):
    def __init__(self, start_time_s: float = 0.0, severity: float = 0.85) -> None:
        super().__init__(name="overheating", start_time_s=start_time_s)
        self.severity = severity

    def apply(self, t_s: float, healthy_values: dict) -> dict:
        v = copy.deepcopy(healthy_values)
        el = max(0.0, t_s - self.start_time_s)
        p = self.ramp(el, tau=2.0) * self.severity
        delta_cht = 55.0 * p
        delta_egt = 110.0 * p
        delta_oil = 25.0 * p

        for k in ("cht_c", "cht"):
            if k in v: v[k] += delta_cht
        for k in ("egt_c", "egt"):
            if k in v: v[k] += delta_egt
        for k in ("oil_temp_c", "oil_temp"):
            if k in v: v[k] += delta_oil
        return v


class ContinuousOilPressureDropFault(ContinuousScenarioFault):
    def __init__(self, start_time_s: float = 0.0, severity: float = 0.85) -> None:
        super().__init__(name="oil_pressure_drop", start_time_s=start_time_s)
        self.severity = severity

    def apply(self, t_s: float, healthy_values: dict) -> dict:
        v = copy.deepcopy(healthy_values)
        el = max(0.0, t_s - self.start_time_s)
        p = self.ramp(el, tau=1.5) * self.severity
        drop_factor = 1.0 - (0.75 * p)

        for k in ("oil_pressure_kpa", "oil_pressure"):
            if k in v: v[k] *= drop_factor
        for k in ("oil_temp_c", "oil_temp"):
            if k in v: v[k] += 22.0 * p
        return v


class ContinuousVibrationFault(ContinuousScenarioFault):
    def __init__(self, start_time_s: float = 0.0, severity: float = 0.85) -> None:
        super().__init__(name="vibration_bearing_fault", start_time_s=start_time_s)
        self.severity = severity

    def apply(self, t_s: float, healthy_values: dict) -> dict:
        v = copy.deepcopy(healthy_values)
        el = max(0.0, t_s - self.start_time_s)
        p = self.ramp(el, tau=1.5) * self.severity
        delta = 0.18 * p

        if "vibration_amplitude" in v:
            v["vibration_amplitude"] += delta
        if "vibration_g" in v:
            v["vibration_g"] += delta
        if "vibration_freq" in v:
            v["vibration_freq"] = 35.0 + (15.0 * p)
        return v


class ContinuousAbnormalOilTempFault(ContinuousScenarioFault):
    def __init__(self, start_time_s: float = 0.0, severity: float = 0.80) -> None:
        super().__init__(name="abnormal_oil_temp", start_time_s=start_time_s)
        self.severity = severity

    def apply(self, t_s: float, healthy_values: dict) -> dict:
        v = copy.deepcopy(healthy_values)
        el = max(0.0, t_s - self.start_time_s)
        p = self.ramp(el, tau=2.5) * self.severity
        for k in ("oil_temp_c", "oil_temp"):
            if k in v: v[k] += 32.0 * p
        for k in ("oil_pressure_kpa", "oil_pressure"):
            if k in v: v[k] *= (1.0 - 0.25 * p)
        return v


class ContinuousElevatedEgtFault(ContinuousScenarioFault):
    def __init__(self, start_time_s: float = 0.0, severity: float = 0.80) -> None:
        super().__init__(name="elevated_egt", start_time_s=start_time_s)
        self.severity = severity

    def apply(self, t_s: float, healthy_values: dict) -> dict:
        v = copy.deepcopy(healthy_values)
        el = max(0.0, t_s - self.start_time_s)
        p = self.ramp(el, tau=2.0) * self.severity
        for k in ("egt_c", "egt"):
            if k in v: v[k] += 180.0 * p
        for k in ("fuel_flow", "fuel_flow_g_s"):
            if k in v: v[k] += 3.5 * p
        return v


class ContinuousInjectorFault(ContinuousScenarioFault):
    def __init__(self, start_time_s: float = 0.0, severity: float = 0.80) -> None:
        super().__init__(name="misfire_or_injector_fault", start_time_s=start_time_s)
        self.severity = severity

    def apply(self, t_s: float, healthy_values: dict) -> dict:
        v = copy.deepcopy(healthy_values)
        el = max(0.0, t_s - self.start_time_s)
        p = self.ramp(el, tau=1.5) * self.severity
        pulse = math.sin(t_s * 6.28 * 2.0)
        for k in ("egt_c", "egt"):
            if k in v: v[k] += 48.0 * p
        if "rpm" in v:
            v["rpm"] -= (35.0 * p + 15.0 * pulse * p)
        if "vibration_amplitude" in v:
            v["vibration_amplitude"] += 0.07 * p
        if "vibration_g" in v:
            v["vibration_g"] += 0.9 * p
        return v


class ContinuousFuelMixtureFault(ContinuousScenarioFault):
    def __init__(self, start_time_s: float = 0.0, severity: float = 0.75) -> None:
        super().__init__(name="fuel_mixture_drift", start_time_s=start_time_s)
        self.severity = severity

    def apply(self, t_s: float, healthy_values: dict) -> dict:
        v = copy.deepcopy(healthy_values)
        el = max(0.0, t_s - self.start_time_s)
        p = self.ramp(el, tau=2.5) * self.severity
        for k in ("fuel_flow", "fuel_flow_g_s"):
            if k in v: v[k] += 6.2 * p
        for k in ("egt_c", "egt"):
            if k in v: v[k] += 120.0 * p
        return v


class ContinuousCoolingFault(ContinuousScenarioFault):
    def __init__(self, start_time_s: float = 0.0, severity: float = 0.80) -> None:
        super().__init__(name="cooling_system_fault", start_time_s=start_time_s)
        self.severity = severity

    def apply(self, t_s: float, healthy_values: dict) -> dict:
        v = copy.deepcopy(healthy_values)
        el = max(0.0, t_s - self.start_time_s)
        p = self.ramp(el, tau=2.0) * self.severity
        for k in ("cht_c", "cht"):
            if k in v: v[k] += 38.0 * p
        for k in ("oil_temp_c", "oil_temp"):
            if k in v: v[k] += 16.0 * p
        return v


class ContinuousOverspeedFault(ContinuousScenarioFault):
    def __init__(self, start_time_s: float = 0.0, severity: float = 0.80) -> None:
        super().__init__(name="engine_overspeed", start_time_s=start_time_s)
        self.severity = severity

    def apply(self, t_s: float, healthy_values: dict) -> dict:
        v = copy.deepcopy(healthy_values)
        el = max(0.0, t_s - self.start_time_s)
        p = self.ramp(el, tau=1.5) * self.severity
        if "rpm" in v:
            v["rpm"] += 380.0 * p
        if "throttle_cmd" in v:
            v["throttle_cmd"] = min(100.0, v["throttle_cmd"] + 25.0 * p)
        return v


class ContinuousCompoundFault(ContinuousScenarioFault):
    def __init__(self, start_time_s: float = 0.0, severity: float = 0.85) -> None:
        super().__init__(name="compound_failure", start_time_s=start_time_s)
        self.severity = severity

    def apply(self, t_s: float, healthy_values: dict) -> dict:
        v = copy.deepcopy(healthy_values)
        el = max(0.0, t_s - self.start_time_s)
        p = self.ramp(el, tau=2.0) * self.severity
        for k in ("oil_pressure_kpa", "oil_pressure"):
            if k in v: v[k] *= (1.0 - 0.70 * p)
        for k in ("cht_c", "cht"):
            if k in v: v[k] += 50.0 * p
        for k in ("egt_c", "egt"):
            if k in v: v[k] += 95.0 * p
        for k in ("oil_temp_c", "oil_temp"):
            if k in v: v[k] += 26.0 * p
        if "vibration_amplitude" in v:
            v["vibration_amplitude"] = 0.08 + (0.24 * p)
        if "vibration_g" in v:
            v["vibration_g"] = 0.8 + (2.8 * p)
        return v


# ---------------------------------------------------------------------------
# Scenario Configuration Manager
# ---------------------------------------------------------------------------

class ScenarioManager:
    """Manages preset and custom telemetry and physical fault injection scenarios."""

    PRESETS = {
        "nominal_cruise": {
            "name": "Nominal Cruise Flight",
            "description": "Standard cruise at 2400 RPM, 65% throttle, standard day, no faults.",
            "environment": "standard_day",
            "throttle_mode": "smooth",
            "faults": [],
        },
        "healthy": {
            "name": "Healthy Baseline",
            "description": "Standard cruise at 2400 RPM, 65% throttle, standard day, no faults.",
            "environment": "standard_day",
            "throttle_mode": "smooth",
            "faults": [],
        },
        "abnormal_oil_temp": {
            "name": "Abnormal Oil Temp (Thermal Degradation)",
            "description": "Oil cooler airflow restriction, oil temperature escalation past 120°C.",
            "environment": "hot_day",
            "throttle_mode": "smooth",
            "faults": [{"type": "ContinuousAbnormalOilTempFault", "severity": 0.80}],
        },
        "elevated_egt": {
            "name": "Elevated Exhaust Gas Temp (EGT)",
            "description": "Injector thermal drift inducing high exhaust temperature in Cylinder #3.",
            "environment": "standard_day",
            "throttle_mode": "smooth",
            "faults": [{"type": "ContinuousElevatedEgtFault", "severity": 0.80}],
        },
        "cht_overheating": {
            "name": "Severe CHT Thermal Runaway",
            "description": "Cooling baffle deformation causing rapid CHT escalation past 210°C.",
            "environment": "hot_day",
            "throttle_mode": "smooth",
            "faults": [{"type": "ContinuousOverheatingFault", "severity": 0.90}],
        },
        "overheating": {
            "name": "Overheating Scenario",
            "description": "Severe thermal runaway with high CHT and EGT.",
            "environment": "hot_day",
            "throttle_mode": "smooth",
            "faults": [{"type": "ContinuousOverheatingFault", "severity": 0.90}],
        },
        "oil_pressure_loss": {
            "name": "Critical Oil Pressure Loss",
            "description": "Scavenge pump cavitation dropping oil pressure down to 14 PSI.",
            "environment": "standard_day",
            "throttle_mode": "smooth",
            "faults": [{"type": "ContinuousOilPressureDropFault", "severity": 0.85}],
        },
        "oil_pressure_drop": {
            "name": "Critical Oil Pressure Drop",
            "description": "Scavenge pump cavitation dropping oil pressure down to 14 PSI.",
            "environment": "standard_day",
            "throttle_mode": "smooth",
            "faults": [{"type": "ContinuousOilPressureDropFault", "severity": 0.85}],
        },
        "bearing_vibration": {
            "name": "Bearing Wear & Vibration Anomaly",
            "description": "Main journal bearing spalling causing vibration amplitude surge to 3.8g.",
            "environment": "standard_day",
            "throttle_mode": "rapid_transient",
            "faults": [{"type": "ContinuousVibrationFault", "severity": 0.85}],
        },
        "vibration_bearing_fault": {
            "name": "Bearing Wear & Vibration Anomaly",
            "description": "Main journal bearing spalling causing vibration amplitude surge to 3.8g.",
            "environment": "standard_day",
            "throttle_mode": "rapid_transient",
            "faults": [{"type": "ContinuousVibrationFault", "severity": 0.85}],
        },
        "misfire_or_injector_fault": {
            "name": "Injector Imbalance & Cylinder Misfire",
            "description": "Cylinder 3 injector blockage leading to high EGT variance and RPM dip.",
            "environment": "standard_day",
            "throttle_mode": "smooth",
            "faults": [{"type": "ContinuousInjectorFault", "severity": 0.80}],
        },
        "fuel_mixture_drift": {
            "name": "Fuel Mixture Lean Drift",
            "description": "Fuel pressure regulator bias causing lean surging and high fuel consumption.",
            "environment": "high_altitude",
            "throttle_mode": "smooth",
            "faults": [{"type": "ContinuousFuelMixtureFault", "severity": 0.75}],
        },
        "cooling_system_fault": {
            "name": "Cooling Baffle Obstruction",
            "description": "Ram-air cooling cowl obstruction causing CHT escalation.",
            "environment": "hot_day",
            "throttle_mode": "smooth",
            "faults": [{"type": "ContinuousCoolingFault", "severity": 0.80}],
        },
        "engine_overspeed": {
            "name": "Governor Overspeed Runaway",
            "description": "Propeller pitch governor failure causing engine overspeed past redline.",
            "environment": "standard_day",
            "throttle_mode": "rapid_transient",
            "faults": [{"type": "ContinuousOverspeedFault", "severity": 0.80}],
        },
        "compound_failure": {
            "name": "Compound Multi-Fault Breakdown",
            "description": "Oil pressure drop accompanied by severe overheating and vibration spike.",
            "environment": "hot_day",
            "throttle_mode": "rapid_transient",
            "faults": [{"type": "ContinuousCompoundFault", "severity": 0.85}],
        },
    }

    def __init__(self) -> None:
        self._custom_scenarios: Dict[str, dict] = {}

    def get_all_scenarios(self) -> Dict[str, dict]:
        combined = dict(self.PRESETS)
        combined.update(self._custom_scenarios)
        return combined

    def save_custom_scenario(self, key: str, scenario_data: dict) -> None:
        self._custom_scenarios[key] = scenario_data

    def create_fault_objects(self, scenario_key: str, base_time_s: float = 0.0) -> List[FaultScenario]:
        all_s = self.get_all_scenarios()
        cfg = all_s.get(scenario_key)
        if not cfg:
            return []

        fault_objs: List[FaultScenario] = []
        for f in cfg.get("faults", []):
            ftype = f.get("type", "")
            sev = float(f.get("severity", 0.75))

            if ftype in ("ContinuousOverheatingFault", "OverheatingFault"):
                fault_objs.append(ContinuousOverheatingFault(start_time_s=base_time_s, severity=sev))
            elif ftype in ("ContinuousOilPressureDropFault", "OilPressureDropFault"):
                fault_objs.append(ContinuousOilPressureDropFault(start_time_s=base_time_s, severity=sev))
            elif ftype in ("ContinuousVibrationFault", "VibrationSpikeFault"):
                fault_objs.append(ContinuousVibrationFault(start_time_s=base_time_s, severity=sev))
            elif ftype in ("ContinuousAbnormalOilTempFault", "AbnormalOilTempFault"):
                fault_objs.append(ContinuousAbnormalOilTempFault(start_time_s=base_time_s, severity=sev))
            elif ftype in ("ContinuousElevatedEgtFault", "ElevatedEgtFault"):
                fault_objs.append(ContinuousElevatedEgtFault(start_time_s=base_time_s, severity=sev))
            elif ftype in ("ContinuousInjectorFault", "InjectorFault", "MisfireFault"):
                fault_objs.append(ContinuousInjectorFault(start_time_s=base_time_s, severity=sev))
            elif ftype in ("ContinuousFuelMixtureFault", "FuelMixtureDriftFault"):
                fault_objs.append(ContinuousFuelMixtureFault(start_time_s=base_time_s, severity=sev))
            elif ftype in ("ContinuousCoolingFault", "CoolingBaffleFault"):
                fault_objs.append(ContinuousCoolingFault(start_time_s=base_time_s, severity=sev))
            elif ftype in ("ContinuousOverspeedFault", "EngineOverspeedFault"):
                fault_objs.append(ContinuousOverspeedFault(start_time_s=base_time_s, severity=sev))
            elif ftype in ("ContinuousCompoundFault", "CompoundFault"):
                fault_objs.append(ContinuousCompoundFault(start_time_s=base_time_s, severity=sev))
        return fault_objs


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

SubscriberCallback = Callable[["TelemetryFrame"], None]

class Orchestrator:
    """Central coordinator for the UAV engine digital twin system (M6).

    Coordinates:
      - M3 physics telemetry generator / streaming harness
      - M1 physics twin and residual engine
      - M2 feature engineering, health index, ISO severity, and RUL estimation
      - M4 machine learning anomaly detection and multi-class classification
      - Scenario Manager for preset/custom operational conditions
      - Live Telemetry Probe for manual reliability validation
    """

    def __init__(
        self,
        twin_adapter:           Optional[M1TwinAdapter]        = None,
        prognostics_adapter:    Optional[M2PrognosticsAdapter] = None,
        ml_adapter:             Optional[M4MachineLearningAdapter] = None,
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
        self._ml            = ml_adapter or M4MachineLearningAdapter()
        self._scenario_mgr  = ScenarioManager()
        self._current_scenario = "nominal_cruise"

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
        self._publisher: Optional[TelemetryPublisher] = None

    # -- Subscriber management --------------------------------------------

    def subscribe(self, callback: SubscriberCallback) -> None:
        with self._lock:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: SubscriberCallback) -> None:
        with self._lock:
            try:
                self._subscribers.remove(callback)
            except ValueError:
                pass

    # -- Scenario & Fault management --------------------------------------

    @property
    def scenario_manager(self) -> ScenarioManager:
        return self._scenario_mgr

    def load_scenario(self, scenario_key: str) -> None:
        """Switch operational scenario and configure corresponding M3 fault generators."""
        self.clear_faults()
        self._current_scenario = scenario_key
        if scenario_key in ("healthy", "nominal_cruise", "nominal"):
            self._m2.reset()
            self._adapter.reset()
            if self._publisher is not None:
                self._publisher.reset_engine()
            return

        scenarios = self._scenario_mgr.get_all_scenarios()
        cfg = scenarios.get(scenario_key)
        if cfg:
            self._environment = cfg.get("environment", "standard_day")
            self._throttle_mode = cfg.get("throttle_mode", "smooth")
            current_ts = self._latest.timestamp if self._latest is not None else 0.0
            base_ts = max(0.0, current_ts - 0.2)
            for f_obj in self._scenario_mgr.create_fault_objects(scenario_key, base_time_s=base_ts):
                self.inject_fault(f_obj)

    def inject_fault(self, scenario: FaultScenario) -> None:
        self._fault_manager.add(scenario)

    def clear_faults(self) -> None:
        self._fault_manager.clear()

    # -- Manual Telemetry Probe / Reliability Sandbox --------------------

    def evaluate_live_probe(self, probe_values: dict) -> dict:
        """Evaluates an arbitrary manual sensor state through M1 -> M2 -> M4.
        
        probe_values: {
            "rpm": float, "throttle": float, "oil_pressure": float,
            "oil_temp": float, "cht": float, "egt": float,
            "fuel_flow": float, "vibration": float, "mission_duration_hours": float
        }
        """
        rpm = float(probe_values.get("rpm", 2400.0))
        throttle = float(probe_values.get("throttle", 65.0))
        oil_p = float(probe_values.get("oil_pressure", 45.0))
        oil_t = float(probe_values.get("oil_temp", 80.0))
        cht = float(probe_values.get("cht", 175.0))
        egt = float(probe_values.get("egt", 740.0))
        fuel_f = float(probe_values.get("fuel_flow", 24.0))
        vib = float(probe_values.get("vibration", 0.02))

        # Synthetic M3 telemetry message
        msg = EngineTelemetryMessage(
            timestamp=time.time(),
            msg_id="PROBE-01",
            rpm=rpm,
            cht=cht,
            egt=egt,
            oil_pressure=oil_p,
            oil_temp=oil_t,
            fuel_flow=fuel_f,
            vibration_amplitude=vib,
            vibration_freq=vib * 1200.0,
            throttle_cmd=throttle,
        )

        # M1 physics twin step
        m2_res = self._adapter.step(msg, dt=0.1)

        # M2 prognostics update
        m2_row = self._m2.update(timestamp=msg.timestamp, m2_residuals=m2_res, fault_label="manual_probe")

        # M4 ML inference
        sample_m4 = {
            "rpm": rpm, "throttle": throttle, "oil_pressure": oil_p,
            "oil_temp": oil_t, "cht": cht, "egt": egt,
            "manifold_pressure": 28.5, "vibration": vib, "fuel_flow": fuel_f,
            "residual_rpm": m2_res.get("res_rpm", 0.0),
            "residual_oil_pressure": m2_res.get("res_oil_p", 0.0),
            "residual_oil_temp": m2_res.get("res_oil_t", 0.0),
            "residual_cht": m2_res.get("res_cht", 0.0),
            "residual_egt": m2_res.get("res_egt", 0.0),
            "residual_vibration": m2_res.get("res_vib", 0.0),
            "residual_fuel_flow": m2_res.get("res_fuel", 0.0),
            "health_index": m2_row.get("health_index", 100.0),
            "baseline_rul": m2_row.get("rul_est", 480.0) if not np.isnan(m2_row.get("rul_est", float("nan"))) else 480.0,
        }
        ml_res = self._ml.evaluate_manual_sample(sample_m4)

        return {
            "inputs": probe_values,
            "m1_residuals": m2_res,
            "m2_prognostics": m2_row,
            "m4_ml_prediction": ml_res,
        }

    # -- Lifecycle --------------------------------------------------------

    def start(
        self,
        duration_s: Optional[float] = None,
        replay_csv: Optional[str]   = None,
        blocking:   bool            = False,
    ) -> None:
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
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        self._thread = None

    def reset(self) -> None:
        self.stop()
        with self._lock:
            self._history.clear()
            self._latest     = None
            self._tick_count = 0
            self._start_wall = None
        self._adapter.reset()
        self._m2.reset()
        self._ml.reset()

    # -- Data access ------------------------------------------------------

    def get_latest(self) -> Optional[TelemetryFrame]:
        with self._lock:
            return self._latest

    def get_history(self, n: int = 100) -> List[TelemetryFrame]:
        with self._lock:
            frames = list(self._history)
        return frames[-n:] if n < len(frames) else frames

    def get_status(self) -> dict:
        latest = self.get_latest()
        wall   = time.perf_counter() - self._start_wall if self._start_wall else 0.0
        return {
            "running":          self._running,
            "current_scenario": self._current_scenario,
            "tick_count":       self._tick_count,
            "wall_time_s":      round(wall, 3),
            "achieved_rate_hz": round(self._tick_count / wall, 2) if wall > 0 else 0.0,
            "latest_timestamp": latest.timestamp     if latest else None,
            "composite_score":  latest.composite_score if latest else None,
            "health_index":     latest.health_index    if latest else None,
            "health_status":    latest.health_status   if latest else None,
            "severity_level":   latest.severity_level  if latest else None,
            "rul_est_min":      latest.rul_est          if latest else None,
            "rul_status":       latest.rul_status       if latest else None,
            "ml_anomaly":       latest.ml_anomaly       if latest else None,
            "ml_fault_type":    latest.ml_fault_type    if latest else None,
            "ml_confidence":    latest.ml_confidence    if latest else None,
            "fault_label":      latest.fault_label      if latest else None,
            "subscriber_count": len(self._subscribers),
            "history_len":      len(self._history),
            "active_faults": [
                s.name for s in self._fault_manager.active_scenarios(
                    latest.timestamp if latest else 0.0
                )
            ],
        }

    # -- Internal frame processing ---------------------------------------

    def _process_frame(
        self,
        msg:         "EngineTelemetryMessage",
        fault_label: str,
        dt:          float,
    ) -> TelemetryFrame:
        # Step 1: M1 Physics Digital Twin Step
        m2_residuals = self._adapter.step(msg, dt)

        # Step 2: M2 Prognostics Pipeline
        m2_row = self._m2.update(
            timestamp    = msg.timestamp,
            m2_residuals = m2_residuals,
            fault_label  = fault_label,
        )

        # Step 3: M4 Real Machine Learning Inference
        m4_row_dict = {
            "timestamp":           msg.timestamp,
            "rpm":                 msg.rpm,
            "throttle_cmd":        msg.throttle_cmd,
            "oil_pressure":        msg.oil_pressure,
            "oil_temp":            msg.oil_temp,
            "cht":                 msg.cht,
            "egt":                 msg.egt,
            "vibration_amplitude": msg.vibration_amplitude,
            "fuel_flow":           msg.fuel_flow,
            "health_index":        m2_row.get("health_index", 100.0),
            "rul_est":             m2_row.get("rul_est", float("nan")),
        }
        m4_row_dict.update(m2_residuals)
        m4_res = self._ml.update(m4_row_dict)

        # Step 4: Assemble Combined TelemetryFrame
        frame = TelemetryFrame.from_m3_m1_m2_m4(
            msg          = msg,
            m1_residuals = m2_residuals,
            m2_row       = m2_row,
            m4_result    = m4_res,
            fault_label  = fault_label,
        )

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
        self._publisher = publisher
        publisher.run(duration_s=duration_s if duration_s is not None else 86400.0)
        self._running = False

    def _run_replay_loop(
        self,
        csv_path:   str,
        duration_s: Optional[float] = None,
    ) -> None:
        prev_ts: Optional[float] = None
        default_dt = 1.0 / self._rate_hz

        for msg in load_replay_csv(csv_path):
            if not self._running:
                break
            if duration_s is not None and msg.timestamp > duration_s:
                break
            dt = (msg.timestamp - prev_ts) if prev_ts is not None else default_dt
            prev_ts = msg.timestamp
            self._process_frame(msg, fault_label="healthy", dt=max(dt, 1e-6))

        self._running = False


# ---------------------------------------------------------------------------
# __main__ -- End-to-End System Smoke Test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 75)
    print("M6 Orchestrator -- End-to-End System Integration Smoke Test")
    print("Wiring: M1 (Twin + M3-coupled residuals)")
    print("      + M2 (Prognostics, Health Index, ISO Severity, RUL CI)")
    print("      + M3 (TelemetryPublisher & Real Fault Injectors)")
    print("      + M4 (Real ML: Isolation Forest + Random Forest + Explainability)")
    print("      + Scenario Manager & Manual Live Probe Sandbox")
    print("=" * 75)

    orch = Orchestrator(
        rate_hz=10.0,
        history_maxlen=500,
        mission_duration_hours=8.0,
    )

    print("\n1. Testing Preset Scenario Loading: abnormal_oil_temp")
    orch.load_scenario("abnormal_oil_temp")
    print(f"Loaded scenario: {orch._current_scenario}")
    print(f"Active faults: {[s.name for s in orch._fault_manager.active_scenarios(0.0)]}")

    print("\n2. Testing Manual Telemetry Live Reliability Probe (Sandboxed)")
    probe_sample = {
        "rpm": 2420.0,
        "throttle": 65.0,
        "oil_pressure": 15.0,  # low oil pressure
        "oil_temp": 125.0,     # abnormal high oil temp
        "cht": 195.0,
        "egt": 780.0,
        "fuel_flow": 26.0,
        "vibration": 0.08,
    }
    probe_result = orch.evaluate_live_probe(probe_sample)
    print("Probe Evaluation Output:")
    print("  M1 Residuals (Oil P, Oil T):", probe_result["m1_residuals"].get("res_oil_p"), probe_result["m1_residuals"].get("res_oil_t"))
    print("  M2 Health Index:", probe_result["m2_prognostics"].get("health_index"))
    print("  M2 Severity:", probe_result["m2_prognostics"].get("severity_level"))
    print("  M4 ML Anomaly:", probe_result["m4_ml_prediction"].get("is_anomaly"))
    print("  M4 ML Fault Class:", probe_result["m4_ml_prediction"].get("fault_type"))
    print("  M4 ML Confidence:", probe_result["m4_ml_prediction"].get("confidence"))
    print("  M4 ML Top Features:", probe_result["m4_ml_prediction"].get("top_features"))

    print("\n3. Testing 10-second Live Tick Loop with Overheating Injection...")
    orch.load_scenario("cht_overheating")

    def _telemetry_cb(frame: TelemetryFrame) -> None:
        if frame.composite_score > 0.03 or frame.ml_anomaly:
            print(
                f"  [TICK t={frame.timestamp:4.1f}s] "
                f"RPM={frame.rpm:4.0f} CHT={frame.cht:5.1f}C OilP={frame.oil_pressure:4.1f}psi "
                f"HI={frame.health_index:5.1f}% Sev={frame.severity_level:<12s} "
                f"ML Anomaly={frame.ml_anomaly} Class={frame.ml_fault_type} Conf={frame.ml_confidence:.2f}"
            )

    orch.subscribe(_telemetry_cb)
    orch.start(duration_s=8.0, blocking=True)

    status = orch.get_status()
    print("\n4. Run Complete. Final Orchestrator Status:")
    for k, v in status.items():
        print(f"  {k:<24}: {v}")

    print("\nEnd-to-End Test Passed Successfully.")
