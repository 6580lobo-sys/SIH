"""Fault injection models for the aero piston engine.

These functions take a healthy telemetry sample (dict) and apply 
physically plausible modifications to simulate various engine faults.
"""

from __future__ import annotations

import copy
import numpy as np


def apply_faults(
    healthy_sample: dict[str, float],
    active_faults: list[str],
    elapsed_fault_time_s: float = 0.0,
) -> dict[str, float]:
    """Apply a list of active faults to a healthy telemetry sample.
    
    Parameters
    ----------
    healthy_sample : dict[str, float]
        The baseline healthy sensor readings.
    active_faults : list[str]
        List of fault string identifiers, e.g., ["oil_pressure_drop", "overheat"].
    elapsed_fault_time_s : float
        How long the fault has been active (used for progressive faults).
        
    Returns
    -------
    dict[str, float]
        A new dictionary with the fault modifiers applied.
    """
    faulted_sample = copy.deepcopy(healthy_sample)

    for fault in active_faults:
        if fault == "oil_pressure_drop":
            faulted_sample = _inject_oil_pressure_drop(faulted_sample)
        elif fault == "overheat":
            faulted_sample = _inject_overheat(faulted_sample, elapsed_fault_time_s)
        elif fault == "misfire":
            faulted_sample = _inject_misfire(faulted_sample)
        elif fault == "vibration_spike":
            faulted_sample = _inject_vibration_spike(faulted_sample)

    # Ensure values don't go below 0 where physically impossible
    for key in ["rpm", "oil_pressure_kpa", "fuel_flow_lph", "vibration_g"]:
        if faulted_sample[key] < 0:
            faulted_sample[key] = 0.0

    return faulted_sample


def _inject_oil_pressure_drop(sample: dict[str, float]) -> dict[str, float]:
    """Simulate a sudden loss of oil pressure (e.g., pump failure or leak).
    
    Drops oil pressure by ~80% and causes a gradual rise in CHT/Oil Temp.
    """
    sample["oil_pressure_kpa"] *= np.random.uniform(0.1, 0.25)
    
    # Secondary effects: slightly higher temps and vibration due to poor lubrication
    sample["cht_c"] += np.random.uniform(5, 15)
    sample["oil_temp_c"] += np.random.uniform(10, 25)
    sample["vibration_g"] += np.random.uniform(0.1, 0.3)
    
    return sample


def _inject_overheat(sample: dict[str, float], elapsed_s: float) -> dict[str, float]:
    """Simulate a cooling system degradation (e.g., blocked cooling fins).
    
    Temperatures rise progressively over time.
    """
    # Max temperature rise of +80C, asymptotic over 60 seconds
    temp_rise = 80.0 * (1 - np.exp(-elapsed_s / 20.0))
    
    sample["cht_c"] += temp_rise + np.random.normal(0, 1.0)
    sample["oil_temp_c"] += (temp_rise * 0.8) + np.random.normal(0, 0.5)
    
    # Slight power loss -> lower RPM for same throttle
    sample["rpm"] -= (temp_rise * 1.5)
    
    return sample


def _inject_misfire(sample: dict[str, float]) -> dict[str, float]:
    """Simulate an intermittent spark plug or coil failure.
    
    Characterized by sudden drops in RPM and EGT, and high vibration spikes.
    """
    # 30% chance per frame for a hard misfire event
    if np.random.rand() < 0.30:
        sample["rpm"] -= np.random.uniform(300, 800)
        sample["egt_c"] -= np.random.uniform(40, 100) # Unburnt fuel drops exhaust temp
        sample["vibration_g"] += np.random.uniform(1.0, 2.5) # Engine runs rough
        
    return sample


def _inject_vibration_spike(sample: dict[str, float]) -> dict[str, float]:
    """Simulate a loose mounting or unbalanced propeller."""
    sample["vibration_g"] += np.random.uniform(3.0, 6.0)
    return sample
