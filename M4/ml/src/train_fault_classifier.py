import numpy as np
import pandas as pd
import joblib
import json
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score, classification_report,
    confusion_matrix, f1_score
)
from src.config import *
from src.train_anomaly_detector import load_splits

def train_random_forest(X_train_sc, y_train_fault):
    rfc = RandomForestClassifier(**RFC_PARAMS)
    rfc.fit(X_train_sc, y_train_fault)
    joblib.dump(rfc, RFC_MODEL_PATH)
    return rfc

def evaluate_classifier(rfc, X_test_sc, y_test_fault, feature_names):
    y_pred = rfc.predict(X_test_sc)
    
    acc = accuracy_score(y_test_fault, y_pred)
    macro_f1 = f1_score(y_test_fault, y_pred, average="macro")
    weighted_f1 = f1_score(y_test_fault, y_pred, average="weighted")
    
    # We only pass labels that actually appear in y_test_fault + predictions to avoid warning
    labels_present = np.unique(np.concatenate([y_test_fault, y_pred]))
    target_names = [FAULT_TYPES[i] for i in labels_present]
    
    report_dict = classification_report(y_test_fault, y_pred, labels=labels_present, target_names=target_names, output_dict=True)
    
    metrics = {
        "accuracy": float(acc),
        "macro_f1": float(macro_f1),
        "weighted_f1": float(weighted_f1),
        "per_class_report": report_dict
    }
    
    with open(REPORT_DIR / "classification_metrics.json", "w") as f:
        json.dump(metrics, f, indent=4)
        
    print(classification_report(y_test_fault, y_pred, labels=labels_present, target_names=target_names))
    return metrics

def plot_confusion_matrix(y_true, y_pred, savepath):
    labels_present = np.unique(np.concatenate([y_true, y_pred]))
    cm = confusion_matrix(y_true, y_pred, labels=labels_present)
    target_names = [FAULT_TYPES[i] for i in labels_present]
    
    plt.figure(figsize=(10, 8))
    sns.heatmap(cm, annot=True, fmt="d", xticklabels=target_names, yticklabels=target_names, cmap="Blues")
    plt.xlabel("Predicted")
    plt.ylabel("True")
    plt.title("Fault Classification Confusion Matrix")
    plt.tight_layout()
    plt.savefig(savepath, dpi=150)
    plt.close()

def plot_feature_importance(rfc, feature_names, top_n=20, savepath=None):
    importances = rfc.feature_importances_
    indices = np.argsort(importances)[-top_n:]
    
    plt.figure(figsize=(10, 6))
    plt.barh([feature_names[i] for i in indices], importances[indices])
    plt.xlabel("Importance")
    plt.title(f"Top {top_n} Feature Importances")
    plt.tight_layout()
    if savepath:
        plt.savefig(savepath, dpi=150)
    plt.close()

if __name__ == "__main__":
    splits = load_splits()
    scaler = joblib.load(SCALER_PATH)
    
    X_train_sc = scaler.transform(splits["X_train"])
    X_val_sc   = scaler.transform(splits["X_val"])
    X_test_sc  = scaler.transform(splits["X_test"])
    
    rfc = train_random_forest(X_train_sc, splits["y_train_fault"])
    metrics = evaluate_classifier(rfc, X_test_sc, splits["y_test_fault"], splits["feature_names"])
    
    y_pred_test = rfc.predict(X_test_sc)
    plot_confusion_matrix(splits["y_test_fault"], y_pred_test, REPORT_DIR / "confusion_matrix.png")
    plot_feature_importance(rfc, splits["feature_names"], top_n=20, savepath=REPORT_DIR / "feature_importance.png")
    
    print(f"\nClassification Metrics: {metrics['accuracy']:.4f} Acc | {metrics['macro_f1']:.4f} Macro F1")
    print(f"Model saved to {RFC_MODEL_PATH}")
