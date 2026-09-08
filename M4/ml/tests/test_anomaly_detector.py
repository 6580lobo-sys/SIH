import joblib
import pandas as pd
import numpy as np
from src.config import IF_MODEL_PATH, SCALER_PATH, DATA_PROC_DIR, IF_THRESHOLD

def test_isolation_forest_loads_successfully():
    assert IF_MODEL_PATH.exists(), "Isolation Forest model file should exist"
    model = joblib.load(IF_MODEL_PATH)
    assert model is not None, "Isolation Forest model should load"

def test_anomaly_detection_logic():
    # Load model and scaler
    model = joblib.load(IF_MODEL_PATH)
    scaler = joblib.load(SCALER_PATH)
    
    # Load tuned threshold
    import json
    from src.config import REPORT_DIR
    with open(REPORT_DIR / "anomaly_metrics.json", "r") as f:
        metrics = json.load(f)
    threshold = metrics.get("threshold_used", -0.05)
    
    # Load test dataset
    df = pd.read_csv(DATA_PROC_DIR / "features_test.csv")
    feature_names = [c for c in df.columns if c not in ["label_anomaly", "label_fault_int"]]
    
    # Filter for healthy and anomalous rows
    healthy_df = df[df["label_anomaly"] == 0]
    anomaly_df = df[df["label_anomaly"] == 1]
    
    # Scale features
    if len(healthy_df) > 0:
        X_healthy = scaler.transform(healthy_df[feature_names].values)
        scores_healthy = model.decision_function(X_healthy)
        preds_healthy = (scores_healthy < threshold).astype(int)
        healthy_accuracy = 1.0 - np.mean(preds_healthy) # fraction of correctly classified healthy
        assert healthy_accuracy > 0.75, f"Healthy data should mostly be normal (Got {healthy_accuracy:.2f} accuracy)"
        
    if len(anomaly_df) > 0:
        X_anomaly = scaler.transform(anomaly_df[feature_names].values)
        scores_anomaly = model.decision_function(X_anomaly)
        preds_anomaly = (scores_anomaly < threshold).astype(int)
        anomaly_accuracy = np.mean(preds_anomaly) # fraction of correctly classified anomalies
        assert anomaly_accuracy > 0.8, f"Fault data should mostly be anomalies (Got {anomaly_accuracy:.2f} accuracy)"
