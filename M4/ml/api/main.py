from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import pandas as pd
from src.predict import predict_engine_health
from src.config import WINDOW_SIZE, FAULT_TYPES

app = FastAPI(
    title       = "M4 AI/ML Engine Health API",
    description = "Anomaly detection and fault classification for MALE UAV aero piston engine digital twin.",
    version     = "1.0.0-baseline"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class TelemetryRow(BaseModel):
    timestamp:              int
    rpm:                    float
    throttle:               float
    oil_pressure:           float
    oil_temp:               float
    cht:                    float
    egt:                    float
    manifold_pressure:      float
    vibration:              float
    fuel_flow:              float
    ambient_temp:           float
    altitude:               float
    mission_phase:          str
    residual_rpm:           Optional[float] = 0.0
    residual_oil_pressure:  Optional[float] = 0.0
    residual_oil_temp:      Optional[float] = 0.0
    residual_cht:           Optional[float] = 0.0
    residual_egt:           Optional[float] = 0.0
    residual_manifold_pressure: Optional[float] = 0.0
    residual_vibration:     Optional[float] = 0.0
    residual_fuel_flow:     Optional[float] = 0.0
    health_index:           Optional[float] = 1.0
    baseline_rul:           Optional[float] = 200.0

class PredictRequest(BaseModel):
    window: List[TelemetryRow]

class PredictResponse(BaseModel):
    timestamp:     str
    is_anomaly:    bool
    anomaly_score: float
    health_state:  str
    fault_type:    str
    confidence:    float
    top_features:  List[str]
    explanation:   str
    severity:      int

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/model-info")
def model_info():
    return {
        "models": ["IsolationForest", "RandomForestClassifier"],
        "fault_types": FAULT_TYPES,
        "window_size": WINDOW_SIZE
    }

@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest):
    if len(req.window) < WINDOW_SIZE:
        raise HTTPException(
            status_code=422,
            detail=f"Window must contain at least {WINDOW_SIZE} rows."
        )
    window_df = pd.DataFrame([row.model_dump() for row in req.window])
    result = predict_engine_health(window_df)
    return PredictResponse(**result)
