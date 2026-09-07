"""Throttle profile generators for the telemetry simulator.

Each profile maps elapsed simulation time to a throttle percentage (0–100 %).
Use :func:`generate_throttle_profile` as the single entry-point; it
dispatches to the correct profile function based on the *mode* string.

Available modes
---------------
``"smooth"``
    Slow sine wave between 20 % and 90 % (30 s period).  Represents a
    steady cruise with gentle power changes.

``"rapid_transient"``
    Baseline cruise at ~45 %, punctuated by 2–3 abrupt step-ups to
    90–100 % held for a few seconds each (simulating dash / climb
    manoeuvres), then stepping back down.

``"idle_to_cruise"``
    Starts near idle (~15 %), ramps linearly over ~5 s to cruise
    (~60 %), then holds.  Represents a ground run-up or takeoff roll.
"""

from __future__ import annotations

import math


# ── Profile functions ───────────────────────────────────────────────────────

def _smooth(t_s: float) -> float:
    """Slow sine wave between 20 % and 90 % (30 s period)."""
    mid = 55.0
    amp = 35.0
    period_s = 30.0
    return mid + amp * math.sin(2 * math.pi * t_s / period_s)


def _rapid_transient(t_s: float) -> float:
    """Cruise at ~45 % with 3 abrupt dash/climb step-ups.

    Burst windows (chosen to be distinct and non-overlapping):
        t ∈ [5, 8)   → 95 %   (3 s burst)
        t ∈ [15, 18) → 100 %  (3 s burst)
        t ∈ [24, 26) → 90 %   (2 s burst)

    Outside these windows the throttle sits at a gentle cruise with
    a small amount of wander (±3 %) so the baseline isn't unnaturally flat.
    """
    bursts: list[tuple[float, float, float]] = [
        # (start_s, end_s, throttle_pct)
        (5.0,  8.0,  95.0),
        (15.0, 18.0, 100.0),
        (24.0, 26.0, 90.0),
    ]
    for start, end, pct in bursts:
        if start <= t_s < end:
            return pct

    # Baseline cruise with a tiny wander
    return 45.0 + 3.0 * math.sin(t_s * 0.4)


def _idle_to_cruise(t_s: float) -> float:
    """Start near idle (~15 %), ramp to cruise (~60 %) over 5 s, then hold.

    The ramp is linear for simplicity.  After reaching cruise the
    throttle stays constant (no further transients).
    """
    idle = 15.0
    cruise = 60.0
    ramp_duration = 5.0

    if t_s < 0:
        return idle
    if t_s < ramp_duration:
        # Linear ramp from idle to cruise
        return idle + (cruise - idle) * (t_s / ramp_duration)
    return cruise


# ── Registry ────────────────────────────────────────────────────────────────

_PROFILES: dict[str, type] = {
    "smooth":           _smooth,
    "rapid_transient":  _rapid_transient,
    "idle_to_cruise":   _idle_to_cruise,
}

AVAILABLE_MODES: list[str] = sorted(_PROFILES.keys())


# ── Public API ──────────────────────────────────────────────────────────────

def generate_throttle_profile(t_s: float, mode: str = "smooth") -> float:
    """Return the throttle percentage at simulation time *t_s*.

    Parameters
    ----------
    t_s : float
        Elapsed simulation time in seconds.
    mode : str
        One of :data:`AVAILABLE_MODES`.

    Raises
    ------
    KeyError
        If *mode* is not a known profile name.
    """
    try:
        fn = _PROFILES[mode]
    except KeyError:
        valid = ", ".join(AVAILABLE_MODES)
        raise KeyError(
            f"Unknown throttle mode '{mode}'. Valid modes: {valid}"
        ) from None
    return float(max(0.0, min(100.0, fn(t_s))))


# ── Quick demo ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    duration = 30.0
    dt = 0.1
    n = int(duration / dt)

    print(f"Throttle profiles over {duration:.0f} s  (dt = {dt} s)\n")

    header = f"{'t (s)':>7s}"
    for mode in AVAILABLE_MODES:
        header += f"  {mode:>18s}"
    print(header)
    print("-" * len(header))

    for i in range(n + 1):
        t = i * dt
        if i % 10 == 0:  # print every 1 second
            row = f"{t:7.1f}"
            for mode in AVAILABLE_MODES:
                val = generate_throttle_profile(t, mode)
                row += f"  {val:18.1f}"
            print(row)

    # ASCII sparkline visualisation for each mode
    print("\n" + "=" * 70)
    print("  ASCII sparklines (each char = 1 second)")
    print("=" * 70)

    SPARK_CHARS = " _.-~*#@"

    for mode in AVAILABLE_MODES:
        line = f"  {mode:<18s} |"
        for sec in range(int(duration)):
            val = generate_throttle_profile(float(sec), mode)
            # Map 0-100% to index 0-7
            idx = min(len(SPARK_CHARS) - 1, int(val / 100 * len(SPARK_CHARS)))
            line += SPARK_CHARS[idx]
        line += "|"
        print(line)

    print(f"\n  Legend: ' '=0%  '_'=~15%  '.'=~25%  '-'=~40%  "
          f"'~'=~55%  '*'=~70%  '#'=~85%  '@'=100%")
