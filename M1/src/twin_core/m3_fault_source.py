"""
m3_fault_source.py — M3 Fault Injection Adapter for M1 Digital Twin
====================================================================
Integrates M3's real physical fault generator directly into M1.
Replaces the temporary dummy `_dev_fault_stub.py`.

Uses:
  - M3 generator.fault_injection: FaultManager, MisfireFault, OverheatingFault,
    OilPressureDropFault, InjectorFault, VibrationSpikeFault, NoOpFault
"""

from __future__ import annotations

import copy
import os
import sys
from typing import Dict, List, Optional

# Ensure M3 is on sys.path
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
_M3_DIR = os.path.join(_REPO_ROOT, "M3")
if _M3_DIR not in sys.path:
    sys.path.insert(0, _M3_DIR)

from generator.fault_injection import (
    FaultManager,
    FaultScenario,
    MisfireFault,
    OverheatingFault,
    OilPressureDropFault,
    InjectorFault,
    VibrationSpikeFault,
    NoOpFault,
)
from twin_core.dynamics import EngineSimulator


# Concrete extensions for additional DRDO SIH fault scenarios
class FuelMixtureDriftFault(FaultScenario):
    """Simulate fuel metering valve drift skewing air-fuel mixture."""
    def __init__(self, start_time_s: float = 0.0, duration_s: Optional[float] = None, drift_rate: float = 0.40):
        super().__init__(name="fuel_mixture_drift", start_time_s=start_time_s, duration_s=duration_s)
        self.drift_rate = drift_rate

    def apply(self, t_s: float, healthy_values: dict[str, float]) -> dict[str, float]:
        values = copy.deepcopy(healthy_values)
        elapsed = self.elapsed_since_start(t_s)
        scale = 1.0 + self.drift_rate * (1.0 - 2.71828 ** (-elapsed / 8.0))
        if "fuel_flow" in values:
            values["fuel_flow"] *= scale
        if "fuel_flow_lph" in values:
            values["fuel_flow_lph"] *= scale
        if "egt" in values:
            values["egt"] += 60.0 * (scale - 1.0)
        if "egt_c" in values:
            values["egt_c"] += 60.0 * (scale - 1.0)
        return values


class CoolingBaffleFault(FaultScenario):
    """Simulate cooling baffle seal degradation reducing cylinder head airflow."""
    def __init__(self, start_time_s: float = 0.0, duration_s: Optional[float] = None):
        super().__init__(name="cooling_system_fault", start_time_s=start_time_s, duration_s=duration_s)

    def apply(self, t_s: float, healthy_values: dict[str, float]) -> dict[str, float]:
        values = copy.deepcopy(healthy_values)
        elapsed = self.elapsed_since_start(t_s)
        cht_rise = 75.0 * (1.0 - 2.71828 ** (-elapsed / 10.0))
        if "cht" in values:
            values["cht"] += cht_rise
        if "cht_c" in values:
            values["cht_c"] += cht_rise
        return values


class EngineOverspeedFault(FaultScenario):
    """Simulate propeller governor runaway driving engine overspeed excursion."""
    def __init__(self, start_time_s: float = 0.0, duration_s: Optional[float] = None, rpm_boost: float = 400.0):
        super().__init__(name="engine_overspeed", start_time_s=start_time_s, duration_s=duration_s)
        self.rpm_boost = rpm_boost

    def apply(self, t_s: float, healthy_values: dict[str, float]) -> dict[str, float]:
        values = copy.deepcopy(healthy_values)
        if "rpm" in values:
            values["rpm"] += self.rpm_boost
        return values


FAULT_PROFILES: Dict[str, str] = {
    "misfire": "Intermittent cylinder misfire with RPM dips and vibration surges",
    "injector_fault": "Fuel injector delivery imbalance with lean burn and EGT divergence",
    "overheating": "Thermal runaway with progressive CHT and EGT elevation",
    "oil_pressure_drop": "Hydraulic oil pressure loss and scavenge temperature rise",
    "vibration_spike": "Mechanical bearing wear and rotational harmonic vibration spike",
    "fuel_mixture_drift": "Fuel metering valve drift skewing air-fuel ratio",
    "cooling_system_fault": "Baffle seal degradation reducing airflow cooling efficiency",
    "engine_overspeed": "Propeller governor fault driving high-RPM excursion",
}


def create_m3_fault(fault_type: str, fault_time_s: float) -> FaultScenario:
    """Instantiate concrete M3 fault model based on fault_type identifier."""
    ft = fault_type.lower()
    if ft in ("misfire", "misfire_or_injector_fault"):
        return MisfireFault(start_time_s=fault_time_s)
    elif ft == "injector_fault":
        return InjectorFault(start_time_s=fault_time_s)
    elif ft in ("overheating", "overheat"):
        return OverheatingFault(start_time_s=fault_time_s)
    elif ft in ("oil_pressure_drop", "oil_pressure_loss"):
        return OilPressureDropFault(start_time_s=fault_time_s)
    elif ft in ("vibration_spike", "vibration_bearing_fault"):
        return VibrationSpikeFault(start_time_s=fault_time_s)
    elif ft == "fuel_mixture_drift":
        return FuelMixtureDriftFault(start_time_s=fault_time_s)
    elif ft in ("cooling_system_fault", "cooling_baffle_fault"):
        return CoolingBaffleFault(start_time_s=fault_time_s)
    elif ft in ("engine_overspeed", "overspeed"):
        return EngineOverspeedFault(start_time_s=fault_time_s)
    else:
        return OverheatingFault(start_time_s=fault_time_s)


class FaultedSimulator:
    """EngineSimulator wrapper powered by M3 physical fault models."""

    def __init__(
        self,
        fault_type: str = "overheating",
        fault_time: float = 30.0,
        ambient_temp: float = 25.0,
        seed: Optional[int] = 99,
    ) -> None:
        self._sim = EngineSimulator(ambient_temp=ambient_temp, seed=seed)
        self._fault_type = fault_type
        self._fault_time = fault_time
        
        # Initialize M3 FaultManager with genuine M3 physical fault
        m3_fault = create_m3_fault(fault_type, fault_time)
        self._fault_mgr = FaultManager([m3_fault])
        self._active = False

    def step(self, throttle_cmd: float, dt: float) -> dict:
        """Step simulator and apply real M3 fault models with bidirectional channel mapping."""
        reading = self._sim.step(throttle_cmd, dt)
        t_s = reading["timestamp"]

        # Adapt M1 channel names to M3 expectations
        m3_input = copy.deepcopy(reading)
        m3_input["cht_c"] = reading.get("cht", 160.0)
        m3_input["egt_c"] = reading.get("egt", 620.0)
        m3_input["oil_temp_c"] = reading.get("oil_temp", 95.0)
        m3_input["oil_pressure_kpa"] = reading.get("oil_pressure", 45.0) * 6.89476
        m3_input["fuel_flow_lph"] = reading.get("fuel_flow", 22.0)
        m3_input["vibration_g"] = reading.get("vibration_amplitude", 0.8)

        # Apply M3 fault injection
        modified = self._fault_mgr.apply_all(t_s, m3_input)
        self._active = bool(self._fault_mgr.active_scenarios(t_s))

        # Map back to M1 schema
        reading["rpm"] = modified["rpm"]
        reading["cht"] = modified["cht_c"]
        reading["egt"] = modified["egt_c"]
        reading["oil_temp"] = modified["oil_temp_c"]
        reading["oil_pressure"] = modified["oil_pressure_kpa"] / 6.89476
        reading["fuel_flow"] = modified["fuel_flow_lph"]
        reading["vibration_amplitude"] = modified["vibration_g"]

        return reading

    @property
    def fault_type(self) -> str:
        return self._fault_type

    @property
    def is_active(self) -> bool:
        return self._active
