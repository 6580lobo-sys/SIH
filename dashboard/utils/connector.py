"""
utils/connector.py
==================
Pluggable data-source connector for the Digital Twin Dashboard.

DAY 2 INTEGRATION: Now supports 5 methods (3 from M1 + RUL + classification):
    next_tick()            -> per-tick residual payload  (§1A)
    get_signature()        -> fault signature            (§1B) or None
    get_raw()              -> (predicted, actual)         (§1C)
    get_rul(score)         -> RUL estimate               (§2A) or None
    get_classification(sig)-> fault classification        (§4A) or None

Three source implementations:
    MockSource    - wraps MockEngine + MockRULEstimator + MockClassifier (dev/demo)
    LiveSource    - try-imports twin_core; falls back to MockSource if unavailable
    ReplaySource  - try-imports CsvReplaySource; falls back to MockSource if unavailable

Usage:
    from utils.connector import get_engine, FAULT_TYPES

    engine = get_engine(mode="Live")
    tick   = engine.next_tick()
    sig    = engine.get_signature()
    pred, actual = engine.get_raw()
    rul    = engine.get_rul(tick["composite_score"])
    cls    = engine.get_classification(sig)

    engine.inject_fault("overheating")
    engine.clear_fault()

Day 2 integration:
    When M1's twin_core is on sys.path, LiveSource auto-activates.
    When M2/M3's RUL module is available, swap MockRULEstimator.
    When M4's classifier is available, swap MockClassifier.
    No page code changes needed — the factory handles the switch.
"""

from __future__ import annotations

import os
import sys
import logging
from typing import Optional, Protocol, runtime_checkable

# Ensure M1 (twin_core), M2, and M3 are on sys.path
_DASH_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ROOT_DIR = os.path.dirname(_DASH_DIR)
for _p in [
    os.path.join(_ROOT_DIR, "M1", "src"),
    os.path.join(_ROOT_DIR, "M2"),
    os.path.join(_ROOT_DIR, "M3"),
    os.path.join(_ROOT_DIR, "M4"),
]:
    if os.path.exists(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

from utils.mock_data import MockEngine, FAULT_TYPES  # noqa: F401 (re-export)
from utils.mock_rul import MockRULEstimator
from utils.mock_classification import MockClassifier

log = logging.getLogger(__name__)


# ── Protocol (interface contract) ─────────────────────────────────────────────

@runtime_checkable
class EngineSource(Protocol):
    """
    Protocol matching the full 5-method API consumed by dashboard pages.
    Any data source must implement these methods.
    """

    def next_tick(self) -> dict:
        """Return a per-tick residual payload (data contract §1A)."""
        ...

    def get_signature(self) -> Optional[dict]:
        """Return a signature payload (§1B) or None."""
        ...

    def get_raw(self) -> tuple[dict, dict]:
        """Return (predicted_dict, actual_dict) - §1C, 10 fields each."""
        ...

    def get_rul(self, composite_score: float) -> Optional[dict]:
        """Return a §2A RUL estimate dict, or None."""
        ...

    def get_classification(self, signature: Optional[dict]) -> Optional[dict]:
        """Return a §4A fault classification dict, or None."""
        ...

    def inject_fault(self, fault_type: str) -> None:
        """Inject a named fault into the actual-value stream."""
        ...

    def clear_fault(self) -> None:
        """Clear any active fault, return to healthy baseline."""
        ...

    @property
    def active_fault(self) -> Optional[str]:
        """Return the currently active fault type, or None."""
        ...

    @property
    def tick_count(self) -> int:
        """Return total ticks emitted so far."""
        ...

    @property
    def using_real_m1(self) -> bool:
        """True if connected to M1's real twin_core, False if using mocks."""
        ...


# ── MockSource (wraps MockEngine + MockRUL + MockClassifier) ─────────────────

class MockSource:
    """
    Development / demo source. Wraps all mock modules with the EngineSource protocol.
    This is what the dashboard uses when twin_core is not available.
    """

    def __init__(self, noise_sigma: float = 0.015, scenario_params: dict = None, **kwargs):
        self._engine = MockEngine(noise_sigma=noise_sigma,
                                  scenario_params=scenario_params, **kwargs)
        self._rul_estimator = MockRULEstimator()
        self._classifier = MockClassifier()

    def next_tick(self) -> dict:
        return self._engine.next_tick()

    def get_signature(self) -> Optional[dict]:
        return self._engine.get_signature()

    def get_raw(self) -> tuple[dict, dict]:
        return self._engine.get_raw()

    def get_rul(self, composite_score: float) -> Optional[dict]:
        return self._rul_estimator.estimate(composite_score)

    def get_classification(self, signature: Optional[dict]) -> Optional[dict]:
        return self._classifier.classify(
            signature=signature,
            active_fault=self._engine.active_fault,
        )

    def inject_fault(self, fault_type: str) -> None:
        self._engine.inject_fault(fault_type)

    def clear_fault(self) -> None:
        self._engine.clear_fault()
        self._classifier.reset()
        self._rul_estimator.reset()

    @property
    def active_fault(self) -> Optional[str]:
        return self._engine.active_fault

    @property
    def tick_count(self) -> int:
        return self._engine.tick_count

    @property
    def using_real_m1(self) -> bool:
        return False


# ── LiveSource (M1 DigitalTwin + ResidualEngine) ────────────────────────────

_TWIN_CORE_AVAILABLE = False
try:
    from twin_core.twin import DigitalTwin          # type: ignore
    from twin_core.dynamics import EngineSimulator   # type: ignore
    from twin_core.residual import ResidualEngine    # type: ignore
    from twin_core._dev_fault_stub import FaultedSimulator, FAULT_PROFILES  # type: ignore
    _TWIN_CORE_AVAILABLE = True
    log.info("twin_core found — LiveSource will use real M1 engine.")
except ImportError:
    log.info("twin_core not found — LiveSource will fall back to MockSource.")


class LiveSource:
    """
    Live data source connecting directly to M1's DigitalTwin + ResidualEngine.
    """

    def __init__(self, noise_sigma: float = 0.015, scenario_params: dict = None, **kwargs):
        self._using_real = False
        self._rul_estimator = MockRULEstimator()
        self._classifier = MockClassifier()
        self._tick_count = 0
        self._last_raw: tuple[dict, dict] = ({}, {})
        self._active_fault: Optional[str] = None
        self._ambient_temp = 25.0
        self._throttle = 65.0

        if scenario_params:
            self._ambient_temp = float(scenario_params.get("ambient_temp_c", 25.0))
            self._throttle = float(scenario_params.get("throttle_demand_pct", 65.0))

        if _TWIN_CORE_AVAILABLE:
            try:
                self._actual_sim = EngineSimulator(ambient_temp=self._ambient_temp, seed=99)
                self._twin = DigitalTwin(
                    actual_source=self._actual_sim.step,
                    ambient_temp=self._ambient_temp,
                    ref_seed=42,
                )
                self._residual = ResidualEngine()
                self._using_real = True
                log.info("LiveSource: Real M1 twin_core engine activated.")
            except Exception as e:
                log.warning(f"LiveSource: twin_core init error: {e}. Falling back to MockSource.")
                self._fallback = MockSource(noise_sigma=noise_sigma,
                                            scenario_params=scenario_params, **kwargs)
        else:
            self._fallback = MockSource(noise_sigma=noise_sigma,
                                        scenario_params=scenario_params, **kwargs)

    def next_tick(self) -> dict:
        if self._using_real:
            self._tick_count += 1
            dt = 0.1
            pair = self._twin.step(self._throttle, dt)
            self._last_raw = (pair["predicted"], pair["actual"])
            res = self._residual.update(pair)
            return res
        return self._fallback.next_tick()

    def get_signature(self) -> Optional[dict]:
        if self._using_real:
            return self._residual.signature()
        return self._fallback.get_signature()

    def get_raw(self) -> tuple[dict, dict]:
        if self._using_real:
            return self._last_raw
        return self._fallback.get_raw()

    def get_rul(self, composite_score: float) -> Optional[dict]:
        return self._rul_estimator.estimate(composite_score)

    def get_classification(self, signature: Optional[dict]) -> Optional[dict]:
        return self._classifier.classify(
            signature=signature,
            active_fault=self.active_fault,
        )

    def inject_fault(self, fault_type: str) -> None:
        self._active_fault = fault_type
        if self._using_real:
            if fault_type in FAULT_PROFILES:
                faulted = FaultedSimulator(fault_type=fault_type, fault_time=0.0, seed=99)
                self._twin.set_actual_source(faulted.step)
            else:
                self._actual_sim = EngineSimulator(ambient_temp=self._ambient_temp, seed=99)
                self._twin.set_actual_source(self._actual_sim.step)
        else:
            self._fallback.inject_fault(fault_type)

    def clear_fault(self) -> None:
        self._active_fault = None
        if self._using_real:
            self._actual_sim = EngineSimulator(ambient_temp=self._ambient_temp, seed=99)
            self._twin.set_actual_source(self._actual_sim.step)
            self._residual.reset()
        else:
            self._fallback.clear_fault()
        self._classifier.reset()
        self._rul_estimator.reset()

    @property
    def active_fault(self) -> Optional[str]:
        if self._using_real:
            return self._active_fault
        return self._fallback.active_fault

    @property
    def tick_count(self) -> int:
        if self._using_real:
            return self._tick_count
        return self._fallback.tick_count

    @property
    def using_real_m1(self) -> bool:
        return self._using_real



# ── ReplaySource (try-import CsvReplaySource, fallback to MockSource) ────────

_REPLAY_AVAILABLE = False
try:
    from twin_core.replay import CsvReplaySource  # type: ignore
    _REPLAY_AVAILABLE = True
    log.info("CsvReplaySource found — ReplaySource will use real replay.")
except ImportError:
    log.info("CsvReplaySource not found — ReplaySource will fall back to MockSource.")


class ReplaySource:
    """
    Replay data source for M1's CsvReplaySource reading a mission-log CSV.

    If twin_core.replay is installed, constructs a real CsvReplaySource.
    Otherwise, falls back to MockSource seamlessly.
    """

    def __init__(self, csv_file=None, noise_sigma: float = 0.015,
                 scenario_params: dict = None, **kwargs):
        self._csv_file = csv_file
        self._replay_idx = 0
        self._using_real = False
        self._rul_estimator = MockRULEstimator()
        self._classifier = MockClassifier()

        if _REPLAY_AVAILABLE and csv_file is not None:
            try:
                self._source = CsvReplaySource(csv_file)
                self._using_real = True
                log.info("ReplaySource: Real CsvReplaySource activated.")
            except Exception as e:
                log.warning(f"ReplaySource: CsvReplaySource init failed: {e}. "
                            f"Falling back to MockSource.")
                self._fallback = MockSource(noise_sigma=noise_sigma,
                                            scenario_params=scenario_params, **kwargs)
        else:
            self._fallback = MockSource(noise_sigma=noise_sigma,
                                        scenario_params=scenario_params, **kwargs)

    def next_tick(self) -> dict:
        if self._using_real:
            self._replay_idx += 1
            return self._source.next_tick()
        return self._fallback.next_tick()

    def get_signature(self) -> Optional[dict]:
        if self._using_real:
            return self._source.get_signature()
        return self._fallback.get_signature()

    def get_raw(self) -> tuple[dict, dict]:
        if self._using_real:
            return self._source.get_raw()
        return self._fallback.get_raw()

    def get_rul(self, composite_score: float) -> Optional[dict]:
        return self._rul_estimator.estimate(composite_score)

    def get_classification(self, signature: Optional[dict]) -> Optional[dict]:
        active = None if self._using_real else self._fallback.active_fault
        return self._classifier.classify(
            signature=signature,
            active_fault=active,
        )

    def inject_fault(self, fault_type: str) -> None:
        # Replay sources don't support fault injection
        if not self._using_real:
            self._fallback.inject_fault(fault_type)

    def clear_fault(self) -> None:
        if not self._using_real:
            self._fallback.clear_fault()
        self._classifier.reset()
        self._rul_estimator.reset()

    @property
    def active_fault(self) -> Optional[str]:
        if self._using_real:
            return None
        return self._fallback.active_fault

    @property
    def tick_count(self) -> int:
        if self._using_real:
            return self._replay_idx
        return self._fallback.tick_count

    @property
    def using_real_m1(self) -> bool:
        return self._using_real


# ── Factory ───────────────────────────────────────────────────────────────────

def get_engine(
    mode: str = "Live",
    csv_file=None,
    noise_sigma: float = 0.015,
    scenario_params: dict = None,
    **kwargs,
) -> EngineSource:
    """
    Factory: return the right data source based on the dashboard mode.

    Args:
        mode:            "Live" or "Replay"
        csv_file:        Uploaded CSV file object (for Replay mode)
        noise_sigma:     Noise level for mock source
        scenario_params: Environmental scenario dict for Block E simulation:
                         {altitude_m, ambient_temp_c, throttle_demand_pct}

    Returns:
        An EngineSource-compatible object with all 5 methods.
    """
    if mode == "Replay":
        return ReplaySource(csv_file=csv_file, noise_sigma=noise_sigma,
                            scenario_params=scenario_params, **kwargs)
    else:
        return LiveSource(noise_sigma=noise_sigma,
                          scenario_params=scenario_params, **kwargs)
