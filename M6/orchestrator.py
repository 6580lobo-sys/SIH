"""
orchestrator.py — M6 Simulation Orchestrator
=============================================

Wires M1's physics twin (DigitalTwin + ResidualEngine) with M3's real
telemetry pipeline (TelemetryPublisher / load_replay_csv) and exposes a
clean subscription/API surface for M4 (ML) and M5 (dashboard).

Architecture
------------
                    ┌──────────────────────────────────────┐
                    │           Orchestrator (M6)           │
                    │                                       │
  M3 TelemetryPublisher ──► tick_loop ──► DigitalTwin (M1) │
  (or CSV replay)           │              ResidualEngine   │
                            ▼                               │
                    subscriber callbacks ──► M4 / M5        │
                    get_latest() / get_history(n)           │
                    └──────────────────────────────────────┘

CONTRACT FLAGS — search "# ⚠️ CONTRACT" for all renegotiation points.
"""

from __future__ import annotations

import collections
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Deque, Dict, List, Optional

# ---------------------------------------------------------------------------
# Path setup — make M1 and M3 importable regardless of cwd
# ---------------------------------------------------------------------------

_HERE      = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)          # …/SIH
_M1_SRC    = os.path.join(_REPO_ROOT, "M1", "src")
_M3_SRC    = os.path.join(_REPO_ROOT, "m3_telemetry")

for _p in (_M1_SRC, _M3_SRC):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# M1 imports
from twin_core.twin     import DigitalTwin    # noqa: E402
from twin_core.residual import ResidualEngine  # noqa: E402

# M3 imports
from schema.telemetry_schema import EngineTelemetryMessage   # noqa: E402
from publisher.api           import load_replay_csv           # noqa: E402
from publisher.streaming_harness import TelemetryPublisher   # noqa: E402
from generator.fault_injection import (                       # noqa: E402
    FaultManager,
    FaultScenario,
    MisfireFault,
    OverheatingFault,
    OilPressureDropFault,
    InjectorFault,
    VibrationSpikeFault,
    NoOpFault,
)

# Re-export fault classes so M4/M5 can import them from one place
__all__ = [
    "Orchestrator", "TelemetryFrame", "M1TwinAdapter",
    "MisfireFault", "OverheatingFault", "OilPressureDropFault",
    "InjectorFault", "VibrationSpikeFault", "NoOpFault",
]


# ---------------------------------------------------------------------------
# TelemetryFrame
# ---------------------------------------------------------------------------

@dataclass
class TelemetryFrame:
    """One processed tick: raw M3 telemetry + M1 residual engine output.

    Field names and units match M3's EngineTelemetryMessage exactly.
    Residuals are added as an extension dict (EWMA-normalised, signed,
    range-normalised per M1's NOMINAL_RANGE).

    Units
    -----
    timestamp           float   seconds from simulation start
    msg_id              str     CAN message identifier
    rpm                 float   rev/min
    cht                 float   °C   (Cylinder Head Temp)
    egt                 float   °C   (Exhaust Gas Temp)
    oil_pressure        float   PSI
    oil_temp            float   °C
    fuel_flow           float   L/hr
    vibration_amplitude float   g
    vibration_freq      float   Hz
    throttle_cmd        float   0–100 %
    residuals           dict    {channel: float} — EWMA residual per channel
    composite_score     float   RMS anomaly score (0 = healthy)
    fault_label         str     ground-truth tag from M3 ("healthy" / fault names)
    """

    # M3 fields (mirror EngineTelemetryMessage)
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

    # M1 residual outputs
    residuals:       Dict[str, float] = field(default_factory=dict)
    composite_score: float = 0.0

    # Out-of-band ground-truth label (not in CAN schema)
    fault_label: str = "healthy"

    @classmethod
    def from_m3(
        cls,
        msg: EngineTelemetryMessage,
        residual_output: dict,
        fault_label: str = "healthy",
    ) -> "TelemetryFrame":
        """Assemble a frame from an M3 message and M1's residual output dict."""
        return cls(
            timestamp=msg.timestamp,
            msg_id=msg.msg_id,
            rpm=msg.rpm,
            cht=msg.cht,
            egt=msg.egt,
            oil_pressure=msg.oil_pressure,
            oil_temp=msg.oil_temp,
            fuel_flow=msg.fuel_flow,
            vibration_amplitude=msg.vibration_amplitude,
            vibration_freq=msg.vibration_freq,
            throttle_cmd=msg.throttle_cmd,
            residuals=residual_output.get("residuals", {}),
            composite_score=residual_output.get("composite_score", 0.0),
            fault_label=fault_label,
        )

    def as_dict(self) -> dict:
        """Flat dict for M4 feature extraction / M5 plotting.

        Residuals are flattened as ``residual_<channel>``.
        """
        d = {
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
            "composite_score":     self.composite_score,
            "fault_label":         self.fault_label,
        }
        for ch, val in self.residuals.items():
            d[f"residual_{ch}"] = val
        return d


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

    M1 interface summary (extracted from twin.py / residual.py):
    ─────────────────────────────────────────────────────────────
    DigitalTwin.__init__(actual_source, ambient_temp, ref_seed, actual_seed)
    DigitalTwin.step(throttle_cmd: float, dt: float)
        → {"predicted": dict, "actual": dict}
        Inner dicts schema:
            timestamp, rpm, cht, egt, oil_pressure, oil_temp,
            fuel_flow, vibration_amplitude, vibration_freq, throttle_cmd
        Units: rpm=RPM, cht/egt/oil_temp=°C, oil_pressure=PSI,
               fuel_flow=L/hr, vibration_amplitude=g, vibration_freq=Hz

    ResidualEngine.update(pair: dict)
        → {"timestamp": float, "residuals": {ch: float}, "composite_score": float}
    ResidualEngine.signature(threshold=0.03)
        → {"feature_vector", "dominant_channels", "severity", "fault_detected"}
    ResidualEngine.reset()
        → resets EWMA state to zero

    # ⚠️ CONTRACT (M1 — DigitalTwin):
    #   step() takes (throttle_cmd, dt) and internally calls actual_source()
    #   to get the "actual" reading.  For live M3 integration we need to
    #   inject each arriving M3 frame into that "actual" slot.  We do this
    #   via a shared variable updated before each twin.step() call.
    #   Renegotiate: DigitalTwin.step() should accept an optional
    #   actual_override dict so the bridge variable hack isn't needed.
    #
    # ⚠️ CONTRACT (M1 — DigitalTwin):
    #   No reset() method exists on DigitalTwin.  After stop()/reset()
    #   the reference EngineSimulator's internal state (time, temperatures)
    #   carries over into the next run.
    #   Renegotiate: add DigitalTwin.reset() that re-creates the reference
    #   EngineSimulator at t=0 idle conditions.
    """

    def __init__(
        self,
        ambient_temp: float = 25.0,
        ref_seed: int = 42,
        ewma_alpha: float = 0.10,
    ) -> None:
        self._latest_m3_actual: Optional[dict] = None

        self._twin = DigitalTwin(
            actual_source=self._m3_bridge,
            ambient_temp=ambient_temp,
            ref_seed=ref_seed,
        )
        self._residual_eng = ResidualEngine(ewma_alpha=ewma_alpha)

    # ── Internal bridge ─────────────────────────────────────────────────

    def _m3_bridge(self, throttle_cmd: float, dt: float) -> dict:
        """Bridge callable: returns the most recent M3 frame as a dict.

        throttle_cmd and dt are accepted for M1's API compatibility but
        ignored — the actual readings come from M3's telemetry.

        # ⚠️ CONTRACT (M1/M3): This is the same pattern as M1's own
        # _dev_fault_stub.CsvReplaySource.step() — both ignore the args.
        # This is acceptable as a handshake convention.
        """
        return self._latest_m3_actual if self._latest_m3_actual else _IDLE_ACTUAL

    @staticmethod
    def _msg_to_m1_dict(msg: EngineTelemetryMessage) -> dict:
        """Map M3's Pydantic model to the dict shape M1's schema expects.

        Field mapping (M3 → M1): all field names match 1-to-1 ✅
        The only extra field in M3 is msg_id which M1 ignores.

        # ⚠️ CONTRACT (M1/M3 — vibration_amplitude SCALE MISMATCH):
        #   M1's NOMINAL_RANGE["vibration_amplitude"] = 0.05  (span in g)
        #   M3's EngineTelemetryMessage.vibration_amplitude  = 0–50 g
        #   Result: residuals for this channel are ~20-80x too large,
        #   dominating the composite_score even on healthy data.
        #   Smoke test confirmed: vibration residuals of 3+ even before fault.
        #
        #   Renegotiate: M1 must update NOMINAL_RANGE["vibration_amplitude"]
        #   to match M3's actual operating span (~2–5 g), OR M3 must rescale
        #   its vibration output to the 0–0.05 g range M1 was built for.
        #   Until fixed, treat vibration residuals as unreliable.
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

    # ── Public API ──────────────────────────────────────────────────────

    def step(self, msg: EngineTelemetryMessage, dt: float) -> dict:
        """Advance M1 one tick using an M3 frame as the 'actual' reading.

        Returns ResidualEngine.update() output dict.
        """
        self._latest_m3_actual = self._msg_to_m1_dict(msg)
        pair = self._twin.step(msg.throttle_cmd, dt)
        return self._residual_eng.update(pair)

    def signature(self, threshold: float = 0.03) -> dict:
        """Current residual signature — M3's classifier (M4) primary input."""
        return self._residual_eng.signature(threshold=threshold)

    def reset(self) -> None:
        """Reset EWMA state and clear the cached M3 actual."""
        self._residual_eng.reset()
        self._latest_m3_actual = None


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

SubscriberCallback = Callable[[TelemetryFrame], None]


class Orchestrator:
    """Central coordinator for the UAV engine digital twin system (M6).

    Responsibilities
    ----------------
    * Pulls frames from M3 (live TelemetryPublisher or CSV replay).
    * Ticks M1's physics twin + residual engine on each frame.
    * Pushes TelemetryFrame to all registered subscriber callbacks
      (M4 for ML, M5 for dashboard).
    * Maintains a rolling history buffer and latest-frame cache.
    * Exposes start/stop/reset/get_latest/get_history/get_status.

    Parameters
    ----------
    twin_adapter : M1TwinAdapter | None
        Pre-configured M1 adapter.  A default one is created if None.
    rate_hz : float
        Target tick rate for live streaming (default 10 Hz).
    history_maxlen : int
        Maximum TelemetryFrames kept in the rolling buffer.
    environment : str
        M3 environment preset: "standard_day" | "hot_day" | "high_altitude".
    throttle_mode : str
        M3 throttle profile: "smooth" | "idle_only" | "takeoff" | etc.
    """

    def __init__(
        self,
        twin_adapter: Optional[M1TwinAdapter] = None,
        rate_hz: float = 10.0,
        history_maxlen: int = 1000,
        environment: str = "standard_day",
        throttle_mode: str = "smooth",
    ) -> None:
        self._adapter       = twin_adapter or M1TwinAdapter()
        self._rate_hz       = rate_hz
        self._environment   = environment
        self._throttle_mode = throttle_mode

        self._fault_manager  = FaultManager()
        self._subscribers:  List[SubscriberCallback] = []
        self._history: Deque[TelemetryFrame] = collections.deque(maxlen=history_maxlen)
        self._latest: Optional[TelemetryFrame] = None

        self._running    = False
        self._thread: Optional[threading.Thread] = None
        self._tick_count = 0
        self._start_wall: Optional[float] = None
        self._lock = threading.Lock()

    # ── Subscriber management ────────────────────────────────────────────

    def subscribe(self, callback: SubscriberCallback) -> None:
        """Register a callback to receive every TelemetryFrame.

        Signature: ``(frame: TelemetryFrame) -> None``
        M4 and M5 call this during their init.
        """
        with self._lock:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: SubscriberCallback) -> None:
        """Remove a previously registered callback."""
        with self._lock:
            try:
                self._subscribers.remove(callback)
            except ValueError:
                pass

    # ── Fault management ─────────────────────────────────────────────────

    def inject_fault(self, scenario: FaultScenario) -> None:
        """Register a fault scenario (delegates to M3's FaultManager.add()).

        Available scenarios (import from this module):
            MisfireFault(severity, start_time_s, duration_s)
            OverheatingFault(severity, start_time_s, duration_s)
            OilPressureDropFault(severity, mode, start_time_s, duration_s)
            InjectorFault(severity, start_time_s, duration_s)
            VibrationSpikeFault(pattern, severity, start_time_s, duration_s)
            NoOpFault(start_time_s, duration_s)

        severity: 0.0 (mild) → 1.0 (severe)
        mode (OilPressureDropFault): "sudden" | "gradual"
        pattern (VibrationSpikeFault): "intermittent" | "sustained"
        """
        self._fault_manager.add(scenario)

    def clear_faults(self) -> None:
        """Remove all registered fault scenarios.

        # ⚠️ CONTRACT (M3 — FaultManager):
        #   clear() removes all scenarios but there is no reset_clock().
        #   If you re-use the same Orchestrator for a second run, you must
        #   re-inject faults from t=0.  The scenario start_time_s values
        #   are absolute from simulation start, not from last reset().
        #   Renegotiate with M3: add FaultManager.reset_time(offset) or
        #   shift scenario timings automatically on Orchestrator.reset().
        """
        self._fault_manager.clear()

    # ── Lifecycle ────────────────────────────────────────────────────────

    def start(
        self,
        duration_s: Optional[float] = None,
        replay_csv: Optional[str] = None,
        blocking: bool = False,
    ) -> None:
        """Start the orchestrator tick loop.

        Parameters
        ----------
        duration_s : float | None
            How long to run.  None = run until stop() is called.
        replay_csv : str | None
            Path to a pre-recorded M3 CSV.  When set, runs replay mode
            (as-fast-as-possible) instead of live streaming.
        blocking : bool
            True = block calling thread.  False (default) = background thread.
        """
        if self._running:
            raise RuntimeError("Orchestrator already running — call stop() first.")

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
        """Signal the tick loop to stop and wait for the thread to exit."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        self._thread = None

    def reset(self) -> None:
        """Stop, clear history, and reset M1's residual EWMA state."""
        self.stop()
        with self._lock:
            self._history.clear()
            self._latest     = None
            self._tick_count = 0
            self._start_wall = None
        self._adapter.reset()

    # ── Data access ──────────────────────────────────────────────────────

    def get_latest(self) -> Optional[TelemetryFrame]:
        """Most recent TelemetryFrame, or None if not started."""
        with self._lock:
            return self._latest

    def get_history(self, n: int = 100) -> List[TelemetryFrame]:
        """Last *n* TelemetryFrames, oldest first."""
        with self._lock:
            frames = list(self._history)
        return frames[-n:] if n < len(frames) else frames

    def get_status(self) -> dict:
        """Snapshot of orchestrator health for M6 monitoring / API."""
        latest = self.get_latest()
        wall   = (
            time.perf_counter() - self._start_wall
            if self._start_wall else 0.0
        )
        return {
            "running":          self._running,
            "tick_count":       self._tick_count,
            "wall_time_s":      round(wall, 3),
            "achieved_rate_hz": round(self._tick_count / wall, 2) if wall > 0 else 0.0,
            "latest_timestamp": latest.timestamp if latest else None,
            "composite_score":  latest.composite_score if latest else None,
            "fault_label":      latest.fault_label if latest else None,
            "subscriber_count": len(self._subscribers),
            "history_len":      len(self._history),
            "active_faults": [
                s.name
                for s in self._fault_manager.active_scenarios(
                    latest.timestamp if latest else 0.0
                )
            ],
        }

    # ── Internal helpers ──────────────────────────────────────────────────

    def _process_frame(
        self,
        msg: EngineTelemetryMessage,
        fault_label: str,
        dt: float,
    ) -> TelemetryFrame:
        """Tick M1, assemble TelemetryFrame, notify subscribers."""
        residual_out = self._adapter.step(msg, dt)
        frame = TelemetryFrame.from_m3(msg, residual_out, fault_label)

        with self._lock:
            self._latest = frame
            self._history.append(frame)
            self._tick_count += 1
            callbacks = list(self._subscribers)

        # Dispatch outside the lock so subscribers can call get_latest() etc.
        for cb in callbacks:
            try:
                cb(frame)
            except Exception as exc:
                print(f"[orchestrator] subscriber raised: {exc}", file=sys.stderr)

        return frame

    # ── Tick loops ───────────────────────────────────────────────────────

    def _run_live_loop(self, duration_s: Optional[float] = None) -> None:
        """Live streaming: pull frames from M3's TelemetryPublisher.

        M3 interface used:
            TelemetryPublisher(rate_hz, publish_cb, fault_manager,
                               environment_name, throttle_mode)
            publish_cb signature: (msg: EngineTelemetryMessage, fault_label: str) -> None
            TelemetryPublisher.run(duration_s) — blocking, pace-controlled loop

        # ⚠️ CONTRACT (M3 — TelemetryPublisher):
        #   run() is a blocking call; there is no step-at-a-time API.
        #   We run it in the orchestrator's background thread, which is fine,
        #   but means we cannot pause mid-stream without killing the thread.
        #   Renegotiate with M3: expose a generator / coroutine version of
        #   run() so M6 owns the tick loop instead of M3.
        """
        prev_ts: Optional[float] = None
        default_dt = 1.0 / self._rate_hz

        def _cb(msg: EngineTelemetryMessage, fault_label: str) -> None:
            nonlocal prev_ts
            if not self._running:
                return
            dt = (msg.timestamp - prev_ts) if prev_ts is not None else default_dt
            prev_ts = msg.timestamp
            self._process_frame(msg, fault_label, max(dt, 1e-6))

        publisher = TelemetryPublisher(
            rate_hz=self._rate_hz,
            publish_cb=_cb,
            fault_manager=self._fault_manager,
            environment_name=self._environment,
            throttle_mode=self._throttle_mode,
        )
        publisher.run(duration_s=duration_s if duration_s is not None else 86400.0)
        self._running = False

    def _run_replay_loop(
        self,
        csv_path: str,
        duration_s: Optional[float] = None,
    ) -> None:
        """Replay mode: iterate frames from a saved M3 CSV.

        M3 interface used:
            load_replay_csv(path: str) -> Iterator[EngineTelemetryMessage]
            Strips the "active_faults" column during loading.

        # ⚠️ CONTRACT (M3 — load_replay_csv):
        #   The fault_label (active_faults column) is stripped during CSV
        #   loading — all replayed frames arrive with fault_label="healthy".
        #   This means M4 cannot use replayed data for labelled training
        #   without M3 updating load_replay_csv() to yield (msg, label) tuples.
        #   Renegotiate with M3: return a tuple or named pair so the label
        #   survives replay.
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

            # ⚠️ fault_label lost in replay — see CONTRACT note above
            self._process_frame(msg, fault_label="healthy", dt=max(dt, 1e-6))

        self._running = False


# ---------------------------------------------------------------------------
# __main__ — runnable end-to-end integration smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    print("=" * 70)
    print("M6 Orchestrator — End-to-End Integration Smoke Test")
    print("Wiring: M1 (DigitalTwin + ResidualEngine) + M3 (TelemetryPublisher)")
    print("=" * 70)

    # ── Build M1 adapter and Orchestrator ───────────────────────────────
    adapter = M1TwinAdapter(ambient_temp=25.0, ref_seed=42, ewma_alpha=0.10)
    orch = Orchestrator(
        twin_adapter=adapter,
        rate_hz=10.0,
        history_maxlen=500,
        environment="standard_day",
        throttle_mode="smooth",
    )

    # ── Inject an overheating fault at t=5s ─────────────────────────────
    orch.inject_fault(
        OverheatingFault(severity=0.8, start_time_s=5.0, duration_s=20.0)
    )

    # ── M4 subscriber stub (anomaly detector) ───────────────────────────
    def m4_callback(frame: TelemetryFrame) -> None:
        """Receives every frame — simulates M4 anomaly detection input."""
        if frame.composite_score > 0.03:
            sig  = adapter.signature()
            top  = sig["dominant_channels"][:2]
            tops = ", ".join(f"{ch}={v:+.4f}" for ch, v in top)
            print(
                f"  [M4] t={frame.timestamp:5.1f}s  "
                f"score={frame.composite_score:.4f}  "
                f"label={frame.fault_label!r:20s}  "
                f"dominant=[{tops}]"
            )

    # ── M5 subscriber stub (dashboard) ──────────────────────────────────
    _tick = [0]

    def m5_callback(frame: TelemetryFrame) -> None:
        """Receives every frame — simulates M5 dashboard update."""
        _tick[0] += 1
        if _tick[0] % 20 == 0:    # print every 2 s at 10 Hz
            health = max(0.0, 100.0 - frame.composite_score * 1000)
            print(
                f"  [M5] t={frame.timestamp:5.1f}s  "
                f"RPM={frame.rpm:6.0f}  "
                f"CHT={frame.cht:5.1f}C  "
                f"EGT={frame.egt:5.1f}C  "
                f"OilP={frame.oil_pressure:5.1f}psi  "
                f"health~{health:5.1f}"  # '~' avoids cp1252 encoding error on Windows
            )

    orch.subscribe(m4_callback)
    orch.subscribe(m5_callback)

    # ── Run live for 30 s ───────────────────────────────────────────────
    print("\n[orch] Live run: 30 s  |  overheating fault activates at t=5 s\n")
    orch.start(duration_s=30.0, blocking=True)

    # ── Status report ────────────────────────────────────────────────────
    status = orch.get_status()
    print("\n" + "=" * 70)
    print("Run complete — orchestrator status:")
    for k, v in status.items():
        print(f"  {k:<22}: {v}")

    # ── Final M1 residual signature (for M4's classifier) ───────────────
    sig = adapter.signature()
    print(f"\nFinal M1 residual signature:")
    print(f"  severity       : {sig['severity']:.6f}")
    print(f"  fault_detected : {sig['fault_detected']}")
    print(f"  dominant       : {sig['dominant_channels'][:3]}")

    # ── Replay smoke test ────────────────────────────────────────────────
    _replay = os.path.join(
        _REPO_ROOT, "m3_telemetry", "data", "replay_library",
        "fault_overheating_standard.csv",
    )
    if os.path.exists(_replay):
        print(f"\n[orch] Replay mode — {os.path.basename(_replay)}")
        orch.reset()
        _tick[0] = 0
        orch.start(replay_csv=_replay, blocking=True)
        print(f"[orch] Replayed {orch.get_status()['tick_count']} frames")
        latest = orch.get_latest()
        if latest:
            print(f"[orch] Final composite_score = {latest.composite_score:.6f}")
    else:
        print(f"\n[orch] Replay CSV not found — skipping replay test.")
        print(f"       Expected: m3_telemetry/data/replay_library/")

    print("\nDone.")
