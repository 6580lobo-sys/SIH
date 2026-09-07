"""Healthy-baseline signal generators for each engine telemetry channel.

Every function returns a single scalar sample for one time-step.  The
relationships are simplified but *physically plausible* — higher throttle
drives higher RPM, which in turn raises temperatures, fuel flow, and
vibration.  Gaussian noise is added via numpy and outputs are clipped to
the valid ranges defined in ``schema.telemetry_schema``.

Environmental coupling
----------------------
``altitude_m`` and ``ambient_temp_c`` are first-class inputs:

*   **Altitude** affects air density, reducing effective engine power
    (RPM sag, fuel flow drop) and oil pump output at higher elevations.
*   **Ambient temperature** shifts the thermal baseline for CHT and EGT
    (hotter day → hotter engine).
"""

from __future__ import annotations

import numpy as np


# ── Altitude derating helper ────────────────────────────────────────────────

def _altitude_derating(altitude_m: float) -> float:
    """Return a multiplicative derating factor (0–1) for altitude.

    Physical reasoning: air density drops ~3 % per 1 000 m of altitude gain
    (simplified ISA model).  A normally-aspirated piston engine loses power
    roughly proportionally to the drop in air density, so we apply a linear
    derating of 3 % per 1 000 m.

    Examples::

        sea level  →  1.00  (no derating)
        4 000 m    →  0.88  (−12 %)
        8 000 m    →  0.76  (−24 %)
    """
    return max(0.5, 1.0 - 0.03 * (altitude_m / 1000.0))


# ── RPM ──────────────────────────────────────────────────────────────────

def healthy_rpm(throttle_pct: float, altitude_m: float = 0.0,
                noise_std: float = 20.0) -> float:
    """Map throttle (0-100 %) to RPM via a linear-ish relationship.

    Idle ≈ 800 rev/min, full throttle ≈ 5 800 rev/min.

    Higher altitude → thinner air → less power at same throttle.
    """
    base = 800 + (throttle_pct / 100.0) * 5000
    # Altitude derating: thinner air reduces volumetric efficiency
    base *= _altitude_derating(altitude_m)
    return float(np.clip(base + np.random.normal(0, noise_std), 0, 10_000))


# ── Cylinder Head Temperature ────────────────────────────────────────────

def healthy_cht(rpm: float, ambient_temp_c: float = 25.0,
                noise_std: float = 1.5) -> float:
    """CHT rises roughly linearly with RPM above ambient.

    At idle (~800 rpm) expect ~100 °C; at 5 800 rpm expect ~220 °C.
    Hotter ambient air → higher baseline CHT (less cooling ΔT).
    """
    # Ambient directly lifts the thermal floor of the cylinder head
    base = ambient_temp_c + 75 + (rpm / 5800) * 120
    return float(np.clip(base + np.random.normal(0, noise_std), -40, 500))


# ── Exhaust Gas Temperature ─────────────────────────────────────────────

def healthy_egt(rpm: float, throttle_pct: float,
                ambient_temp_c: float = 25.0,
                noise_std: float = 3.0) -> float:
    """EGT depends on both RPM and throttle (fuel-air mixture richness).

    Typical cruise band: 500-750 °C.
    Hotter intake air → hotter combustion → higher EGT.
    """
    # Ambient contributes ~0.6× to exhaust temp (attenuated by combustion)
    ambient_offset = (ambient_temp_c - 25.0) * 0.6
    base = 350 + (rpm / 5800) * 250 + (throttle_pct / 100) * 100 + ambient_offset
    return float(np.clip(base + np.random.normal(0, noise_std), -40, 1000))


# ── Oil Pressure ─────────────────────────────────────────────────────────

def healthy_oil_pressure(rpm: float, altitude_m: float = 0.0,
                         noise_std: float = 2.0) -> float:
    """Oil pressure is pump-driven; rises with RPM then plateaus.

    Idle ≈ 200 kPa, cruise ≈ 400-500 kPa.
    Higher altitude → slightly lower oil pressure (pump draws through
    thinner air-oil mist in the crankcase, mild cavitation effect).
    """
    base = 180 + (rpm / 5800) * 300
    # ~1.5 % drop per 1 000 m — milder than the power derating
    alt_factor = max(0.85, 1.0 - 0.015 * (altitude_m / 1000.0))
    base *= alt_factor
    return float(np.clip(base + np.random.normal(0, noise_std), 0, 1000))


# ── Oil Temperature ──────────────────────────────────────────────────────

def healthy_oil_temp(cht_c: float, noise_std: float = 1.0) -> float:
    """Oil temp tracks CHT but sits ~15-25 °C lower."""
    base = cht_c - 20
    return float(np.clip(base + np.random.normal(0, noise_std), -40, 250))


# ── Fuel Flow ────────────────────────────────────────────────────────────

def healthy_fuel_flow(rpm: float, throttle_pct: float,
                      altitude_m: float = 0.0,
                      noise_std: float = 0.3) -> float:
    """Fuel flow (L/h) increases with RPM and throttle.

    Idle ≈ 5 L/h, full power ≈ 40 L/h.
    Higher altitude → less air → ECU leans the mixture → less fuel.
    """
    base = 3 + (rpm / 5800) * 25 + (throttle_pct / 100) * 12
    # Fuel flow tracks the power derating (engine ingests less air)
    base *= _altitude_derating(altitude_m)
    return float(np.clip(base + np.random.normal(0, noise_std), 0, 200))


# ── Vibration ────────────────────────────────────────────────────────────

def healthy_vibration(rpm: float, noise_std: float = 0.02) -> float:
    """Vibration (g) has a mild quadratic relationship with RPM.

    Normal band: 0.1 – 0.6 g.
    """
    normalised_rpm = rpm / 5800
    base = 0.1 + 0.4 * normalised_rpm ** 2
    return float(np.clip(base + np.random.normal(0, noise_std), 0, 50))


# ── Convenience: generate a full healthy sample dict ─────────────────────

def healthy_sample(throttle_pct: float,
                   altitude_m: float = 0.0,
                   ambient_temp_c: float = 25.0) -> dict[str, float]:
    """Return a dict of all sensor values for one time-step.

    Parameters
    ----------
    throttle_pct : float
        Throttle position (0–100 %).
    altitude_m : float
        Aircraft altitude in metres above sea level.
    ambient_temp_c : float
        Outside air temperature in degrees Celsius.
    """
    rpm   = healthy_rpm(throttle_pct, altitude_m)
    cht   = healthy_cht(rpm, ambient_temp_c)
    egt   = healthy_egt(rpm, throttle_pct, ambient_temp_c)
    oil_p = healthy_oil_pressure(rpm, altitude_m)
    oil_t = healthy_oil_temp(cht)
    fuel  = healthy_fuel_flow(rpm, throttle_pct, altitude_m)
    vib   = healthy_vibration(rpm)
    return {
        "rpm": rpm,
        "cht_c": cht,
        "egt_c": egt,
        "oil_pressure_kpa": oil_p,
        "oil_temp_c": oil_t,
        "fuel_flow_lph": fuel,
        "vibration_g": vib,
        "throttle_pct": throttle_pct,
        "ambient_temp_c": ambient_temp_c,
    }


# ── Quick demo ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    np.random.seed(42)

    conditions = [
        ("Sea level, cool (15 C)",  0,    15.0),
        ("Sea level, hot  (40 C)",  0,    40.0),
        ("4 000 m,   cool (15 C)",  4000, 15.0),
        ("4 000 m,   hot  (40 C)",  4000, 40.0),
    ]

    throttle = 70.0
    header = f"{'Field':<20s}"
    for label, _, _ in conditions:
        header += f"  {label:>26s}"
    print(f"Healthy samples @ throttle = {throttle} %\n")
    print(header)
    print("-" * len(header))

    # Collect samples
    samples = []
    for _, alt, amb in conditions:
        np.random.seed(42)  # same noise seed for fair comparison
        samples.append(healthy_sample(throttle, altitude_m=alt,
                                      ambient_temp_c=amb))

    # Print comparison table
    for key in samples[0]:
        row = f"{key:<20s}"
        for s in samples:
            row += f"  {s[key]:>26.2f}"
        print(row)
