"""Pydantic schema for a single CAN-like telemetry frame from a MALE UAV
aero piston engine.

Sampling rate assumption: 10 Hz (one message every 100 ms).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class EngineTelemetryMessage(BaseModel):
    """One CAN-like telemetry frame for the MALE UAV piston engine.

    Each instance represents a single snapshot of engine state captured at
    the given ``timestamp``.
    """

    timestamp: float = Field(
        ...,
        ge=0,
        description="Relative time in seconds from start of simulation.",
    )

    msg_id: str = Field(
        ...,
        min_length=1,
        description="CAN message identifier, e.g. 'ENG_TELEM_01'.",
    )

    rpm: float = Field(
        ...,
        ge=0,
        le=10_000,
        description="Engine speed in revolutions per minute (rev/min).",
    )

    cht: float = Field(
        ...,
        ge=-40,
        le=500,
        description="Cylinder Head Temperature in degrees Celsius.",
    )

    egt: float = Field(
        ...,
        ge=-40,
        le=1000,
        description="Exhaust Gas Temperature in degrees Celsius.",
    )

    oil_pressure: float = Field(
        ...,
        ge=0,
        le=150,
        description="Engine oil pressure in PSI.",
    )

    oil_temp: float = Field(
        ...,
        ge=-40,
        le=250,
        description="Engine oil temperature in degrees Celsius.",
    )

    fuel_flow: float = Field(
        ...,
        ge=0,
        le=200,
        description="Fuel flow rate in litres per hour (L/h).",
    )

    vibration_amplitude: float = Field(
        ...,
        ge=0,
        le=50,
        description="Vibration amplitude in g-force (g).",
    )

    vibration_freq: float = Field(
        ...,
        ge=0,
        le=1000,
        description="Vibration frequency in Hz.",
    )

    throttle_cmd: float = Field(
        ...,
        ge=0,
        le=100,
        description="Throttle position as a percentage (0–100 %).",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "timestamp": 12.5,
                    "msg_id": "ENG_TELEM_01",
                    "rpm": 5200.0,
                    "cht": 180.0,
                    "egt": 650.0,
                    "oil_pressure": 65.0,
                    "oil_temp": 95.0,
                    "fuel_flow": 28.5,
                    "vibration_amplitude": 0.35,
                    "vibration_freq": 86.6,
                    "throttle_cmd": 72.0,
                }
            ]
        }
    }
