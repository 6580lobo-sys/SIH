"""
residual.py — Physics-informed residual engine (USP #1).

Consumes paired ``{"predicted": …, "actual": …}`` snapshots from
:class:`DigitalTwin` and produces per-channel normalised residuals plus a
single composite anomaly score.

Design decisions
----------------
* **Range-normalised residuals** — each channel is divided by its nominal
  operating span so that an RPM deviation of 50 and an oil-pressure
  deviation of 5 are comparable on a 0-1 scale.
* **EWMA smoothing** — an exponentially weighted moving average of the
  signed residual reduces false-positives from single-sample sensor noise
  while preserving directionality (M3 needs to know *which way* a channel
  drifted).
* **Composite score** — RMS of the EWMA-smoothed normalised residuals,
  yielding a single 0–1+ severity number.  Near-zero on healthy data,
  rises when any channel diverges.
* **Streaming interface** — :meth:`update` processes one tick at a time,
  suitable for M4's live dashboard.  :meth:`process_batch` is a
  convenience wrapper for offline / replay use.
"""

import math
from typing import Dict, Generator, List, Optional


# ---------------------------------------------------------------------------
# Nominal operating ranges (max − min) per the engine_maps reference data.
# Used to normalise raw residuals so channels with different physical units
# become comparable.
# ---------------------------------------------------------------------------

NOMINAL_RANGE: Dict[str, float] = {
    "rpm":                 4400.0,   # 1400 – 5800
    "cht":                  170.0,   # 90 – 260  °C
    "egt":                  350.0,   # 600 – 950 °C
    "oil_pressure":          70.0,   # 20 – 90   psi
    "oil_temp":              80.0,   # 50 – 130  °C
    "fuel_flow":             13.0,   # 2 – 15    L/hr
    "vibration_amplitude":    0.05,  # 0 – 0.05  g  (approximate)
    "vibration_freq":       120.0,   # ~25 – 145  Hz (firing freq range)
}

# Channels included in residual computation (skip timestamp, throttle_cmd)
RESIDUAL_CHANNELS = list(NOMINAL_RANGE.keys())


class ResidualEngine:
    """Streaming residual calculator for the digital-twin comparison loop.

    Parameters
    ----------
    ewma_alpha : float
        Smoothing factor for the EWMA (0 < alpha <= 1).  Larger values
        make the residual more responsive but noisier.  Default 0.10
        (~2 s effective window at 10 Hz).
    """

    def __init__(self, ewma_alpha: float = 0.10):
        self._alpha = ewma_alpha
        # EWMA state per channel — initialised to 0 (no divergence)
        self._ewma: Dict[str, float] = {ch: 0.0 for ch in RESIDUAL_CHANNELS}
        self._tick = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, pair: Dict[str, dict]) -> dict:
        """Process one ``{"predicted": …, "actual": …}`` tick.

        Parameters
        ----------
        pair : dict
            Output of :meth:`DigitalTwin.step`.

        Returns
        -------
        dict
            ``{"timestamp": float,
              "residuals": {channel: float, …},
              "composite_score": float}``

            ``residuals`` values are EWMA-smoothed, range-normalised,
            and **signed** (positive = actual > predicted).
            ``composite_score`` is the RMS of all residual channels (≥ 0).
        """
        predicted = pair["predicted"]
        actual = pair["actual"]
        self._tick += 1

        residuals: Dict[str, float] = {}
        sum_sq = 0.0
        n = 0

        for ch in RESIDUAL_CHANNELS:
            p_val = predicted.get(ch)
            a_val = actual.get(ch)
            if p_val is None or a_val is None:
                continue

            # 1. Raw normalised residual (signed)
            span = NOMINAL_RANGE[ch]
            raw_norm = (a_val - p_val) / span

            # 2. EWMA smoothing (signed, so direction is preserved)
            self._ewma[ch] = (self._alpha * raw_norm
                              + (1.0 - self._alpha) * self._ewma[ch])

            residuals[ch] = round(self._ewma[ch], 6)
            sum_sq += self._ewma[ch] ** 2
            n += 1

        # 3. Composite anomaly score — RMS of EWMA residuals
        composite = math.sqrt(sum_sq / n) if n > 0 else 0.0

        return {
            "timestamp": predicted.get("timestamp", 0.0),
            "residuals": residuals,
            "composite_score": round(composite, 6),
        }

    def process_stream(self,
                       pairs: Generator) -> Generator[dict, None, None]:
        """Generator wrapper: yields residual output for each incoming pair.

        Parameters
        ----------
        pairs : iterable
            Iterable of ``{"predicted": …, "actual": …}`` dicts.

        Yields
        ------
        dict
            Same schema as :meth:`update`.
        """
        for pair in pairs:
            yield self.update(pair)

    def process_batch(self, pairs: List[Dict[str, dict]]) -> List[dict]:
        """Convenience: process a full batch and return a list.

        Parameters
        ----------
        pairs : list[dict]
            Output of :meth:`DigitalTwin.run`.

        Returns
        -------
        list[dict]
            One residual output per tick.
        """
        return [self.update(p) for p in pairs]

    def reset(self) -> None:
        """Reset EWMA state to zero (e.g. between replay scenarios)."""
        self._ewma = {ch: 0.0 for ch in RESIDUAL_CHANNELS}
        self._tick = 0

    def signature(self, threshold: float = 0.03) -> dict:
        """Return the current residual signature for M3 classification.

        This is the primary interface M3's fault classifier consumes.
        Call it after :meth:`update` to get a snapshot of which channels
        are deviating and by how much.

        Parameters
        ----------
        threshold : float
            Minimum |EWMA residual| for a channel to be considered
            "dominant" (i.e. meaningfully deviating vs. noise).
            Default 0.03 (~3% of operating range).

        Returns
        -------
        dict
            ``{
                "feature_vector":    {channel: float, ...},
                "dominant_channels": [(channel, value), ...],
                "severity":          float,
                "fault_detected":    bool,
            }``

            - ``feature_vector``: EWMA-smoothed normalised residual per
              channel (signed).  This is what M3 should use as input to
              the classifier — fixed-length, fixed-order.
            - ``dominant_channels``: channels sorted by ``|residual|``
              descending, filtered to those above *threshold*.
            - ``severity``: composite RMS score (same as
              ``composite_score`` from :meth:`update`).
            - ``fault_detected``: ``True`` if severity exceeds threshold.
        """
        import math as _math

        feature_vector = {ch: round(self._ewma[ch], 6)
                          for ch in RESIDUAL_CHANNELS}

        # Sort by absolute magnitude, descending
        sorted_channels = sorted(
            feature_vector.items(),
            key=lambda x: abs(x[1]),
            reverse=True,
        )

        dominant = [(ch, val) for ch, val in sorted_channels
                    if abs(val) > threshold]

        sum_sq = sum(v ** 2 for v in self._ewma.values())
        severity = _math.sqrt(sum_sq / len(self._ewma)) if self._ewma else 0.0

        return {
            "feature_vector": feature_vector,
            "dominant_channels": dominant,
            "severity": round(severity, 6),
            "fault_detected": severity > threshold,
        }


# ---------------------------------------------------------------------------
# Sanity check: 60 s of healthy data — composite_score should stay near zero
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from twin_core.twin import DigitalTwin

    DT = 0.1
    DURATION = 60.0  # seconds

    # Throttle profile: ramp 30 -> 70 -> 30 to exercise transients
    profile: list = []
    profile += [30.0] * int(10 / DT)
    n_ramp = int(10 / DT)
    profile += [30.0 + (70.0 - 30.0) * i / n_ramp for i in range(n_ramp)]
    profile += [70.0] * int(15 / DT)
    profile += [70.0 + (30.0 - 70.0) * i / n_ramp for i in range(n_ramp)]
    profile += [30.0] * int(15 / DT)

    twin = DigitalTwin()
    residual_eng = ResidualEngine()

    pairs = twin.run(profile, DT)
    results = residual_eng.process_batch(pairs)

    # Print header
    print(f"{'t(s)':>6}  {'composite':>10}  ", end="")
    for ch in RESIDUAL_CHANNELS:
        print(f"{ch:>12}", end="  ")
    print()
    print("-" * 130)

    # Print every 5 seconds
    sample_every = int(5.0 / DT)
    max_composite = 0.0

    for i in range(0, len(results), sample_every):
        r = results[i]
        max_composite = max(max_composite, r["composite_score"])
        print(f"{r['timestamp']:6.1f}  {r['composite_score']:10.6f}  ", end="")
        for ch in RESIDUAL_CHANNELS:
            print(f"{r['residuals'].get(ch, 0):12.6f}", end="  ")
        print()

    print(f"\nMax composite score over {DURATION:.0f}s: {max_composite:.6f}")
    if max_composite < 0.05:
        print("PASS: composite stays near-zero (< 0.05) on healthy data.")
    else:
        print("WARNING: composite exceeded 0.05 — investigate noise / EWMA tuning.")
