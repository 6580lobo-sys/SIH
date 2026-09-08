import numpy as np
import pandas as pd
import joblib
import json
from src.config import *
from src.train_anomaly_detector import load_splits

def run_full_evaluation():
    splits = load_splits()
    
    # Anomaly models
    if_model = joblib.load(IF_MODEL_PATH)
    rfc = joblib.load(RFC_MODEL_PATH)
    scaler = joblib.load(SCALER_PATH)
    
    X_test_sc = scaler.transform(splits["X_test"])
    
    # We already have evaluation code in train scripts, so we just run them here if we want or just skip.
    print("Run `python -m src.train_anomaly_detector` and `python -m src.train_fault_classifier` to generate full reports.")

if __name__ == "__main__":
    run_full_evaluation()
