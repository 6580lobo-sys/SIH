"""Generator package — baseline signal models and fault injection."""

from .signal_models import (
    healthy_cht,
    healthy_egt,
    healthy_fuel_flow,
    healthy_oil_pressure,
    healthy_oil_temp,
    healthy_rpm,
    healthy_sample,
    healthy_vibration,
)
from .fault_models import apply_faults
from .fault_injection import (
    FaultManager,
    FaultScenario,
    InjectorFault,
    MisfireFault,
    NoOpFault,
    OilPressureDropFault,
    OverheatingFault,
    VibrationSpikeFault,
)

__all__ = [
    "healthy_rpm",
    "healthy_cht",
    "healthy_egt",
    "healthy_oil_pressure",
    "healthy_oil_temp",
    "healthy_fuel_flow",
    "healthy_vibration",
    "healthy_sample",
    "apply_faults",
    "FaultScenario",
    "FaultManager",
    "InjectorFault",
    "MisfireFault",
    "NoOpFault",
    "OilPressureDropFault",
    "OverheatingFault",
    "VibrationSpikeFault",
]
