"""
dynamics.py — Stateful engine simulator with first-order-lag dynamics and
sensor noise.

Wraps the pure steady-state maps from engine_maps.py into a time-stepping
simulation where each channel moves toward its steady-state target at a
channel-specific time constant (RPM fastest, oil_temp slowest).

Noise is added here, NOT in engine_maps.py — this is the only place
stochastic behaviour lives.
"""

import math
import random
from typing import List, Optional

from twin_core import engine_maps


# ---------------------------------------------------------------------------
# Time constants (seconds) — how fast each channel tracks its target.
# Physically: RPM responds within fractions of a second (flywheel inertia),
# EGT lags a few seconds (exhaust thermal mass), CHT lags many seconds
# (cylinder head thermal mass), oil temp is the slowest (large oil volume).
# ---------------------------------------------------------------------------

TAU = {
    "rpm":          0.5,    # flywheel inertia — fast
    "fuel_flow":    0.8,    # injector response — fast
    "egt":          3.0,    # exhaust gas thermal lag
    "cht":          8.0,    # cylinder head thermal mass
    "oil_temp":    15.0,    # oil sump thermal mass — slowest
    "oil_pressure": 1.0,   # hydraulic response — fairly fast
}

# ---------------------------------------------------------------------------
# Sensor noise standard deviations (realistic instrument-grade noise).
# Kept small enough that the residual engine doesn't false-alarm on noise
# alone, but large enough to be visible in plots.
# ---------------------------------------------------------------------------

NOISE_STD = {
    "rpm":           8.0,    # tachometer jitter
    "fuel_flow":     0.05,   # flow sensor noise [L/hr]
    "egt":           4.0,    # thermocouple noise [deg C]
    "cht":           2.5,    # thermocouple noise [deg C]
    "oil_temp":      1.5,    # temp sensor noise [deg C]
    "oil_pressure":  0.8,    # pressure transducer noise [psi]
    "vibration_amp": 0.003,  # accelerometer noise [g]
    "vibration_freq": 0.5,   # frequency estimation jitter [Hz]
}


class EngineSimulator:
    """Stateful time-stepping engine simulator.

    Each call to :meth:`step` advances internal state by ``dt`` seconds,
    applying first-order-lag dynamics toward the steady-state targets
    computed by :mod:`engine_maps`, then adds sensor noise.

    Parameters
    ----------
    ambient_temp : float
        Ambient air temperature [deg C].  Default 25.
    seed : int or None
        Random seed for reproducibility.  ``None`` = non-deterministic.
    """

    # Number of cylinders (Rotax 912 = 4-cyl, 4-stroke)
    _NUM_CYLINDERS = 4

    def __init__(self, ambient_temp: float = 25.0,
                 seed: Optional[int] = None):
        self.ambient_temp = ambient_temp
        self._rng = random.Random(seed)
        self._time = 0.0

        # Initialise state to idle (throttle = 0)
        idle_rpm = engine_maps.target_rpm(0.0)
        idle = engine_maps.compute_all(0.0, idle_rpm, ambient_temp)

        self._state = {
            "rpm":          idle["rpm"],
            "fuel_flow":    idle["fuel_flow_Lph"],
            "egt":          idle["egt_C"],
            "cht":          idle["cht_C"],
            "oil_temp":     idle["oil_temp_C"],
            "oil_pressure": idle["oil_pressure_psi"],
        }

    # ------------------------------------------------------------------
    # Core stepping
    # ------------------------------------------------------------------

    def step(self, throttle_cmd: float, dt: float) -> dict:
        """Advance the simulation by *dt* seconds at the given throttle.

        Parameters
        ----------
        throttle_cmd : float
            Throttle command, 0-100 %.
        dt : float
            Time step in seconds (e.g. 0.1).

        Returns
        -------
        dict
            Snapshot matching the agreed schema::

                {timestamp, rpm, cht, egt, oil_pressure, oil_temp,
                 fuel_flow, vibration_amplitude, vibration_freq,
                 throttle_cmd}
        """
        self._time += dt

        # --- 1. Compute steady-state targets from current throttle ----
        target_rpm = engine_maps.target_rpm(throttle_cmd)
        targets = engine_maps.compute_all(
            throttle_cmd, target_rpm, self.ambient_temp
        )
        target_map = {
            "rpm":          targets["rpm"],
            "fuel_flow":    targets["fuel_flow_Lph"],
            "egt":          targets["egt_C"],
            "cht":          targets["cht_C"],
            "oil_temp":     targets["oil_temp_C"],
            "oil_pressure": targets["oil_pressure_psi"],
        }

        # --- 2. First-order lag toward each target --------------------
        for ch, tau in TAU.items():
            alpha = 1.0 - math.exp(-dt / tau)
            self._state[ch] += alpha * (target_map[ch] - self._state[ch])

        # --- 3. Recompute coupled channels from lagged state ----------
        # Oil pressure depends on current (lagged) RPM and oil_temp,
        # not on the instantaneous target. Re-derive its target from
        # the lagged values so the coupling stays physically consistent.
        coupled_op_target = engine_maps.oil_pressure_steady(
            self._state["rpm"], self._state["oil_temp"]
        )
        alpha_op = 1.0 - math.exp(-dt / TAU["oil_pressure"])
        self._state["oil_pressure"] += alpha_op * (
            coupled_op_target - self._state["oil_pressure"]
        )

        # --- 4. Vibration -------------------------------------------
        # Firing frequency for a 4-stroke, 4-cylinder:
        #   firing_freq = RPM * num_cylinders / (2 * 60)
        firing_freq = (self._state["rpm"] * self._NUM_CYLINDERS
                       / (2.0 * 60.0))
        base_amplitude = 0.02 + 0.008 * (self._state["rpm"] / 5500.0)
        vib_amp = base_amplitude + self._noise("vibration_amp")
        vib_freq = firing_freq + self._noise("vibration_freq")

        # --- 5. Add sensor noise to each channel ---------------------
        reading = {}
        for ch in self._state:
            reading[ch] = self._state[ch] + self._noise(ch)

        # --- 6. Clamp to physical minimums (nothing goes negative) ----
        reading["rpm"] = max(reading["rpm"], 0.0)
        reading["fuel_flow"] = max(reading["fuel_flow"], 0.0)
        reading["oil_pressure"] = max(reading["oil_pressure"], 0.0)
        vib_amp = max(vib_amp, 0.0)
        vib_freq = max(vib_freq, 0.0)

        # --- 7. Assemble output in the agreed schema ------------------
        return {
            "timestamp":           round(self._time, 4),
            "rpm":                 round(reading["rpm"], 2),
            "cht":                 round(reading["cht"], 2),
            "egt":                 round(reading["egt"], 2),
            "oil_pressure":        round(reading["oil_pressure"], 2),
            "oil_temp":            round(reading["oil_temp"], 2),
            "fuel_flow":           round(reading["fuel_flow"], 3),
            "vibration_amplitude": round(vib_amp, 5),
            "vibration_freq":      round(vib_freq, 2),
            "throttle_cmd":        throttle_cmd,
        }

    def run(self, throttle_profile: list, dt: float) -> list:
        """Step through an entire throttle profile and return the time series.

        Parameters
        ----------
        throttle_profile : list[float]
            One throttle command per time step.
        dt : float
            Time step in seconds.

        Returns
        -------
        list[dict]
            One dict per step, same schema as :meth:`step`.
        """
        return [self.step(t, dt) for t in throttle_profile]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _noise(self, channel: str) -> float:
        """Return a single Gaussian noise sample for *channel*."""
        std = NOISE_STD.get(channel, 0.0)
        return self._rng.gauss(0.0, std)

    @property
    def time(self) -> float:
        """Current simulation time [s]."""
        return self._time


# ---------------------------------------------------------------------------
# Sanity check: 20 -> 80 -> 20 throttle ramp over ~60 s
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    DT = 0.1  # 10 Hz

    # Build throttle profile: hold 20 -> ramp to 80 -> hold -> ramp to 20
    profile: List[float] = []
    # 0-10 s: hold at 20
    profile += [20.0] * int(10 / DT)
    # 10-25 s: ramp 20 -> 80
    n_ramp = int(15 / DT)
    profile += [20.0 + (80.0 - 20.0) * i / n_ramp for i in range(n_ramp)]
    # 25-40 s: hold at 80
    profile += [80.0] * int(15 / DT)
    # 40-55 s: ramp 80 -> 20
    profile += [80.0 + (20.0 - 80.0) * i / n_ramp for i in range(n_ramp)]
    # 55-60 s: hold at 20
    profile += [20.0] * int(5 / DT)

    sim = EngineSimulator(seed=42)
    series = sim.run(profile, DT)

    # Print header + one row every 5 seconds
    print(f"{'t(s)':>6}  {'Thr%':>5}  {'RPM':>7}  {'FF L/h':>7}  "
          f"{'EGT C':>7}  {'CHT C':>7}  {'OilT C':>7}  {'OilP psi':>8}  "
          f"{'VibA':>7}  {'VibF Hz':>7}")
    print("-" * 90)

    sample_every = int(5.0 / DT)
    for i in range(0, len(series), sample_every):
        r = series[i]
        print(f"{r['timestamp']:6.1f}  {r['throttle_cmd']:5.1f}  "
              f"{r['rpm']:7.1f}  {r['fuel_flow']:7.3f}  "
              f"{r['egt']:7.1f}  {r['cht']:7.1f}  "
              f"{r['oil_temp']:7.1f}  {r['oil_pressure']:8.1f}  "
              f"{r['vibration_amplitude']:7.4f}  {r['vibration_freq']:7.2f}")

    # Quick NaN / negative check
    any_bad = False
    for r in series:
        for k, v in r.items():
            if k == "throttle_cmd":
                continue
            if isinstance(v, float) and (math.isnan(v) or v < 0):
                print(f"BAD VALUE: {k}={v} at t={r['timestamp']}")
                any_bad = True
    if not any_bad:
        print("\nAll values non-negative, no NaNs. OK.")
