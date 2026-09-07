"""
engine_maps.py — Steady-state algebraic maps for a small aero piston engine.

Models a Rotax 912-class flat-four (~100 hp, 5800 RPM redline) used in
MALE UAV applications. Every function is pure and deterministic: given the
same inputs it always returns the same output. Noise, lag, and transient
dynamics belong in dynamics.py (Step 2), not here.

Reference operating ranges (from Rotax 912 ULS operator's manual and
general small aero piston data):
    RPM:            1400 – 5800
    CHT:            90 – 260 °C  (air-cooled cylinder head)
    EGT:            600 – 950 °C
    Oil pressure:   20 – 90 psi
    Oil temperature: 50 – 130 °C
    Fuel flow:      2 – 15 L/hr
"""


# ---------------------------------------------------------------------------
# Steady-state maps
# ---------------------------------------------------------------------------

def target_rpm(throttle: float) -> float:
    """Compute the steady-state RPM target for a given throttle setting.

    Simple affine map:
        idle (throttle=0)   → 1400 RPM
        full (throttle=100) → 5500 RPM

    Parameters
    ----------
    throttle : float
        Throttle command, 0–100 %.

    Returns
    -------
    float
        Target RPM.
    """
    return 1400.0 + 41.0 * throttle


def fuel_flow(rpm: float, throttle: float) -> float:
    """Fuel flow rate [L/hr].

    Roughly linear in throttle (injector opening) with a small RPM²
    pumping-loss / volumetric-efficiency term.

    Parameters
    ----------
    rpm : float
        Current engine RPM.
    throttle : float
        Throttle command, 0–100 %.

    Returns
    -------
    float
        Fuel flow in litres per hour.
    """
    return 1.8 + 0.095 * throttle + 1.5e-7 * rpm ** 2


def egt_steady(rpm: float, ff: float) -> float:
    """Exhaust gas temperature at steady state [°C].

    Driven by fuel flow (combustion energy) and RPM (mass flow / timing).

    Parameters
    ----------
    rpm : float
        Current engine RPM.
    ff : float
        Current fuel flow [L/hr] (output of :func:`fuel_flow`).

    Returns
    -------
    float
        EGT in degrees Celsius.
    """
    return 500.0 + 24.0 * ff + 0.009 * rpm


def cht_steady(rpm: float, ff: float, ambient_temp: float = 25.0) -> float:
    """Cylinder head temperature at steady state [°C].

    Driven by combustion heat (~fuel flow) minus cooling. Cooling is a
    function of airspeed which we stub as constant for the sprint.

    Parameters
    ----------
    rpm : float
        Current engine RPM.
    ff : float
        Current fuel flow [L/hr].
    ambient_temp : float, optional
        Ambient air temperature [°C].  Default 25 °C (ISA sea level).

    Returns
    -------
    float
        CHT in degrees Celsius.
    """
    return ambient_temp + 35.0 + 10.5 * ff + 0.007 * rpm


def oil_temp_steady(rpm: float, cht: float) -> float:
    """Oil temperature at steady state [°C].

    Driven by cylinder-head heat soak and friction (RPM²-ish).

    Parameters
    ----------
    rpm : float
        Current engine RPM.
    cht : float
        Current cylinder head temperature [°C].

    Returns
    -------
    float
        Oil temperature in degrees Celsius.
    """
    return 45.0 + 0.22 * cht + 3.5e-7 * rpm ** 2


def oil_pressure_steady(rpm: float, oil_temp: float) -> float:
    """Oil pressure at steady state [psi].

    Proportional to RPM (gear-driven pump) with a viscosity correction:
    hotter oil → thinner → lower pressure.

    Parameters
    ----------
    rpm : float
        Current engine RPM.
    oil_temp : float
        Current oil temperature [°C].

    Returns
    -------
    float
        Oil pressure in psi.
    """
    viscosity_factor = 1.0 - 0.004 * (oil_temp - 80.0)
    return (rpm / 5500.0) * 82.0 * viscosity_factor


# ---------------------------------------------------------------------------
# Convenience: compute all channels at once
# ---------------------------------------------------------------------------

def compute_all(throttle: float, rpm: float,
                ambient_temp: float = 25.0) -> dict:
    """Return all steady-state engine parameters as a dict.

    Evaluation order respects the causal chain:
        throttle/RPM → fuel_flow → EGT → CHT → oil_temp → oil_pressure

    Parameters
    ----------
    throttle : float
        Throttle command, 0–100 %.
    rpm : float
        Engine RPM.
    ambient_temp : float, optional
        Ambient temperature [°C].

    Returns
    -------
    dict
        Keys: rpm, fuel_flow, egt, cht, oil_temp, oil_pressure
    """
    ff = fuel_flow(rpm, throttle)
    egt = egt_steady(rpm, ff)
    cht = cht_steady(rpm, ff, ambient_temp)
    ot = oil_temp_steady(rpm, cht)
    op = oil_pressure_steady(rpm, ot)
    return {
        "rpm": rpm,
        "throttle": throttle,
        "fuel_flow_Lph": ff,
        "egt_C": egt,
        "cht_C": cht,
        "oil_temp_C": ot,
        "oil_pressure_psi": op,
    }


# ---------------------------------------------------------------------------
# Sanity-check printout
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 72)
    print("Steady-state engine maps — sanity check")
    print("Engine class: Rotax 912-type, ~100 hp, 5800 RPM redline")
    print("=" * 72)

    for throttle_pct in [20, 50, 90]:
        rpm = target_rpm(throttle_pct)
        vals = compute_all(throttle_pct, rpm)

        print(f"\n--- Throttle {throttle_pct:3d}% -> RPM {rpm:.0f} ---")
        print(f"  Fuel flow:     {vals['fuel_flow_Lph']:6.2f} L/hr")
        print(f"  EGT:           {vals['egt_C']:6.1f} deg C")
        print(f"  CHT:           {vals['cht_C']:6.1f} deg C")
        print(f"  Oil temp:      {vals['oil_temp_C']:6.1f} deg C")
        print(f"  Oil pressure:  {vals['oil_pressure_psi']:6.1f} psi")

    print("\n" + "=" * 72)
    print("Expected ranges:  RPM 1400-5800 | CHT 90-260 | EGT 600-950")
    print("                  Oil P 20-90 psi | Oil T 50-130 | FF 2-15 L/hr")
    print("=" * 72)
