"""
_dev_fault_stub.py — THROWAWAY / DEV-ONLY fault stub for smoke-testing
the residual engine before M2's real fault injector is integrated.

*** DELETE THIS FILE once M2's injector is wired in. ***

Supports all 5 fault types from the plan:
  1. misfire          — RPM jitter/drop, vibration spike, EGT dip
  2. injector_fault   — fuel flow drop, EGT rise (lean burn), slight RPM drop
  3. overheating      — CHT and EGT rise
  4. oil_pressure_drop — oil pressure drops sharply
  5. vibration_spike  — vibration amplitude surge, slight freq shift
"""

from typing import Dict, Optional

from twin_core.dynamics import EngineSimulator


# ---------------------------------------------------------------------------
# Fault profiles: per-channel additive offsets in native units.
# Designed so each fault produces a DISTINCT residual signature — not just
# "composite went up."
# ---------------------------------------------------------------------------

FAULT_PROFILES: Dict[str, Dict[str, float]] = {
    "misfire": {
        "rpm":                 -180.0,   # power loss from dead cylinder
        "egt":                  -40.0,   # less combustion → cooler exhaust
        "vibration_amplitude":   0.04,   # uneven firing → vibration spike
    },
    "injector_fault": {
        "fuel_flow":            -3.5,    # injector stuck/clogged → starved
        "egt":                  +80.0,   # lean burn → hotter exhaust
        "rpm":                  -90.0,   # slight power loss
    },
    "overheating": {
        "cht":                 +100.0,   # cooling failure → hot heads
        "egt":                 +120.0,   # heat propagates to exhaust
        "oil_temp":             +25.0,   # oil absorbs cylinder heat
    },
    "oil_pressure_drop": {
        "oil_pressure":         -35.0,   # pump degradation or leak
        "oil_temp":             +10.0,   # less flow → less cooling
    },
    "vibration_spike": {
        "vibration_amplitude":   0.06,   # bearing wear / imbalance
        "vibration_freq":       +15.0,   # harmonic shift from wear
    },
}


class FaultedSimulator:
    """EngineSimulator wrapper that injects a configurable fault.

    Parameters
    ----------
    fault_type : str
        One of the keys in :data:`FAULT_PROFILES`.
    fault_time : float
        Simulation time [s] at which the fault activates.
    ambient_temp : float
        Passed to the underlying :class:`EngineSimulator`.
    seed : int or None
        Random seed for the underlying simulator.
    """

    def __init__(self,
                 fault_type: str = "overheating",
                 fault_time: float = 30.0,
                 ambient_temp: float = 25.0,
                 seed: Optional[int] = 99):
        if fault_type not in FAULT_PROFILES:
            raise ValueError(
                f"Unknown fault type '{fault_type}'. "
                f"Choose from: {list(FAULT_PROFILES.keys())}"
            )
        self._sim = EngineSimulator(ambient_temp=ambient_temp, seed=seed)
        self._fault_type = fault_type
        self._offsets = FAULT_PROFILES[fault_type]
        self._fault_time = fault_time
        self._active = False

    def step(self, throttle_cmd: float, dt: float) -> dict:
        """Step the simulator, injecting fault offsets if past activation."""
        reading = self._sim.step(throttle_cmd, dt)

        if reading["timestamp"] >= self._fault_time:
            self._active = True
            for channel, offset in self._offsets.items():
                if channel in reading:
                    reading[channel] += offset

        return reading

    @property
    def fault_type(self) -> str:
        return self._fault_type


# ---------------------------------------------------------------------------
# Smoke test: run all 5 fault types and compare residual signatures
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from twin_core.twin import DigitalTwin
    from twin_core.residual import ResidualEngine

    DT = 0.1
    FAULT_TIME = 30.0
    DURATION = 50.0
    THROTTLE = 60.0  # steady cruise

    profile = [THROTTLE] * int(DURATION / DT)

    # Channels to display
    channels = ["rpm", "egt", "cht", "oil_pressure", "oil_temp",
                "fuel_flow", "vibration_amplitude", "vibration_freq"]

    print("=" * 110)
    print("Per-fault residual signatures (averaged over t=40-50s, post-fault)")
    print("=" * 110)

    # Header
    print(f"\n{'Fault Type':<22} {'Composite':>10}  ", end="")
    for ch in channels:
        label = ch[:8]
        print(f"{label:>10}", end="  ")
    print("\n" + "-" * 110)

    for fault_name in FAULT_PROFILES:
        faulted = FaultedSimulator(
            fault_type=fault_name,
            fault_time=FAULT_TIME,
            seed=99,
        )
        twin = DigitalTwin(actual_source=faulted.step)
        residual_eng = ResidualEngine()

        pairs = twin.run(profile, DT)
        results = residual_eng.process_batch(pairs)

        # Average residuals over post-fault window (t=40-50s)
        post = [r for r in results if 40.0 <= r["timestamp"] <= 50.0]
        n = len(post)
        avg_composite = sum(r["composite_score"] for r in post) / n
        avg_resid = {}
        for ch in channels:
            avg_resid[ch] = sum(
                r["residuals"].get(ch, 0.0) for r in post
            ) / n

        # Print row
        print(f"{fault_name:<22} {avg_composite:10.4f}  ", end="")
        for ch in channels:
            val = avg_resid[ch]
            # Mark dominant channels (|val| > 0.02)
            marker = " *" if abs(val) > 0.02 else "  "
            print(f"{val:+8.4f}{marker}", end="  ")
        print()

        # Print signature from ResidualEngine
        sig = residual_eng.signature()
        top = sig["dominant_channels"][:3]
        top_str = ", ".join(f"{ch}={v:+.4f}" for ch, v in top)
        print(f"{'':22} Signature: [{top_str}]")
        print()

    print("=" * 110)
    print("* = dominant channel for that fault (|residual| > 0.02)")
    print("\nExpected patterns:")
    print("  misfire         -> rpm*, vibration*, egt*")
    print("  injector_fault  -> fuel_flow*, egt*, rpm*")
    print("  overheating     -> cht*, egt*, oil_temp*")
    print("  oil_press_drop  -> oil_pressure*, oil_temp*")
    print("  vibration_spike -> vibration_amp*, vibration_freq*")
