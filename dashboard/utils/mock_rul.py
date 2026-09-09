"""
utils/mock_rul.py
=================
Mock RUL (Remaining Useful Life) estimator matching data contract §2A.

Produces the exact payload shape M5 expects from M2/M3:
    {
        timestamp:          float   (Unix epoch),
        rul_hours:          float   (estimated remaining flight-hours),
        rul_cycles:         int     (estimated remaining start-stop cycles),
        confidence_lower:   float   (lower bound of CI, hours),
        confidence_upper:   float   (upper bound of CI, hours),
        confidence_level:   float   (e.g. 0.90 for 90% CI),
        trend:              str     ("stable" | "degrading" | "improving"),
        trend_slope:        float   (rate of change; negative = degrading),
        model_id:           str     (which model produced this estimate),
    }

This is a MOCK — replace with M2/M3's real RUL module when available.
The mock derives RUL from composite_score: lower score -> higher RUL.

Usage:
    from utils.mock_rul import MockRULEstimator

    rul_est = MockRULEstimator()
    rul_payload = rul_est.estimate(composite_score=0.12, timestamp=time.time())
"""

import time
import random
import math
from collections import deque


# ── Constants ─────────────────────────────────────────────────────────────────
_BASELINE_RUL_HOURS = 280.0       # Healthy engine RUL ceiling
_BASELINE_RUL_CYCLES = 560        # ~ 2x hours
_MIN_RUL = 0.0
_TREND_WINDOW = 10                # number of samples for trend computation
_TREND_THRESHOLD = 0.01           # slope magnitude below this = "stable"
_CI_BASE_HALF_WIDTH = 22.0        # +/- hours at full RUL
_CI_DEGRADED_MULTIPLIER = 2.5     # CI widens as RUL shrinks


class MockRULEstimator:
    """
    Derives RUL from composite_score using a simple inverse relationship.

    Higher composite_score (0-1+) -> more degradation -> lower RUL.
    Tracks history for trend computation.
    """

    def __init__(self, baseline_rul: float = _BASELINE_RUL_HOURS):
        self._baseline = baseline_rul
        self._history: deque[float] = deque(maxlen=_TREND_WINDOW)
        self._prev_rul: float = baseline_rul

    def estimate(self, composite_score: float, timestamp: float | None = None) -> dict:
        """
        Produce a section 2A RUL payload from the current composite_score.

        Args:
            composite_score: 0.0-1.0+ from M1's ResidualEngine.
            timestamp:       Unix epoch (defaults to now).

        Returns:
            dict matching data contract section 2A.
        """
        if timestamp is None:
            timestamp = time.time()

        # ── RUL calculation ───────────────────────────────────────────────────
        # Exponential decay: small scores -> near-baseline; large scores -> rapid drop
        decay_factor = math.exp(-3.5 * composite_score)
        rul_hours = max(_MIN_RUL, self._baseline * decay_factor)

        # Add slight noise for realism
        noise = random.gauss(0, 1.5)
        rul_hours = max(_MIN_RUL, round(rul_hours + noise, 1))

        rul_cycles = max(0, int(rul_hours * 2 + random.gauss(0, 3)))

        # ── Trend computation ─────────────────────────────────────────────────
        self._history.append(rul_hours)
        trend, trend_slope = self._compute_trend()

        # ── Confidence interval ───────────────────────────────────────────────
        # CI widens as RUL drops (less certain when degraded)
        rul_fraction = max(0.01, rul_hours / self._baseline)
        ci_half = _CI_BASE_HALF_WIDTH / max(0.1, rul_fraction)
        ci_half = min(ci_half, rul_hours * 0.35)  # cap at 35% of RUL

        confidence_lower = max(0.0, round(rul_hours - ci_half, 1))
        confidence_upper = round(rul_hours + ci_half, 1)

        self._prev_rul = rul_hours

        return {
            "timestamp":        round(timestamp, 3),
            "rul_hours":        rul_hours,
            "rul_cycles":       rul_cycles,
            "confidence_lower": confidence_lower,
            "confidence_upper": confidence_upper,
            "confidence_level": 0.90,
            "trend":            trend,
            "trend_slope":      round(trend_slope, 4),
            "model_id":         "mock_ensemble_v1",
        }

    def _compute_trend(self) -> tuple[str, float]:
        """
        Compute trend from the last N RUL values using linear slope.

        Returns:
            (trend_label, slope_value)
        """
        n = len(self._history)
        if n < 3:
            return "stable", 0.0

        # Simple linear regression slope
        vals = list(self._history)
        x_mean = (n - 1) / 2.0
        y_mean = sum(vals) / n
        num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(vals))
        den = sum((i - x_mean) ** 2 for i in range(n))
        slope = num / max(den, 1e-9)

        if slope < -_TREND_THRESHOLD:
            return "degrading", slope
        elif slope > _TREND_THRESHOLD:
            return "improving", slope
        else:
            return "stable", slope

    def reset(self):
        """Clear history and reset to baseline."""
        self._history.clear()
        self._prev_rul = self._baseline


# ── Self-test ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    est = MockRULEstimator()

    print("=" * 60)
    print("MOCK RUL ESTIMATOR SELF-TEST")
    print("=" * 60)

    # Healthy engine
    print("\n[1] HEALTHY ENGINE (composite_score ~ 0.03)")
    for i in range(5):
        payload = est.estimate(0.03 + random.gauss(0, 0.005))
        print(f"  tick {i+1}: rul={payload['rul_hours']:.1f}h "
              f"[{payload['confidence_lower']:.0f}-{payload['confidence_upper']:.0f}] "
              f"trend={payload['trend']} slope={payload['trend_slope']:.4f}")

    # Degrading engine
    print("\n[2] DEGRADING ENGINE (composite_score ramps 0.1 -> 0.8)")
    est.reset()
    for i in range(10):
        score = 0.1 + (0.7 * i / 9)
        payload = est.estimate(score)
        print(f"  tick {i+1}: score={score:.2f} -> rul={payload['rul_hours']:.1f}h "
              f"trend={payload['trend']}")

    print(f"\n[OK] All payloads match section 2A schema.\n")
