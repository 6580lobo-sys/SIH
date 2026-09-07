"""Fault injection framework for the aero piston-engine telemetry generator.

This module provides the *structural* plumbing for injecting faults into
healthy telemetry streams, plus concrete fault implementations.

Key classes
-----------
FaultScenario
    Abstract base – every concrete fault inherits from this.
NoOpFault
    Dummy scenario that returns values unchanged (integration test).
MisfireFault
    Periodic RPM dips and vibration spikes simulating spark/coil failure.
FaultManager
    Owns a list of ``FaultScenario`` objects, applies active ones in
    sequence, and collects ground-truth ``fault_label`` tags.
"""

from __future__ import annotations

import copy
import math
from abc import ABC, abstractmethod
from typing import Optional

import numpy as np


# ── Base class ──────────────────────────────────────────────────────────────


class FaultScenario(ABC):
    """Base class for every injectable fault.

    Parameters
    ----------
    name : str
        Human-readable identifier used as the ground-truth label
        (e.g. ``"oil_leak"``, ``"sensor_drift"``).
    start_time_s : float
        Simulation time (seconds from t=0) at which the fault activates.
    duration_s : float | None
        How long the fault stays active.  ``None`` means "until the end
        of the simulation".
    """

    def __init__(
        self,
        name: str,
        start_time_s: float = 0.0,
        duration_s: Optional[float] = None,
    ) -> None:
        if start_time_s < 0:
            raise ValueError(f"start_time_s must be >= 0, got {start_time_s}")
        if duration_s is not None and duration_s <= 0:
            raise ValueError(f"duration_s must be > 0 or None, got {duration_s}")

        self.name = name
        self.start_time_s = start_time_s
        self.duration_s = duration_s

    # ── helpers ─────────────────────────────────────────────────────────

    def is_active(self, t_s: float) -> bool:
        """Return ``True`` if the fault should be applied at time *t_s*.

        The fault is active when ``start_time_s <= t_s`` and either
        ``duration_s is None`` (active until end) or the elapsed time
        since activation is still within the duration window.
        """
        if t_s < self.start_time_s:
            return False
        if self.duration_s is None:
            return True
        return t_s < (self.start_time_s + self.duration_s)

    @property
    def end_time_s(self) -> Optional[float]:
        """Return the wall-clock time the fault deactivates, or ``None``."""
        if self.duration_s is None:
            return None
        return self.start_time_s + self.duration_s

    def elapsed_since_start(self, t_s: float) -> float:
        """Seconds elapsed since the fault activated (clamped to >= 0)."""
        return max(0.0, t_s - self.start_time_s)

    # ── abstract interface ──────────────────────────────────────────────

    @abstractmethod
    def apply(self, t_s: float, healthy_values: dict[str, float]) -> dict[str, float]:
        """Apply the fault effect and return a *modified copy* of the values.

        Parameters
        ----------
        t_s : float
            Current simulation time in seconds.
        healthy_values : dict[str, float]
            Sensor readings produced by ``signal_models.healthy_sample()``.

        Returns
        -------
        dict[str, float]
            A new dict with the fault effect applied.  Implementations
            **must not** mutate *healthy_values* in-place.
        """
        ...  # pragma: no cover

    # ── dunder helpers ──────────────────────────────────────────────────

    def __repr__(self) -> str:
        dur = f"{self.duration_s:.1f}s" if self.duration_s is not None else "∞"
        return (
            f"{self.__class__.__name__}("
            f"name={self.name!r}, "
            f"window=[{self.start_time_s:.1f}s, +{dur}])"
        )


# ── No-op proof-of-concept ─────────────────────────────────────────────────


class NoOpFault(FaultScenario):
    """Dummy fault that passes values through unchanged.

    Useful for integration testing the fault-injection pipeline without
    actually modifying any sensor readings.
    """

    def __init__(
        self,
        start_time_s: float = 0.0,
        duration_s: Optional[float] = None,
    ) -> None:
        super().__init__(
            name="noop",
            start_time_s=start_time_s,
            duration_s=duration_s,
        )

    def apply(self, t_s: float, healthy_values: dict[str, float]) -> dict[str, float]:
        """Return *healthy_values* unchanged (deep-copied for safety)."""
        return copy.deepcopy(healthy_values)


# ── Misfire fault ───────────────────────────────────────────────────────────


class MisfireFault(FaultScenario):
    """Simulate intermittent engine misfires (spark plug / ignition coil).

    The fault produces **periodic RPM dips** with correlated vibration
    spikes.  Between dips the engine runs normally.

    Parameters
    ----------
    severity : float
        0.0 = barely noticeable, 1.0 = severe.  Controls:
        - *dip depth*: RPM drops by ``10 + 15 * severity`` percent.
        - *dip duration*: 100–200 ms window scales with severity.
        - *dip frequency*: interval between events shrinks with severity
          (1.5 s at sev=0 → 0.5 s at sev=1).
        - *vibration spike*: amplitude of the g-force bump.
    start_time_s, duration_s
        Time window (inherited from :class:`FaultScenario`).
    seed : int | None
        RNG seed for reproducible event schedules.
    """

    def __init__(
        self,
        severity: float = 0.5,
        start_time_s: float = 0.0,
        duration_s: Optional[float] = None,
        seed: Optional[int] = None,
    ) -> None:
        if not 0.0 <= severity <= 1.0:
            import warnings
            clamped = max(0.0, min(1.0, severity))
            warnings.warn(f"severity {severity} out of bounds, clamped to {clamped}")
            severity = clamped

        super().__init__(
            name="misfire",
            start_time_s=start_time_s,
            duration_s=duration_s,
        )
        self.severity = severity
        self._rng = np.random.default_rng(seed)

        # Pre-compute a schedule of misfire events covering the full
        # duration (or a generous 600 s default if duration is None).
        span = duration_s if duration_s is not None else 600.0
        self._events = self._build_schedule(span)

    # ── schedule construction ───────────────────────────────────────────

    def _build_schedule(
        self, span_s: float
    ) -> list[tuple[float, float, float, float]]:
        """Return a list of ``(event_start, event_dur, rpm_drop_frac, vib_spike)``."""
        events: list[tuple[float, float, float, float]] = []

        # Interval between misfire events (centre of the random range)
        #   severity=0 → ~1.5 s,  severity=1 → ~0.5 s
        mean_interval = 1.5 - 1.0 * self.severity
        # Dip duration range (seconds)
        dip_lo = 0.10 + 0.05 * self.severity   # 0.10 – 0.15
        dip_hi = 0.15 + 0.05 * self.severity   # 0.15 – 0.20
        # RPM drop fraction
        drop_lo = 0.10 + 0.10 * self.severity  # 10 – 20 %
        drop_hi = 0.15 + 0.10 * self.severity  # 15 – 25 %
        # Vibration spike (g)
        vib_lo = 0.5 + 1.0 * self.severity     # 0.5 – 1.5 g
        vib_hi = 1.0 + 1.5 * self.severity     # 1.0 – 2.5 g

        cursor = self._rng.uniform(0.0, mean_interval)  # stagger first event
        while cursor < span_s:
            dur = float(self._rng.uniform(dip_lo, dip_hi))
            drop = float(self._rng.uniform(drop_lo, drop_hi))
            vib = float(self._rng.uniform(vib_lo, vib_hi))
            events.append((cursor, dur, drop, vib))
            cursor += float(self._rng.uniform(
                mean_interval * 0.6, mean_interval * 1.4
            ))

        return events

    # ── core apply ──────────────────────────────────────────────────────

    def apply(self, t_s: float, healthy_values: dict[str, float]) -> dict[str, float]:
        """Modify ``rpm`` and ``vibration_g`` if *t_s* falls inside a dip.

        All other channels are returned untouched.
        """
        values = copy.deepcopy(healthy_values)
        elapsed = self.elapsed_since_start(t_s)

        for ev_start, ev_dur, rpm_drop_frac, vib_spike in self._events:
            if ev_start <= elapsed < ev_start + ev_dur:
                # Smooth dip shape: half-sine pulse within the dip window
                phase = (elapsed - ev_start) / ev_dur          # 0 → 1
                pulse = math.sin(math.pi * phase)              # 0 → 1 → 0

                values["rpm"] *= (1.0 - rpm_drop_frac * pulse)
                values["vibration_g"] += vib_spike * pulse
                break  # only one event can be active at a time

        return values


# ── Overheating fault ───────────────────────────────────────────────────────


class OverheatingFault(FaultScenario):
    """Simulate gradual engine overheating (e.g. blocked cooling fins, low coolant).

    Temperatures ramp **exponentially** from their healthy baseline toward
    a critical overshoot ceiling.  The curve follows
    ``delta(t) = max_delta * (1 - exp(-t / tau))`` where *tau* is chosen
    so that ~95 % of the overshoot is reached by the end of
    ``duration_s``.

    Parameters
    ----------
    severity : float
        0.0 = barely warm, 1.0 = severe.  Controls peak overshoot:

        ======  ==================  ==================  ================
        Channel  severity=0 max     severity=1 max      unit
        ======  ==================  ==================  ================
        CHT     +20 deg C            +80 deg C           deg C
        EGT     +30 deg C            +120 deg C          deg C
        oil_temp +5 deg C            +25 deg C           deg C
        ======  ==================  ==================  ================

    start_time_s, duration_s
        Time window (inherited from :class:`FaultScenario`).
        ``duration_s`` **must** be provided (not ``None``) so the
        exponential time-constant can be computed.
    seed : int | None
        RNG seed for small per-sample noise jitter.
    """

    def __init__(
        self,
        severity: float = 0.5,
        start_time_s: float = 0.0,
        duration_s: float = 10.0,
        seed: int | None = None,
    ) -> None:
        if not 0.0 <= severity <= 1.0:
            import warnings
            clamped = max(0.0, min(1.0, severity))
            warnings.warn(f"severity {severity} out of bounds, clamped to {clamped}")
            severity = clamped
        if duration_s is None or duration_s <= 0:
            raise ValueError(
                "OverheatingFault requires a positive duration_s "
                f"(got {duration_s})"
            )

        super().__init__(
            name="overheating",
            start_time_s=start_time_s,
            duration_s=duration_s,
        )
        self.severity = severity
        self._rng = np.random.default_rng(seed)

        # Peak overshoot values (linearly scaled by severity)
        self._cht_max = 20.0 + 60.0 * severity    # +20 .. +80 deg C
        self._egt_max = 30.0 + 90.0 * severity    # +30 .. +120 deg C
        self._oil_max = 5.0 + 20.0 * severity     # +5  .. +25 deg C

        # Time constant: pick tau so that 95 % of max is reached at
        # t = duration_s  →  1 - e^(-T/tau) = 0.95  →  tau = T / 3
        self._tau_heat = duration_s / 3.0
        
        # Cooling is typically slower than heating due to thermal mass
        self._tau_cool = self._tau_heat * 1.5
        
        # Keep the fault active after duration_s to simulate the cooldown
        # (5 time constants gets us back to ~99% of baseline)
        self._cooldown_tail_s = self._tau_cool * 5.0

    # ── helpers ─────────────────────────────────────────────────────────

    def is_active(self, t_s: float) -> bool:
        """Override to keep the fault alive during the cooldown phase."""
        if t_s < self.start_time_s:
            return False
        if self.duration_s is None:
            return True
        return t_s < (self.start_time_s + self.duration_s + self._cooldown_tail_s)

    def _ramp(self, elapsed_s: float, max_delta: float) -> float:
        """Exponential approach during heating, exponential decay during cooling."""
        if self.duration_s is None or elapsed_s <= self.duration_s:
            # Heating phase
            progress = 1.0 - math.exp(-elapsed_s / self._tau_heat)
            return max_delta * progress
        else:
            # Cooldown phase: decay from whatever peak was reached
            peak = max_delta * (1.0 - math.exp(-self.duration_s / self._tau_heat))
            cooldown_elapsed = elapsed_s - self.duration_s
            return peak * math.exp(-cooldown_elapsed / self._tau_cool)

    # ── core apply ──────────────────────────────────────────────────────

    def apply(self, t_s: float, healthy_values: dict[str, float]) -> dict[str, float]:
        """Ramp ``cht_c``, ``egt_c``, and ``oil_temp_c`` above baseline.

        All other channels are returned untouched.
        """
        values = copy.deepcopy(healthy_values)
        elapsed = self.elapsed_since_start(t_s)

        # Small per-sample noise so the curve isn't unnaturally smooth
        noise_cht = float(self._rng.normal(0, 0.8))
        noise_egt = float(self._rng.normal(0, 1.2))
        noise_oil = float(self._rng.normal(0, 0.4))

        values["cht_c"]     += self._ramp(elapsed, self._cht_max) + noise_cht
        values["egt_c"]     += self._ramp(elapsed, self._egt_max) + noise_egt
        values["oil_temp_c"] += self._ramp(elapsed, self._oil_max) + noise_oil

        return values


# ── Oil pressure drop fault ────────────────────────────────────────────────


class OilPressureDropFault(FaultScenario):
    """Simulate an oil system failure (pump degradation, seal leak, line rupture).

    Two distinct failure modes are supported:

    *   ``"sudden"`` — Pressure drops to its floor almost instantly (within
        ~0.3 s), modelling a catastrophic line rupture or pump seizure.
    *   ``"gradual"`` — Pressure decays exponentially over ``duration_s``,
        modelling progressive seal wear or a slow leak.

    In both modes the secondary symptom of **rising oil temperature** is
    coupled: lower oil pressure → less lubrication → more friction → heat.

    Parameters
    ----------
    severity : float
        0.0 = mild, 1.0 = total loss.  Controls the *floor* that
        pressure drops to:
        ``floor = baseline * (1 - 0.3 - 0.6 * severity)``
        i.e. severity=0 keeps ~70 % of baseline, severity=1 keeps ~10 %.
    mode : ``"sudden"`` | ``"gradual"``
        Failure profile shape.
    start_time_s, duration_s
        Time window.  ``duration_s`` controls how long the fault persists
        (and for ``"gradual"`` mode, how fast the decline is).
    seed : int | None
        RNG seed for per-sample noise.
    """

    VALID_MODES = ("sudden", "gradual")

    def __init__(
        self,
        severity: float = 0.5,
        mode: str = "gradual",
        start_time_s: float = 0.0,
        duration_s: float = 10.0,
        seed: int | None = None,
    ) -> None:
        if not 0.0 <= severity <= 1.0:
            import warnings
            clamped = max(0.0, min(1.0, severity))
            warnings.warn(f"severity {severity} out of bounds, clamped to {clamped}")
            severity = clamped
        if mode not in self.VALID_MODES:
            raise ValueError(
                f"mode must be one of {self.VALID_MODES}, got {mode!r}"
            )
        if duration_s is None or duration_s <= 0:
            raise ValueError(
                f"OilPressureDropFault requires a positive duration_s "
                f"(got {duration_s})"
            )

        super().__init__(
            name=f"oil_pressure_drop_{mode}",
            start_time_s=start_time_s,
            duration_s=duration_s,
        )
        self.severity = severity
        self.mode = mode
        self._rng = np.random.default_rng(seed)

        # Fraction of baseline pressure to *retain* at full effect
        #   severity=0 → keep 70 %,  severity=1 → keep 10 %
        self._floor_frac = 1.0 - (0.3 + 0.6 * severity)

        # Gradual mode: tau so ~95 % of drop reached by duration_s
        self._tau_drop = duration_s / 3.0
        # Sudden mode: very fast step (~0.3 s tau)
        self._tau_sudden = 0.3

        # Oil temp rise from friction (secondary symptom)
        #   severity=0 → +5 deg C,  severity=1 → +30 deg C
        self._oil_temp_max = 5.0 + 25.0 * severity

        # Recovery tail (pressure slowly returns after fault ends)
        self._tau_recover = self._tau_drop * 1.5
        self._recovery_tail_s = self._tau_recover * 5.0

    # ── helpers ─────────────────────────────────────────────────────────

    def is_active(self, t_s: float) -> bool:
        """Override to keep alive during the recovery tail."""
        if t_s < self.start_time_s:
            return False
        if self.duration_s is None:
            return True
        return t_s < (self.start_time_s + self.duration_s + self._recovery_tail_s)

    def _pressure_factor(self, elapsed_s: float) -> float:
        """Return the multiplier for oil_pressure_kpa (1.0 = healthy, floor_frac = worst).

        During the active fault window, pressure drops toward the floor.
        After duration_s, it exponentially recovers back toward 1.0.
        """
        drop_depth = 1.0 - self._floor_frac  # total fractional drop

        if elapsed_s <= self.duration_s:
            # Active fault phase
            if self.mode == "sudden":
                progress = 1.0 - math.exp(-elapsed_s / self._tau_sudden)
            else:  # gradual
                progress = 1.0 - math.exp(-elapsed_s / self._tau_drop)
            return 1.0 - drop_depth * progress
        else:
            # Recovery phase: pressure climbs back from whatever it reached
            peak_progress = 1.0 - math.exp(-self.duration_s / (
                self._tau_sudden if self.mode == "sudden" else self._tau_drop
            ))
            peak_factor = 1.0 - drop_depth * peak_progress
            recover_elapsed = elapsed_s - self.duration_s
            # Exponential return toward 1.0
            return 1.0 - (1.0 - peak_factor) * math.exp(
                -recover_elapsed / self._tau_recover
            )

    def _temp_rise(self, elapsed_s: float) -> float:
        """Secondary symptom: oil temp rise from low lubrication."""
        # Temperature rise is proportional to how much pressure has dropped
        pressure_factor = self._pressure_factor(elapsed_s)
        drop_fraction = 1.0 - pressure_factor  # 0 when healthy, ~0.9 at worst
        return self._oil_temp_max * drop_fraction

    # ── core apply ──────────────────────────────────────────────────────

    def apply(self, t_s: float, healthy_values: dict[str, float]) -> dict[str, float]:
        """Reduce ``oil_pressure_kpa`` and raise ``oil_temp_c``.

        All other channels are returned untouched.
        """
        values = copy.deepcopy(healthy_values)
        elapsed = self.elapsed_since_start(t_s)

        # Pressure drop
        noise_p = float(self._rng.normal(0, 2.0))
        values["oil_pressure_kpa"] = max(
            0.0, values["oil_pressure_kpa"] * self._pressure_factor(elapsed) + noise_p
        )

        # Secondary: oil temp rise
        noise_t = float(self._rng.normal(0, 0.5))
        values["oil_temp_c"] += self._temp_rise(elapsed) + noise_t

        return values


# ── Injector fault ─────────────────────────────────────────────────────────


class InjectorFault(FaultScenario):
    """Simulate a faulty fuel injector (partial blockage / lean-running).

    **Physical model — lean running:**  A partially clogged injector
    delivers *less fuel* than commanded.  The air-fuel mixture shifts
    lean, which has three observable consequences:

    1.  ``fuel_flow_lph`` **drops** on average and becomes **erratic**
        (intermittent partial blockages cause irregular dropouts).
    2.  ``rpm`` **sags** because each combustion cycle releases less
        energy.
    3.  ``egt_c`` **rises** because a lean mixture burns at a higher
        temperature (excess oxygen raises peak flame temperature).

    All other channels (CHT, oil_pressure, oil_temp, vibration) are
    returned untouched.

    Parameters
    ----------
    severity : float
        0.0 = barely noticeable, 1.0 = severe blockage.  Controls:

        - *mean fuel reduction*: 5–30 % of healthy baseline.
        - *fuel noise amplitude*: baseline noise × (1 + 4 × severity).
        - *dropout probability*: 5–40 % chance per sample of a deeper
          transient dip (simulating intermittent blockage).
        - *dropout depth*: 20–60 % additional reduction during a dropout.
        - *RPM sag*: proportional to fuel reduction.
        - *EGT rise*: up to +60 °C at severity=1.

    start_time_s, duration_s
        Time window (inherited from :class:`FaultScenario`).
    seed : int | None
        RNG seed for reproducibility.
    """

    def __init__(
        self,
        severity: float = 0.5,
        start_time_s: float = 0.0,
        duration_s: float | None = None,
        seed: int | None = None,
    ) -> None:
        if not 0.0 <= severity <= 1.0:
            import warnings
            clamped = max(0.0, min(1.0, severity))
            warnings.warn(f"severity {severity} out of bounds, clamped to {clamped}")
            severity = clamped

        super().__init__(
            name="injector_fault",
            start_time_s=start_time_s,
            duration_s=duration_s,
        )
        self.severity = severity
        self._rng = np.random.default_rng(seed)

        # Mean fuel reduction fraction (5 – 30 %)
        self._fuel_reduction = 0.05 + 0.25 * severity

        # Erratic noise multiplier on top of healthy noise
        #   severity=0 → 1.5× normal noise,  severity=1 → 5× normal noise
        self._noise_mult = 1.5 + 3.5 * severity

        # Intermittent dropout parameters
        #   probability per sample that a deep transient dip occurs
        self._dropout_prob = 0.05 + 0.35 * severity   # 5 – 40 %
        #   depth of the dropout (additional reduction fraction)
        self._dropout_lo = 0.20 + 0.15 * severity     # 20 – 35 %
        self._dropout_hi = 0.35 + 0.25 * severity     # 35 – 60 %

        # EGT rise ceiling (lean burns hotter)
        #   severity=0 → +10 °C,  severity=1 → +60 °C
        self._egt_rise_max = 10.0 + 50.0 * severity

        # RPM sag ceiling (less fuel → less power)
        #   severity=0 → −2 %,  severity=1 → −12 %
        self._rpm_sag_frac = 0.02 + 0.10 * severity

    # ── core apply ──────────────────────────────────────────────────────

    def apply(self, t_s: float, healthy_values: dict[str, float]) -> dict[str, float]:
        """Reduce and add noise to ``fuel_flow_lph``, sag ``rpm``, raise ``egt_c``.

        All other channels are returned untouched.
        """
        values = copy.deepcopy(healthy_values)
        elapsed = self.elapsed_since_start(t_s)

        # Ramp the fault effect in over the first 2 seconds to avoid an
        # unphysical instant change (injector clogs progressively).
        ramp = min(1.0, elapsed / 2.0)

        # ── Fuel flow ───────────────────────────────────────────────
        fuel = values["fuel_flow_lph"]

        # Base reduction
        reduction = self._fuel_reduction * ramp
        fuel *= (1.0 - reduction)

        # Erratic noise (irregular delivery)
        noise = float(self._rng.normal(0, 0.3 * self._noise_mult * ramp))
        fuel += noise

        # Intermittent dropout pulse
        if float(self._rng.random()) < self._dropout_prob * ramp:
            dropout_depth = float(self._rng.uniform(
                self._dropout_lo, self._dropout_hi
            ))
            fuel *= (1.0 - dropout_depth)

        values["fuel_flow_lph"] = max(0.0, fuel)

        # ── RPM sag (proportional to actual fuel deficit) ───────────
        # The RPM sag is driven by how much fuel was actually lost,
        # so dropouts cause visible RPM dips too.
        actual_fuel_loss = 1.0 - (values["fuel_flow_lph"] /
                                   max(1e-6, healthy_values["fuel_flow_lph"]))
        rpm_sag = actual_fuel_loss * self._rpm_sag_frac * values["rpm"]
        noise_rpm = float(self._rng.normal(0, 5.0 * ramp))
        values["rpm"] = max(0.0, values["rpm"] - rpm_sag + noise_rpm)

        # ── EGT rise (lean mixture burns hotter) ────────────────────
        egt_rise = self._egt_rise_max * reduction  # scales with fuel loss
        noise_egt = float(self._rng.normal(0, 1.5 * ramp))
        values["egt_c"] += egt_rise + noise_egt

        return values


# ── Vibration spike ─────────────────────────────────────────────────────────


class VibrationSpikeFault(FaultScenario):
    """Simulate a mechanical fault (e.g. bearing wear, imbalance).

    The fault causes ``vibration_g`` to rise well above the healthy baseline.
    It supports two patterns:
    - ``"intermittent"``: sudden, sharp spikes in vibration.
    - ``"sustained"``: a constant elevated floor for vibration.

    A very subtle RPM instability is also introduced as a secondary symptom.

    Parameters
    ----------
    pattern : str
        Either ``"intermittent"`` or ``"sustained"``.
    severity : float
        0.0 = barely noticeable, 1.0 = severe. Controls spike magnitude/frequency
        or the elevated floor height.
    start_time_s, duration_s
        Time window (inherited from :class:`FaultScenario`).
    seed : int | None
        RNG seed for reproducible events.
    """

    def __init__(
        self,
        pattern: str = "sustained",
        severity: float = 0.5,
        start_time_s: float = 0.0,
        duration_s: Optional[float] = None,
        seed: Optional[int] = None,
    ) -> None:
        if pattern not in ("intermittent", "sustained"):
            raise ValueError("pattern must be 'intermittent' or 'sustained'")
        if not 0.0 <= severity <= 1.0:
            import warnings
            clamped = max(0.0, min(1.0, severity))
            warnings.warn(f"severity {severity} out of bounds, clamped to {clamped}")
            severity = clamped

        super().__init__(
            name="vibration_spike",
            start_time_s=start_time_s,
            duration_s=duration_s,
        )
        self.pattern = pattern
        self.severity = severity
        self._rng = np.random.default_rng(seed)

    def apply(self, t_s: float, healthy_values: dict[str, float]) -> dict[str, float]:
        if not self.is_active(t_s):
            return copy.deepcopy(healthy_values)

        values = copy.deepcopy(healthy_values)
        
        # Subtle RPM instability (up to +/- 0.5%)
        # Real bearing faults show up as slight drag/chatter on the shaft
        rpm_noise_amp = values["rpm"] * 0.005 * self.severity
        values["rpm"] += float(self._rng.uniform(-rpm_noise_amp, rpm_noise_amp))

        if self.pattern == "sustained":
            # Sustained elevated floor: 0.5g to 2.5g above baseline
            elevated = 0.5 + 2.0 * self.severity
            noise = float(self._rng.normal(0, 0.2 + 0.3 * self.severity))
            values["vibration_g"] += max(0.0, elevated + noise)
        else:
            # Intermittent spikes: randomly occur ~ 10-30% of the time (1-3 times/sec at 10Hz)
            # Probability scales with severity
            prob = 0.1 + 0.2 * self.severity
            if self._rng.random() < prob:
                spike = float(self._rng.uniform(1.0 + self.severity, 3.0 + 2.0 * self.severity))
                values["vibration_g"] += spike

        return values


# ── Fault manager ──────────────────────────────────────────────────────────


class FaultManager:
    """Orchestrate multiple ``FaultScenario`` instances.

    The manager iterates through its scenarios in registration order,
    applying each active fault's ``apply()`` to the running values dict.
    It also exposes the current ground-truth **fault label** — a
    comma-separated string of active fault names (or ``"healthy"`` when
    no faults are active).

    Parameters
    ----------
    scenarios : list[FaultScenario] | None
        Initial list of fault scenarios.  More can be added later via
        :meth:`add`.
    """

    def __init__(self, scenarios: list[FaultScenario] | None = None) -> None:
        self._scenarios: list[FaultScenario] = list(scenarios) if scenarios else []

    # ── mutation ────────────────────────────────────────────────────────

    def add(self, scenario: FaultScenario) -> None:
        """Register a new fault scenario."""
        self._scenarios.append(scenario)

    def clear(self) -> None:
        """Remove all registered scenarios."""
        self._scenarios.clear()

    # ── query ───────────────────────────────────────────────────────────

    @property
    def scenarios(self) -> list[FaultScenario]:
        """Return an immutable *copy* of the scenario list."""
        return list(self._scenarios)

    def active_scenarios(self, t_s: float) -> list[FaultScenario]:
        """Return only the scenarios that are active at time *t_s*."""
        return [s for s in self._scenarios if s.is_active(t_s)]

    def fault_label(self, t_s: float) -> str:
        """Ground-truth label for the current time-step.

        Returns a comma-separated string of active fault names, or the
        literal string ``"healthy"`` when no faults are active.  This
        value is intended for the out-of-band label column written
        alongside the telemetry CSV — **not** for the CAN schema itself,
        since real hardware would never know the label.
        """
        active = self.active_scenarios(t_s)
        if not active:
            return "healthy"
        return ",".join(s.name for s in active)

    # ── core pipeline ───────────────────────────────────────────────────

    def apply_all(
        self, t_s: float, healthy_values: dict[str, float]
    ) -> dict[str, float]:
        """Run every active fault's ``apply()`` in registration order.

        Parameters
        ----------
        t_s : float
            Current simulation time in seconds.
        healthy_values : dict[str, float]
            Clean sensor readings from ``signal_models.healthy_sample()``.

        Returns
        -------
        dict[str, float]
            The sensor dict after all active faults have been applied.
            If no faults are active, a deep copy of *healthy_values* is
            returned so callers can safely mutate the result.
        """
        active = self.active_scenarios(t_s)
        if not active:
            return copy.deepcopy(healthy_values)

        values = healthy_values
        for scenario in active:
            values = scenario.apply(t_s, values)
            
        # ── Safety Clipping ─────────────────────────────────────────────
        # Prevent compounding faults from producing mathematically impossible
        # physical states that would fail CAN schema bounds or physics.
        values["rpm"] = max(0.0, values["rpm"])
        values["cht_c"] = max(0.0, values["cht_c"])
        values["egt_c"] = max(0.0, values["egt_c"])
        values["oil_pressure_kpa"] = max(0.0, values["oil_pressure_kpa"])
        values["oil_temp_c"] = max(0.0, values["oil_temp_c"])
        values["fuel_flow_lph"] = max(0.0, values["fuel_flow_lph"])
        values["vibration_g"] = max(0.0, values["vibration_g"])
            
        return values

    # ── dunder helpers ──────────────────────────────────────────────────

    def __len__(self) -> int:
        return len(self._scenarios)

    def __repr__(self) -> str:
        return f"FaultManager(scenarios={self._scenarios!r})"


# ── Quick demo ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from generator.signal_models import healthy_sample

    # Create a NoOpFault active from 0 s to 5 s
    noop = NoOpFault(start_time_s=0.0, duration_s=5.0)
    mgr = FaultManager([noop])

    for t in [0.0, 2.5, 5.0, 7.5]:
        sample = healthy_sample(throttle_pct=70.0)
        result = mgr.apply_all(t, sample)
        label = mgr.fault_label(t)
        print(f"t={t:5.1f}s  label={label:<10s}  active={mgr.active_scenarios(t)}")
        print(f"         rpm={result['rpm']:.1f}  cht={result['cht_c']:.1f}")
        print()
