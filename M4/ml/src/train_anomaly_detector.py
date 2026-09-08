import numpy as np
import pandas as pd
import joblib
import json
import matplotlib.pyplot as plt
from sklearn.ensemble import IsolationForest
from sklearn.metrics import (
    precision_score, recall_score, f1_score,
    confusion_matrix, classification_report
)
from src.config import *

def load_splits():
    train = pd.read_csv(DATA_PROC_DIR / "features_train.csv")
    val = pd.read_csv(DATA_PROC_DIR / "features_val.csv")
    test = pd.read_csv(DATA_PROC_DIR / "features_test.csv")
    
    feature_names = [c for c in train.columns if c not in ["label_anomaly", "label_fault_int"]]
    
    return {
        "X_train": train[feature_names].values,
        "X_val": val[feature_names].values,
        "X_test": test[feature_names].values,
        "y_train_anomaly": train["label_anomaly"].values,
        "y_val_anomaly": val["label_anomaly"].values,
        "y_test_anomaly": test["label_anomaly"].values,
        "y_train_fault": train["label_fault_int"].values,
        "y_val_fault": val["label_fault_int"].values,
        "y_test_fault": test["label_fault_int"].values,
        "feature_names": feature_names
    }

def train_isolation_forest(X_healthy_scaled):
    clf = IsolationForest(**IF_PARAMS)
    clf.fit(X_healthy_scaled)
    joblib.dump(clf, IF_MODEL_PATH)
    return clf

def tune_threshold(model, X_val_scaled, y_val_anomaly, max_far=0.02):
    scores = model.decision_function(X_val_scaled)
    thresholds = np.linspace(scores.min(), scores.max(), 300)
    best_f1 = 0
    best_thresh = IF_THRESHOLD
    
    normal_mask = (y_val_anomaly == 0)
    total_normal = np.sum(normal_mask)
    
    for t in thresholds:
        y_pred = (scores < t).astype(int)
        far = np.sum((y_pred == 1) & normal_mask) / total_normal if total_normal > 0 else 0
        if far <= max_far:
            f1 = f1_score(y_val_anomaly, y_pred, zero_division=0)
            if f1 > best_f1:
                best_f1 = f1
                best_thresh = t
                
    print(f"Tuned Threshold (FAR <= {max_far*100:.1f}%): {best_thresh:.4f} (Val F1: {best_f1:.4f})")
    return best_thresh

def evaluate_anomaly_detector(model, threshold, X_test_scaled, y_test_anomaly):
    scores = model.decision_function(X_test_scaled)
    y_pred = (scores < threshold).astype(int)
    
    prec = precision_score(y_test_anomaly, y_pred, zero_division=0)
    rec = recall_score(y_test_anomaly, y_pred, zero_division=0)
    f1 = f1_score(y_test_anomaly, y_pred, zero_division=0)
    
    # false alarm rate
    normal_mask = (y_test_anomaly == 0)
    false_alarms = np.sum((y_pred == 1) & normal_mask)
    total_normal = np.sum(normal_mask)
    far = false_alarms / total_normal if total_normal > 0 else 0.0
    
    metrics = {
        "precision": float(prec),
        "recall": float(rec),
        "f1_score": float(f1),
        "false_alarm_rate": float(far),
        "threshold_used": float(threshold)
    }
    
    with open(REPORT_DIR / "anomaly_metrics.json", "w") as f:
        json.dump(metrics, f, indent=4)
        
    print("Anomaly Detection Report:")
    print(classification_report(y_test_anomaly, y_pred))
    return metrics

def plot_anomaly_scores(scores, y_true, threshold, savepath):
    plt.figure(figsize=(14, 4))
    plt.plot(scores, label='Anomaly Score', color='blue', alpha=0.6)
    plt.axhline(threshold, color='red', linestyle='--', label='Threshold')
    
    # Shade actual anomalies
    anomaly_indices = np.where(y_true == 1)[0]
    for idx in anomaly_indices:
        plt.axvline(idx, color='orange', alpha=0.1)
        
    plt.title('Isolation Forest Anomaly Scores over Test Set')
    plt.xlabel('Timestep')
    plt.ylabel('Decision Function Score')
    plt.legend()
    plt.tight_layout()
    plt.savefig(savepath, dpi=150)
    plt.close()

if __name__ == "__main__":
    splits = load_splits()
    scaler = joblib.load(SCALER_PATH)
    
    X_train_sc = scaler.transform(splits["X_train"])
    X_val_sc   = scaler.transform(splits["X_val"])
    X_test_sc  = scaler.transform(splits["X_test"])
    
    mask_healthy = splits["y_train_anomaly"] == 0
    X_healthy_sc = X_train_sc[mask_healthy]
    print(f"Training IF on {X_healthy_sc.shape[0]} healthy samples.")
    
    model = train_isolation_forest(X_healthy_sc)
    threshold = tune_threshold(model, X_val_sc, splits["y_val_anomaly"])
    metrics = evaluate_anomaly_detector(model, threshold, X_test_sc, splits["y_test_anomaly"])
    
    scores_test = model.decision_function(X_test_sc)
    plot_anomaly_scores(scores_test, splits["y_test_anomaly"], threshold,
                        REPORT_DIR / "anomaly_score_plot.png")
    
    print(f"\nAnomaly Detection Metrics: {metrics}")
    print(f"Model saved to {IF_MODEL_PATH}")
