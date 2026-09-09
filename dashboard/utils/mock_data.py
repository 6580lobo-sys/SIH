"""
utils/mock_data.py
==================
Mock data generator that exactly mirrors M1's three output schemas.

Payload 1 — Per-tick residual (emitted every tick):
    {
        timestamp:      float  (Unix time),
        residuals: {
            rpm:                  float,
            cht:                  float,
            egt:                  float,
            oil_pressure:         float,
            oil_temp:             float,
            fuel_flow:            float,
            vibration_amplitude:  float,
            vibration_freq:       float,
        },
        composite_score: float   # 0.0–1.0+ (NOT 0–100; scale in UI)
    }

Payload 2 — Signature (on-demand / occasional):
    {
        feature_vector:   {channel: float, ...},   # raw feature magnitudes
        dominant_channels: [(channel, float), ...], # sorted DESC by magnitude
        severity:         float,                    # 0.0–1.0
        fault_detected:   bool,
    }

Payload 3 — Raw predicted / actual dicts (10 fields each):
    {
        timestamp:            float,
        rpm:                  float,
        cht:                  float,
        egt:                  float,
        oil_pressure:         float,
        oil_temp:             float,
        fuel_flow:            float,
        vibration_amplitude:  float,
        vibration_freq:       float,
        throttle_cmd:         float,
    }

Usage:
    from utils.mock_data import MockEngine

    engine = MockEngine()
    tick = engine.next_tick()          # -> Payload 1
    sig  = engine.get_signature()      # -> Payload 2 (or None if no fault)
    pred, actual = engine.get_raw()    # -> (Payload 3, Payload 3)

    # Inject a fault for testing:
    engine.inject_fault("overheating")
    engine.clear_fault()
"""

import time
import math
import random
from typing import Optional


# ── Channel metadata ──────────────────────────────────────────────────────────
# Healthy baseline ranges  (min, max, unit)
_CHANNEL_RANGES = {
    "rpm":                 (2200.0, 2800.0,  "RPM"),
    "cht":                 (150.0,  200.0,   "°C"),
    "egt":                 (600.0,  750.0,   "°C"),
    "oil_pressure":        (3.5,    5.5,     "bar"),
    "oil_temp":            (80.0,   110.0,   "°C"),
    "fuel_flow":           (18.0,   25.0,    "L/h"),
    "vibration_amplitude": (0.02,   0.08,    "g"),
    "vibration_freq":      (48.0,   52.0,    "Hz"),
    "throttle_cmd":        (0.6,    0.9,     "%"),   # Payload 3 only
}

CHANNELS = list(_CHANNEL_RANGES.keys())
RESIDUAL_CHANNELS = [c for c in CHANNELS if c != "throttle_cmd"]

# ── Fault definitions ─────────────────────────────────────────────────────────
# Each fault biases specific channels by (additive_offset, multiplicative_factor)
_FAULT_PROFILES = {
    "overheating": {
        "egt":         (+120.0, 1.0),
        "cht":         (+40.0,  1.0),
        "oil_temp":    (+25.0,  1.0),
    },
    "oil_pressure_drop": {
        "oil_pressure": (-2.5,  1.0),
        "oil_temp":     (+15.0, 1.0),
    },
    "misfire": {
        "rpm":          (-300.0, 1.0),
        "egt":          (+60.0,  1.0),
        "vibration_amplitude": (+0.15, 1.0),
    },
    "injector_fault": {
        "fuel_flow":    (-6.0,  1.0),
        "rpm":          (-150.0, 1.0),
        "egt":          (-40.0,  1.0),
    },
    "vibration_spike": {
        "vibration_amplitude": (+0.30, 1.5),
        "vibration_freq":      (+8.0,  1.0),
    },
}

FAULT_TYPES = list(_FAULT_PROFILES.keys())


class MockEngine:
    """
    Simulates M1's DigitalTwin + ResidualEngine output.

    The internal 'predicted' track is the clean analytical model.
    The 'actual' track = predicted + gaussian noise + optional fault bias.
    Residuals = actual - predicted per channel.
    composite_score = weighted L2 norm of normalised residuals.

    This is a drop-in stand-in for M1's real feed.
    Swap out next_tick() / get_signature() / get_raw() call sites on Day 2.
    """

    def __init__(
        self,
        tick_rate_hz: float = 2.0,
        noise_sigma: float = 0.02,
        signature_probability: float = 0.15,
        fault_ramp_ticks: int = 10,
        scenario_params: dict = None,
    ):
        """
        Args:
            tick_rate_hz:          How fast the engine sim advances (ticks/sec).
            noise_sigma:           Gaussian noise std as fraction of channel range.
            signature_probability: Chance of returning a signature on any given tick.
            fault_ramp_ticks:      How many ticks a fault takes to reach full severity.
            scenario_params:       Environmental scenario dict:
                                   {altitude_m, ambient_temp_c, throttle_demand_pct}
                                   Shifts predicted baselines to reflect operating
                                   environment (Block E — M4 scenario simulation).
        """
        self.tick_rate_hz       = tick_rate_hz
        self.noise_sigma        = noise_sigma
        self.sig_prob           = signature_probability
        self.fault_ramp_ticks   = fault_ramp_ticks

        # Block E — Environmental scenario parameters
        _sp = scenario_params or {}
        self.altitude_m         = float(_sp.get("altitude_m",       1000.0))   # m ASL
        self.ambient_temp_c     = float(_sp.get("ambient_temp_c",    25.0))    # deg C
        self.throttle_demand    = float(_sp.get("throttle_demand_pct", 70.0)) / 100.0  # 0-1

        # Pre-compute scenario offsets applied to predicted baseline
        # High altitude: lower air density  → lower RPM, fuel_flow, oil_pressure
        _alt_factor  = max(0.0, 1.0 - self.altitude_m / 15000.0)   # 0 at 15 000 m
        _temp_excess = max(0.0, self.ambient_temp_c - 25.0)         # excess above ISA 25°C
        _thr_excess  = max(0.0, self.throttle_demand - 0.70)        # excess above 70% demand

        # Offsets added to predicted values (not fault offsets — baseline shift)
        self._scenario_offsets = {
            "rpm":                  -200.0  * (1.0 - _alt_factor),  # altitude robs RPM
            "egt":                  +15.0   * (_temp_excess / 10.0) + 30.0 * _thr_excess,
            "cht":                  +10.0   * (_temp_excess / 10.0) + 20.0 * _thr_excess,
            "oil_temp":             +8.0    * (_temp_excess / 10.0),
            "oil_pressure":         -0.3    * (1.0 - _alt_factor),  # lower density → less oil back-pressure
            "fuel_flow":            +2.0    * _thr_excess,           # more throttle → more fuel
            "vibration_amplitude":  +0.005  * _thr_excess,
            "vibration_freq":       0.0,
        }
        # Noise scales with throttle demand (more demand → noisier readings)
        self._scenario_noise_scale = 1.0 + 0.5 * _thr_excess

        # Internal state
        self._t0            = time.time()
        self._tick_count    = 0
        self._active_fault  = None      # None or one of FAULT_TYPES
        self._fault_age     = 0         # ticks since fault was injected
        self._fault_cleared = False

        # Last computed values (for get_raw() call)
        self._last_predicted: dict = {}
        self._last_actual: dict    = {}
        self._last_residuals: dict = {}
        self._last_composite: float = 0.0

    # ── Public API (matches M1 interface) ────────────────────────────────────

    def next_tick(self) -> dict:
        """
        Emit one per-tick residual payload (Payload 1).

        Returns:
            {
                timestamp:       float,
                residuals:       {channel: float, ...},
                composite_score: float   # 0.0–1.0+
            }
        """
        now = time.time()
        self._tick_count += 1
        if self._active_fault:
            self._fault_age += 1

        predicted = self._compute_predicted(now)
        actual    = self._compute_actual(predicted)

        residuals = {
            ch: round(actual[ch] - predicted[ch], 4)
            for ch in RESIDUAL_CHANNELS
        }
        composite = self._compute_composite(residuals)

        # Cache for get_raw()
        self._last_predicted = {**predicted, "timestamp": now}
        self._last_actual    = {**actual,    "timestamp": now}
        self._last_residuals = residuals
        self._last_composite = composite

        return {
            "timestamp":       round(now, 3),
            "residuals":       residuals,
            "composite_score": round(composite, 4),
        }

    def get_signature(self) -> Optional[dict]:
        """
        Return a fault signature payload (Payload 2), or None.

        Probability of returning a signature increases when a fault is active.
        Matches M1's ResidualEngine.get_signature() output shape exactly.

        Returns:
            {
                feature_vector:   {channel: float},
                dominant_channels: [(channel, float), ...],   # sorted DESC
                severity:          float,
                fault_detected:    bool,
            }
            or None
        """
        # Boost probability when fault is active
        prob = self.sig_prob
        if self._active_fault:
            prob = min(0.9, prob * 4.0)

        if random.random() > prob:
            return None

        # feature_vector = absolute residuals (what M1's ResidualEngine does)
        feature_vector = {
            ch: round(abs(self._last_residuals.get(ch, 0.0)), 4)
            for ch in RESIDUAL_CHANNELS
        }

        # dominant_channels: sorted by magnitude DESC (M1 already sorts these)
        dominant_channels = sorted(
            feature_vector.items(),
            key=lambda x: x[1],
            reverse=True,
        )

        severity      = min(1.0, round(self._last_composite, 4))
        fault_detected = self._active_fault is not None or self._last_composite > 0.35

        return {
            "feature_vector":    feature_vector,
            "dominant_channels": dominant_channels,   # list of (str, float) tuples
            "severity":          severity,
            "fault_detected":    fault_detected,
        }

    def get_raw(self) -> tuple[dict, dict]:
        """
        Return (predicted, actual) raw dicts (Payload 3).
        Call after next_tick() to get the values for that tick.

        Returns:
            (predicted_dict, actual_dict)  — each has 10 fields:
            {timestamp, rpm, cht, egt, oil_pressure, oil_temp,
             fuel_flow, vibration_amplitude, vibration_freq, throttle_cmd}
        """
        # Include throttle_cmd in the raw dicts (not in residuals)
        pred = dict(self._last_predicted)
        act  = dict(self._last_actual)

        # Ensure throttle_cmd is present
        if "throttle_cmd" not in pred:
            lo, hi, _ = _CHANNEL_RANGES["throttle_cmd"]
            pred["throttle_cmd"] = round(random.uniform(lo, hi), 3)
            act["throttle_cmd"]  = round(pred["throttle_cmd"] + random.gauss(0, 0.02), 3)

        return pred, act

    # ── Fault injection controls ──────────────────────────────────────────────

    def inject_fault(self, fault_type: str):
        """
        Inject a named fault into the actual-value stream.

        Args:
            fault_type: one of FAULT_TYPES
                        ('overheating', 'oil_pressure_drop', 'misfire',
                         'injector_fault', 'vibration_spike')
        """
        if fault_type not in _FAULT_PROFILES:
            raise ValueError(f"Unknown fault type: {fault_type!r}. "
                             f"Choose from {FAULT_TYPES}")
        self._active_fault  = fault_type
        self._fault_age     = 0
        self._fault_cleared = False

    def clear_fault(self):
        """Return the engine to healthy baseline (no active fault)."""
        self._active_fault  = None
        self._fault_age     = 0
        self._fault_cleared = True

    @property
    def active_fault(self) -> Optional[str]:
        return self._active_fault

    @property
    def tick_count(self) -> int:
        return self._tick_count

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _compute_predicted(self, now: float) -> dict:
        """
        Analytical 'healthy' model output — slow sinusoidal drift mimics
        real engine warm-up / load variation without needing M1's physics.
        Block E: scenario_params (altitude, ambient_temp, throttle_demand)
        shift the baseline values to reflect operating environment.
        On Day 2, this is replaced by M1's real predicted dict.
        """
        t = now - self._t0
        values = {}
        for ch in RESIDUAL_CHANNELS:
            lo, hi, _ = _CHANNEL_RANGES[ch]
            mid   = (lo + hi) / 2.0
            amp   = (hi - lo) / 2.0
            # Slow drift: different frequency per channel so they look independent
            freq  = 0.03 + RESIDUAL_CHANNELS.index(ch) * 0.007
            drift = math.sin(2 * math.pi * freq * t) * amp * 0.3
            # Block E: add scenario baseline offset
            scenario_shift = self._scenario_offsets.get(ch, 0.0)
            values[ch] = round(mid + drift + scenario_shift, 4)
        return values

    def _compute_actual(self, predicted: dict) -> dict:
        """
        Actual = predicted + Gaussian noise + fault bias (if active).
        Block E: noise is scaled by throttle_demand (more demand → wider readings).
        On Day 2, this is replaced by M1/M2's real actual stream.
        """
        actual = {}
        for ch in RESIDUAL_CHANNELS:
            lo, hi, _ = _CHANNEL_RANGES[ch]
            sigma = (hi - lo) * self.noise_sigma * self._scenario_noise_scale
            noise = random.gauss(0.0, sigma)

            fault_offset = self._get_fault_offset(ch)
            actual[ch] = round(predicted[ch] + noise + fault_offset, 4)

        return actual

    def _get_fault_offset(self, channel: str) -> float:
        """Compute fault bias for a channel, ramped up over fault_ramp_ticks."""
        if not self._active_fault:
            return 0.0

        profile = _FAULT_PROFILES[self._active_fault]
        if channel not in profile:
            return 0.0

        additive, multiplicative = profile[channel]

        # Ramp factor: 0.0 → 1.0 over fault_ramp_ticks
        ramp = min(1.0, self._fault_age / max(1, self.fault_ramp_ticks))

        return additive * multiplicative * ramp

    def _compute_composite(self, residuals: dict) -> float:
        """
        Composite score = weighted RMS of normalised residuals.
        Score is 0.0 when healthy; exceeds 0.35 on significant faults.
        Mirrors M1's ResidualEngine.composite_score logic.
        """
        # Channel weights (higher = more sensitive to that channel's deviation)
        weights = {
            "rpm":                 1.0,
            "cht":                 1.2,
            "egt":                 1.5,   # most sensitive
            "oil_pressure":        1.8,   # highest priority
            "oil_temp":            1.0,
            "fuel_flow":           0.8,
            "vibration_amplitude": 1.3,
            "vibration_freq":      0.6,
        }

        total_sq  = 0.0
        total_w   = 0.0
        for ch, residual in residuals.items():
            lo, hi, _ = _CHANNEL_RANGES[ch]
            channel_range = max(hi - lo, 1e-6)
            normalised    = residual / channel_range      # dimensionless
            w             = weights.get(ch, 1.0)
            total_sq     += w * (normalised ** 2)
            total_w      += w

        rms = math.sqrt(total_sq / max(total_w, 1e-6))
        return round(rms, 6)


# ── Convenience: one-shot generators (for testing / notebook use) ─────────────

def generate_tick(engine: Optional["MockEngine"] = None) -> dict:
    """Return a single per-tick residual payload from a shared engine."""
    global _shared_engine
    if engine is None:
        if "_shared_engine" not in globals() or _shared_engine is None:
            globals()["_shared_engine"] = MockEngine()
        engine = globals()["_shared_engine"]
    return engine.next_tick()


def generate_signature(engine: Optional["MockEngine"] = None) -> Optional[dict]:
    """Return a signature payload (or None) from a shared engine."""
    global _shared_engine
    if engine is None:
        engine = globals().get("_shared_engine")
        if engine is None:
            return None
    return engine.get_signature()


def generate_mock_alert_log(
    n_ticks: int = 80,
    fault_at: Optional[int] = None,
    fault_type: str = "overheating",
    noise_sigma: float = 0.015,
) -> list[dict]:
    """
    Run a fresh MockEngine and collect every signature where fault_detected=True.

    Returns a chronologically sorted list of alert entries:
        [
            {
                "tick":               int,
                "timestamp":          float   (Unix time),
                "severity":           float   (0.0–1.0),
                "fault_type":         str     (human-readable label),
                "composite_score":    float   (0.0–1.0+),
                "dominant_channels":  [(channel, float), ...]   # top 2
            },
            ...
        ]

    The list may be empty if no fault_detected events were generated (e.g.
    healthy engine with no fault injection).

    Usage:
        from utils.mock_data import generate_mock_alert_log
        alerts = generate_mock_alert_log(n_ticks=80, fault_at=25, fault_type="overheating")
    """
    engine = MockEngine(noise_sigma=noise_sigma, signature_probability=0.30)
    alerts: list[dict] = []

    # Determine human-readable fault label
    fault_label = (fault_type.replace("_", " ").title()) if fault_at else "Unknown"

    for tick in range(1, n_ticks + 1):
        if fault_at and tick == fault_at:
            engine.inject_fault(fault_type)

        tick_payload = engine.next_tick()
        sig = engine.get_signature()

        if sig and sig.get("fault_detected"):
            alerts.append({
                "tick":              tick,
                "timestamp":         tick_payload["timestamp"],
                "severity":          sig["severity"],
                "fault_type":        fault_label,
                "composite_score":   tick_payload["composite_score"],
                "dominant_channels": sig["dominant_channels"][:2],  # top 2
            })

    return alerts


# ── Self-test ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json

    engine = MockEngine(tick_rate_hz=2.0)

    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace") if hasattr(sys.stdout, "reconfigure") else None
    print("=" * 60)
    print("MOCK ENGINE SELF-TEST")
    print("="  * 60)

    # ── 3 healthy ticks ───────────────────────────────────────────
    print("\n[1] HEALTHY TICKS (×3)")
    for i in range(3):
        tick = engine.next_tick()
        print(f"  tick {i+1}: composite_score={tick['composite_score']:.4f} "
              f"| egt_residual={tick['residuals']['egt']:.4f}")

    # ── Signature (may be None in healthy state) ──────────────────
    print("\n[2] SIGNATURE (healthy state)")
    sig = engine.get_signature()
    print(f"  {json.dumps(sig, indent=4) if sig else 'None (no fault, low probability)'}")

    # ── Raw predicted vs actual ───────────────────────────────────
    print("\n[3] RAW PREDICTED / ACTUAL")
    pred, actual = engine.get_raw()
    for ch in list(pred.keys())[:4]:
        print(f"  {ch:22s} pred={pred[ch]:.2f}  actual={actual.get(ch, '?'):.2f}")

    # ── Inject overheating fault ──────────────────────────────────
    print("\n[4] INJECT 'overheating' FAULT")
    engine.inject_fault("overheating")
    for i in range(5):
        tick = engine.next_tick()
        sig  = engine.get_signature()
        print(f"  tick {i+1}: composite={tick['composite_score']:.4f} "
              f"| egt_res={tick['residuals']['egt']:.2f} "
              f"| fault_detected={sig['fault_detected'] if sig else '?'}")

    # ── Full signature on faulted state ──────────────────────────
    print("\n[5] SIGNATURE (overheating active)")
    engine._fault_age = engine.fault_ramp_ticks  # force full ramp
    engine.next_tick()
    sig = engine.get_signature()
    if sig:
        print(f"  severity:       {sig['severity']}")
        print(f"  fault_detected: {sig['fault_detected']}")
        print(f"  dominant_channels (top 3):")
        for ch, val in sig["dominant_channels"][:3]:
            print(f"    {ch:22s} {val:.4f}")

    # ── Clear fault ───────────────────────────────────────────────
    print("\n[6] CLEAR FAULT")
    engine.clear_fault()
    tick = engine.next_tick()
    print(f"  composite_score after clear: {tick['composite_score']:.4f} (expect near 0)")

    print("\n[OK] All payloads match M1 schema. Ready for Day 2 integration.\n")
