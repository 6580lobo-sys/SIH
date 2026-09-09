"""
backend_server.py -- Integrated FastAPI Backend Server for DRDO SIH26054
========================================================================
Runs the continuous real-time M1-M6 system orchestrator and exposes high-speed
REST endpoints for the Ground Control Station (GCS) frontend.
"""

import os
import sys
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from orchestrator import Orchestrator, TelemetryFrame

app = FastAPI(
    title="DRDO SIH26054 Aero-Piston Engine Digital Twin Backend",
    description="Unified backend server coordinating M1 (Physics Twin), M2 (Prognostics/RUL), M3 (Telemetry/Fault Injection), and M4 (Machine Learning Inference).",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize global orchestrator
orchestrator = Orchestrator(
    rate_hz=10.0,
    history_maxlen=1000,
    mission_duration_hours=8.0,
)

# Start orchestrator background loop
try:
    orchestrator.start(blocking=False)
    print("[backend_server] Orchestrator background streaming started at 10.0 Hz.")
except Exception as e:
    print(f"[backend_server] Notice starting orchestrator: {e}")


class ProbeRequest(BaseModel):
    rpm: Optional[float] = 2438.0
    throttle: Optional[float] = 65.0
    oil_temp: Optional[float] = 94.2
    oil_pressure: Optional[float] = 4.82
    cht: Optional[float] = 167.4
    egt: Optional[float] = 612.8
    fuel_flow: Optional[float] = 21.7
    vibration: Optional[float] = 0.84
    mission_duration_hours: Optional[float] = 8.0


class ScenarioSelectRequest(BaseModel):
    scenario_key: Optional[str] = None
    scenario_id: Optional[str] = None


class CustomScenarioRequest(BaseModel):
    key: str
    name: str
    description: str
    fault_type: str
    severity: Optional[float] = 0.8
    environment: Optional[str] = "standard_day"
    throttle_mode: Optional[str] = "smooth"


@app.get("/")
def root():
    return {
        "service": "DRDO SIH26054 Aero-Piston Engine Digital Twin Backend",
        "status": "online",
        "orchestrator_running": orchestrator._running,
        "current_scenario": orchestrator._current_scenario,
        "tick_count": orchestrator._tick_count,
        "docs_url": "http://localhost:8000/docs",
        "latest_telemetry_url": "http://localhost:8000/api/telemetry/latest",
        "health_url": "http://localhost:8000/health",
        "scenarios_url": "http://localhost:8000/api/scenarios"
    }


@app.get("/health")
@app.get("/api/health")
def health():
    return {
        "status": "healthy",
        "orchestrator_running": orchestrator._running,
        "current_scenario": orchestrator._current_scenario,
        "tick_count": orchestrator._tick_count,
    }


@app.get("/api/status")
def get_status():
    return orchestrator.get_status()


@app.get("/api/telemetry/latest")
@app.get("/api/telemetry/live")
def get_latest_telemetry():
    latest = orchestrator.get_latest()
    if not latest:
        return {"status": "waiting_for_first_tick"}
    return latest.as_dict()


@app.get("/api/telemetry/history")
def get_telemetry_history(n: int = 50):
    frames = orchestrator.get_history(n=n)
    return [f.as_dict() for f in frames]


@app.get("/api/scenarios")
def list_scenarios():
    return orchestrator.scenario_manager.get_all_scenarios()


@app.post("/api/scenarios/select")
def select_scenario(req: ScenarioSelectRequest):
    all_s = orchestrator.scenario_manager.get_all_scenarios()
    key = req.scenario_key or req.scenario_id or "healthy"
    aliases = {
        "healthy": "healthy",
        "nominal": "nominal_cruise",
        "misfire": "misfire_or_injector_fault",
        "overheating": "cht_overheating",
        "oil_pressure_loss": "oil_pressure_drop",
        "bearing_vibration": "vibration_bearing_fault",
    }
    normalized_key = aliases.get(key, key)
    if normalized_key not in all_s:
        matches = [k for k in all_s if key in k or k in key]
        if matches:
            normalized_key = matches[0]
        else:
            raise HTTPException(status_code=404, detail=f"Scenario '{key}' not found.")
    orchestrator.load_scenario(normalized_key)
    return {
        "status": "scenario_loaded",
        "active_scenario": normalized_key,
        "details": all_s.get(normalized_key, {}),
    }


@app.post("/api/scenarios/save")
def save_scenario(req: CustomScenarioRequest):
    scenario_data = {
        "name": req.name,
        "description": req.description,
        "environment": req.environment,
        "throttle_mode": req.throttle_mode,
        "faults": [
            {
                "type": req.fault_type,
                "severity": req.severity,
                "start_time_s": 1.0,
                "duration_s": 30.0,
            }
        ],
    }
    orchestrator.scenario_manager.save_custom_scenario(req.key, scenario_data)
    return {
        "status": "custom_scenario_saved",
        "key": req.key,
        "scenario": scenario_data,
    }


@app.post("/api/probe")
def evaluate_probe(req: ProbeRequest):
    """Run real-time M1 Physics Twin -> M2 Prognostics -> M4 ML Inference."""
    result = orchestrator.evaluate_live_probe(req.model_dump())
    return result


if __name__ == "__main__":
    uvicorn.run("backend_server:app", host="0.0.0.0", port=8000, reload=False, log_level="info")
