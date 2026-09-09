import numpy as np
import pandas as pd
import joblib
from datetime import datetime
from src.config import *
from src.feature_engineering import (
    clean_dataframe, encode_mission_phase,
    compute_rolling_features, compute_slope_features,
    get_feature_columns
)
from src.explain import build_explanation

_scaler = None
_if_model = None
_rfc = None
_feature_names = None

def _load_models():
    global _scaler, _if_model, _rfc, _feature_names
    if _scaler is None:
        _scaler = joblib.load(SCALER_PATH)
        _if_model = joblib.load(IF_MODEL_PATH)
        _rfc = joblib.load(RFC_MODEL_PATH)
        # We need feature names. Since predict gets raw window, we'll get it from processing.

def preprocess_window(window_df):
    df = window_df.copy()
    df = clean_dataframe(df)
    df = encode_mission_phase(df)
    
    # We must ensure all columns exist
    for phase in MISSION_PHASES:
        col = f"mission_phase_{phase}"
        if col not in df.columns:
            df[col] = 0
            
    df = compute_rolling_features(df)
    df = compute_slope_features(df)
    
    global _feature_names
    if _feature_names is None:
        _feature_names = get_feature_columns(df)
        
    # extract last row
    last_row = df.iloc[[-1]]
    
    # Select exact features in exact order
    for col in _feature_names:
        if col not in last_row.columns:
            last_row[col] = 0.0
            
    X = last_row[_feature_names].values
    return _scaler.transform(X), _feature_names

def compute_health_state(anomaly_score, is_anomaly, fault_type):
    if not is_anomaly or fault_type == "healthy":
        return "normal"
    elif anomaly_score > 0.7 or "escalating" in fault_type:
        return "critical"
    else:
        return "degrading"

def normalize_anomaly_score(raw_score, score_min=-0.10, score_max=0.05):
    raw_score = np.clip(raw_score, score_min, score_max)
    # raw_score is <0 for anomalies, >0 for normal.
    # we want 1 to be highly anomalous, 0 to be normal
    norm = 1.0 - (raw_score - score_min) / (score_max - score_min)
    return float(np.clip(norm, 0.0, 1.0))

def predict_engine_health(window_df: pd.DataFrame) -> dict:
    _load_models()
    
    X_scaled, feature_names = preprocess_window(window_df)
    
    raw_score = _if_model.decision_function(X_scaled)[0]
    is_if_anomaly = bool(raw_score < IF_THRESHOLD)
    anomaly_score = normalize_anomaly_score(raw_score)
    
    proba = _rfc.predict_proba(X_scaled)[0]
    fault_int = int(np.argmax(proba))
    rfc_fault_type = INT_TO_FAULT_TYPE[fault_int]
    rfc_confidence = float(proba[fault_int])
    
    # Dual-model fusion logic:
    # 1. Known fault pattern detected by classifier
    if rfc_fault_type != "healthy":
        is_anomaly = True
        fault_type = rfc_fault_type
        confidence = rfc_confidence
    # 2. Outlier / Zero-day anomaly detected by Isolation Forest (unseen fault signature)
    elif is_if_anomaly:
        is_anomaly = True
        fault_type = "unknown_anomaly"
        confidence = float(anomaly_score)
    # 3. Healthy nominal flight
    else:
        is_anomaly = False
        fault_type = "healthy"
        confidence = float(proba[0])
        
    health_state = compute_health_state(anomaly_score, is_anomaly, fault_type)
    
    if not is_anomaly:
        severity = 0
    elif "escalating" in fault_type:
        severity = 3
    elif anomaly_score < 0.4:
        severity = 1
    elif anomaly_score < 0.7:
        severity = 2
    else:
        severity = 3
        
    sensor_vals = window_df.iloc[-1].to_dict()
    explanation = build_explanation(
        fault_type=fault_type,
        confidence=confidence,
        feature_names=feature_names,
        X_window_scaled=X_scaled,
        sensor_values=sensor_vals
    )
    
    prob_dict = {INT_TO_FAULT_TYPE[i]: round(float(p), 4) for i, p in enumerate(proba)}
    
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "is_anomaly": is_anomaly,
        "anomaly_score": round(anomaly_score, 4),
        "health_state": health_state,
        "fault_type": fault_type,
        "confidence": round(confidence, 4),
        "probabilities": prob_dict,
        "top_features": explanation["top_features"],
        "explanation": explanation["explanation"],
        "severity": severity
    }
