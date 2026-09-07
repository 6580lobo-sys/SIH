"""Environment profiles for the telemetry generator.

Defines standard flight-condition presets that feed ``altitude_m`` and
``ambient_temp_c`` into the signal models, so every generated dataset
can be tagged with a reproducible environmental scenario.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EnvironmentProfile:
    """Immutable snapshot of the environmental conditions for a flight."""

    altitude_m: float
    ambient_temp_c: float


# ── Presets ──────────────────────────────────────────────────────────────────

ENVIRONMENT_PRESETS: dict[str, EnvironmentProfile] = {
    "standard_day": EnvironmentProfile(altitude_m=500, ambient_temp_c=25),
    "hot_day":      EnvironmentProfile(altitude_m=500, ambient_temp_c=42),
    "high_altitude": EnvironmentProfile(altitude_m=4500, ambient_temp_c=10),
    "hot_and_high": EnvironmentProfile(altitude_m=4500, ambient_temp_c=38),
}


# ── Accessor ────────────────────────────────────────────────────────────────

def get_environment(name: str) -> EnvironmentProfile:
    """Look up a preset by name, raising a clear error if not found.

    Parameters
    ----------
    name : str
        One of the keys in :data:`ENVIRONMENT_PRESETS`.

    Raises
    ------
    KeyError
        If *name* does not match any preset.  The error message lists
        all valid names so the caller can fix typos quickly.
    """
    try:
        return ENVIRONMENT_PRESETS[name]
    except KeyError:
        valid = ", ".join(sorted(ENVIRONMENT_PRESETS))
        raise KeyError(
            f"Unknown environment preset '{name}'. "
            f"Valid presets: {valid}"
        ) from None


# ── Quick demo ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"{'Preset':<18s}  {'Altitude (m)':>14s}  {'Ambient (C)':>12s}")
    print("-" * 50)
    for name, profile in ENVIRONMENT_PRESETS.items():
        print(
            f"{name:<18s}  {profile.altitude_m:>14.0f}  "
            f"{profile.ambient_temp_c:>12.1f}"
        )
