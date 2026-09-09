import numpy as np
import pandas as pd
try:
    import shap
except ImportError:
    shap = None
import joblib
try:
    import matplotlib.pyplot as plt
except ImportError:
    plt = None
from src.config import *

def load_explainer(rfc, X_background):
    # Use a smaller subsample for TreeExplainer speed
    explainer = shap.TreeExplainer(rfc, X_background[:100])
    return explainer

def get_shap_values(explainer, X_window_scaled):
    return explainer.shap_values(X_window_scaled)

def get_top_shap_features(shap_vals, feature_names, predicted_class, n=3):
    # shap_vals is a list of arrays (one per class)
    shap_for_class = shap_vals[:, :, predicted_class] if len(np.array(shap_vals).shape) == 3 else shap_vals[predicted_class]
    if isinstance(shap_for_class, list) or len(shap_for_class.shape) > 1:
        # aggregate or take the first row
        shap_for_class = shap_for_class[0]
        
    top_indices = np.argsort(np.abs(shap_for_class))[-n:][::-1]
    return [feature_names[i] for i in top_indices]

EXPLANATION_TEMPLATES = {
    "healthy": "Engine is operating within normal parameters. All sensor readings and residuals are within expected range.",
    "overheating": "Overheating detected. Cylinder head temperature and/or exhaust gas temperature are rising above expected values. Recommend reducing power and checking cooling system.",
    "oil_pressure_drop": "Oil pressure degradation detected. Measured oil pressure is below physics-model expectation and trending downward. Oil temperature is also rising. Recommend reducing load and scheduling oil system inspection.",
    "vibration_bearing_fault": "Abnormal vibration detected. Vibration level is above expected trend. This pattern is consistent with bearing wear or mechanical imbalance. Recommend immediate inspection of rotating components.",
    "misfire_or_injector_fault": "Combustion irregularity detected. EGT is showing intermittent spikes and RPM is fluctuating. Fuel flow shows irregular delivery pattern. Possible injector fault or ignition misfire. Recommend engine inspection.",
    "fuel_mixture_drift": "Fuel mixture drift detected. Fuel flow is above commanded value. EGT trending upward indicates rich mixture condition. Recommend checking fuel metering system and mixture control.",
    "cooling_system_fault": "Cooling system degradation detected. CHT residual is above expected. Oil temperature is also elevated. Cooling efficiency has dropped. Recommend coolant system check.",
    "engine_overspeed": "Engine overspeed detected. RPM is spiking drastically above normal operating limits. Recommend immediate throttle reduction and inspection of governor system.",
    "unknown_anomaly": "Unseen anomaly detected. Telemetry signature deviates significantly from normal baseline envelope without matching known fault modes. Recommend telemetry review."
}

def format_explanation(fault_type, sensor_values, top_features):
    if fault_type in EXPLANATION_TEMPLATES:
        text = EXPLANATION_TEMPLATES[fault_type]
    elif fault_type.startswith("mixed_"):
        parts = fault_type.replace("mixed_", "").split("__")
        part_names = [p.replace("_", " ") for p in parts]
        text = f"Compound multi-subsystem fault detected: simultaneous '{part_names[0]}' and '{part_names[1]}' conditions observed. High risk of compounding engine degradation."
    elif fault_type.endswith("_escalating"):
        base_name = fault_type.replace("_escalating", "").replace("_", " ")
        text = f"Escalating {base_name} detected. Sensor values are deteriorating rapidly over time. Immediate corrective action required."
    elif fault_type.endswith("_recovering"):
        base_name = fault_type.replace("_recovering", "").replace("_", " ")
        text = f"Transient/Recovering {base_name} detected. Sensor parameters are stabilizing back toward nominal range."
    else:
        text = f"Anomaly detected ({fault_type.replace('_', ' ')}). Telemetry signature shows abnormal deviation from nominal flight envelope."

    if top_features:
        text += f" Key sensors contributing to this alert: {', '.join(top_features)}."
    return text

def build_explanation(fault_type, confidence, feature_names, X_window_scaled, explainer=None, sensor_values=None):
    if explainer is not None:
        try:
            # Need int class for SHAP
            fault_int = FAULT_TYPE_TO_INT[fault_type]
            shap_vals = get_shap_values(explainer, X_window_scaled)
            top_features = get_top_shap_features(shap_vals, feature_names, fault_int)
        except Exception:
            top_features = []
            method = "fallback"
    else:
        # Fast real-time heuristic: top features by standardized deviation
        if X_window_scaled is not None and feature_names is not None:
            vals = np.abs(X_window_scaled[0])
            top_indices = np.argsort(vals)[-3:][::-1]
            top_features = [feature_names[i] for i in top_indices if vals[i] > 0.8]
        else:
            top_features = []
        method = "deviation"
        
    explanation_text = format_explanation(fault_type, sensor_values or {}, top_features)
    
    return {
        "fault_type": fault_type,
        "confidence": float(confidence),
        "top_features": top_features,
        "explanation": explanation_text,
        "method": method
    }

def plot_shap_summary(explainer, X_sample_scaled, feature_names, savepath):
    shap_vals = explainer.shap_values(X_sample_scaled)
    shap.summary_plot(shap_vals, X_sample_scaled, feature_names=feature_names, class_names=FAULT_TYPES, show=False)
    plt.savefig(savepath, dpi=150, bbox_inches="tight")
    plt.close()
