import joblib
import pandas as pd
from src.config import RFC_MODEL_PATH, DATA_RAW_DIR, WINDOW_SIZE
from src.predict import predict_engine_health

def test_rfc_loads_successfully():
    assert RFC_MODEL_PATH.exists(), "Random Forest Classifier model file should exist"
    model = joblib.load(RFC_MODEL_PATH)
    assert model is not None, "Random Forest Classifier model should load"

def test_predict_engine_health_schema():
    # Pick a dummy window from a raw CSV file
    csv_files = list(DATA_RAW_DIR.glob("*.csv"))
    assert len(csv_files) > 0, "No raw CSV files available for test"
    
    df = pd.read_csv(csv_files[0])
    assert len(df) >= WINDOW_SIZE, f"CSV {csv_files[0]} doesn't have enough rows for window size {WINDOW_SIZE}"
    
    window = df.iloc[:WINDOW_SIZE].copy()
    
    # Predict
    result = predict_engine_health(window)
    
    # Check required fields
    required_fields = [
        "timestamp",
        "is_anomaly",
        "anomaly_score",
        "health_state",
        "fault_type",
        "confidence",
        "top_features",
        "explanation",
        "severity"
    ]
    
    for field in required_fields:
        assert field in result, f"Result should contain field '{field}'"
        
    # Check types
    assert isinstance(result["is_anomaly"], bool)
    assert isinstance(result["anomaly_score"], float)
    assert isinstance(result["health_state"], str)
    assert isinstance(result["fault_type"], str)
    assert isinstance(result["confidence"], float)
    assert isinstance(result["top_features"], list)
    assert isinstance(result["explanation"], str)
    assert isinstance(result["severity"], int)
