"""
twin.py — Digital Twin scaffold: two synchronized signal paths.

Holds a **reference** EngineSimulator (the physics prediction) and a
pluggable **actual** source.  When no fault is present, actual ≈ reference
plus independent sensor noise.

The actual source is designed as a swappable callable so M2 can later
replace it with their live/faulted stream without touching this class.
"""

from typing import Callable, Dict, List, Optional

from twin_core.dynamics import EngineSimulator


# Type alias for the actual-source interface.
# Any callable matching  (throttle_cmd: float, dt: float) -> dict  works.
ActualSourceFn = Callable[[float, float], dict]


def _make_default_actual(ambient_temp: float = 25.0,
                         seed: int = 99) -> ActualSourceFn:
    """Create a default actual source — a second EngineSimulator.

    Uses a *different* random seed from the reference so the two streams
    have independent noise, but identical deterministic dynamics.
    """
    sim = EngineSimulator(ambient_temp=ambient_temp, seed=seed)
    return sim.step


class DigitalTwin:
    """Two-path engine model: predicted (reference) vs. actual.

    Parameters
    ----------
    actual_source : callable, optional
        Any callable with signature ``(throttle_cmd, dt) -> dict`` that
        returns a reading in the agreed schema.  If ``None``, a second
        :class:`EngineSimulator` with independent noise is used.
    ambient_temp : float
        Ambient temperature for the reference model [deg C].
    ref_seed : int
        Random seed for the reference simulator.
    actual_seed : int
        Random seed for the default actual simulator (ignored if
        *actual_source* is provided).
    """

    def __init__(self,
                 actual_source: Optional[ActualSourceFn] = None,
                 ambient_temp: float = 25.0,
                 ref_seed: int = 42,
                 actual_seed: int = 99):
        # Reference model — always the pure physics simulator
        self._reference = EngineSimulator(
            ambient_temp=ambient_temp, seed=ref_seed
        )

        # Actual source — pluggable; defaults to a second simulator
        if actual_source is not None:
            self._actual_source = actual_source
        else:
            self._actual_source = _make_default_actual(
                ambient_temp=ambient_temp, seed=actual_seed
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def step(self, throttle_cmd: float, dt: float) -> Dict[str, dict]:
        """Advance both paths by *dt* seconds and return side-by-side.

        Parameters
        ----------
        throttle_cmd : float
            Throttle command, 0-100 %.
        dt : float
            Time step in seconds.

        Returns
        -------
        dict
            ``{"predicted": {…}, "actual": {…}}`` — each inner dict
            follows the agreed schema from :meth:`EngineSimulator.step`.
        """
        predicted = self._reference.step(throttle_cmd, dt)
        actual = self._actual_source(throttle_cmd, dt)
        return {"predicted": predicted, "actual": actual}

    def run(self, throttle_profile: list, dt: float) -> List[Dict[str, dict]]:
        """Step through an entire throttle profile.

        Parameters
        ----------
        throttle_profile : list[float]
            One throttle command per time step.
        dt : float
            Time step in seconds.

        Returns
        -------
        list[dict]
            One ``{"predicted": …, "actual": …}`` per step.
        """
        return [self.step(t, dt) for t in throttle_profile]

    def set_actual_source(self, source: ActualSourceFn) -> None:
        """Hot-swap the actual source (e.g. when M2 plugs in faults).

        Parameters
        ----------
        source : callable
            ``(throttle_cmd, dt) -> dict``
        """
        self._actual_source = source


# ---------------------------------------------------------------------------
# Sanity check: both paths track closely with noise-only divergence
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    DT = 0.1

    # Throttle profile: hold 30 -> ramp 80 -> hold -> ramp 30
    profile = []
    profile += [30.0] * int(10 / DT)
    n_ramp = int(10 / DT)
    profile += [30.0 + (80.0 - 30.0) * i / n_ramp for i in range(n_ramp)]
    profile += [80.0] * int(15 / DT)
    profile += [80.0 + (30.0 - 80.0) * i / n_ramp for i in range(n_ramp)]
    profile += [30.0] * int(5 / DT)

    twin = DigitalTwin()
    series = twin.run(profile, DT)

    # Channels to compare (skip timestamp, throttle_cmd)
    channels = ["rpm", "cht", "egt", "oil_pressure", "oil_temp", "fuel_flow"]

    # Print header
    print(f"{'t(s)':>6}  {'Thr%':>5}  ", end="")
    for ch in channels:
        print(f"{'P_' + ch:>10} {'A_' + ch:>10} {'diff':>8}  ", end="")
    print()
    print("-" * 200)

    # Print one row every 5 seconds
    sample_every = int(5.0 / DT)
    max_abs_diff = {ch: 0.0 for ch in channels}

    for i in range(0, len(series), sample_every):
        p = series[i]["predicted"]
        a = series[i]["actual"]
        t = p["timestamp"]
        thr = p["throttle_cmd"]
        print(f"{t:6.1f}  {thr:5.1f}  ", end="")
        for ch in channels:
            diff = a[ch] - p[ch]
            max_abs_diff[ch] = max(max_abs_diff[ch], abs(diff))
            print(f"{p[ch]:10.2f} {a[ch]:10.2f} {diff:+8.2f}  ", end="")
        print()

    print("\n--- Max absolute divergence per channel (should be noise-level) ---")
    for ch in channels:
        print(f"  {ch:15s}: {max_abs_diff[ch]:.3f}")
