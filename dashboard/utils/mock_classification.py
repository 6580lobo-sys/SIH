"""
utils/mock_classification.py
============================
Mock fault classifier matching data contract section 4A.

Produces the exact payload shape M5 expects from M3/M4:
    {
        timestamp:          float   (Unix epoch),
        fault_label:        str     (human-readable classification),
        fault_id:           str     (unique event ID for dedup),
        confidence:         float   (0.0-1.0),
        top_k_classes:      list    ([{label, confidence}, ...]),
        explanation: {
            method:         str     ("shap" | "attention" | null),
            features:       dict    ({channel: importance_score}),
        },
        recommended_action: str     (maintenance advisory text),
    }

This is a MOCK -- replace with M3/M4's real classifier when available.
The mock infers fault type from dominant_channels, mimicking a real classifier.

Usage:
    from utils.mock_classification import MockClassifier

    classifier = MockClassifier()
    cls = classifier.classify(
        signature=sig,                # M1's signature payload
        active_fault="overheating",   # from engine state (optional hint)
        timestamp=time.time(),
    )
"""

import time
import random
from typing import Optional


# ── Channel-to-fault mapping (heuristic classification) ───────────────────────
# Which dominant channels suggest which fault type
_CHANNEL_FAULT_MAP = {
    "egt":                  "overheating",
    "cht":                  "overheating",
    "oil_pressure":         "oil_pressure_drop",
    "oil_temp":             "oil_pressure_drop",
    "rpm":                  "misfire",
    "fuel_flow":            "injector_fault",
    "vibration_amplitude":  "vibration_anomaly",
    "vibration_freq":       "vibration_anomaly",
}

# All known fault labels
FAULT_LABELS = [
    "overheating",
    "oil_pressure_drop",
    "misfire",
    "injector_fault",
    "vibration_anomaly",
    "unknown",
]

# Human-readable labels
_LABEL_DISPLAY = {
    "overheating":        "Overheating",
    "oil_pressure_drop":  "Oil Pressure Drop",
    "misfire":            "Misfire",
    "injector_fault":     "Injector Fault",
    "vibration_anomaly":  "Vibration Anomaly",
    "unknown":            "Unknown Fault",
}

# Recommended actions per fault type
_RECOMMENDATIONS = {
    "overheating":        "Reduce throttle, monitor CHT/EGT. Schedule inspection within 5 flight-hours.",
    "oil_pressure_drop":  "Check oil level and pump integrity. Abort mission if pressure < 2.5 bar.",
    "misfire":            "Inspect spark plugs & ignition leads. Check fuel injector spray pattern.",
    "injector_fault":     "Inspect fuel injector for clog/leak. Check fuel pressure at injector rail.",
    "vibration_anomaly":  "Inspect propeller balance & mounting. Check engine mounts for looseness.",
    "unknown":            "Elevated anomaly detected. Schedule ground inspection at next opportunity.",
}

# Icons per fault type (for UI display)
FAULT_ICONS = {
    "overheating":        "\U0001f525",   # fire
    "oil_pressure_drop":  "\U0001f4a7",   # droplet
    "misfire":            "\u26a1",        # lightning
    "injector_fault":     "\u26fd",        # fuel pump
    "vibration_anomaly":  "\U0001f4f3",   # vibration
    "unknown":            "\u2753",        # question mark
}


class MockClassifier:
    """
    Infers fault type from M1's signature payload.

    Uses dominant_channels to guess the fault label (mimicking what
    M3/M4's real ML classifier would produce). Generates stable fault_ids
    so the same ongoing fault event doesn't create duplicate alerts.
    """

    def __init__(self):
        self._fault_counter = 0
        self._current_fault_id: Optional[str] = None
        self._last_fault_label: Optional[str] = None

    def classify(
        self,
        signature: Optional[dict],
        active_fault: Optional[str] = None,
        timestamp: Optional[float] = None,
    ) -> Optional[dict]:
        """
        Produce a section 4A classification payload from M1's signature.

        Args:
            signature:    M1's signature payload (section 1B), or None.
            active_fault: Optional hint from the engine's active fault state.
            timestamp:    Unix epoch (defaults to now).

        Returns:
            dict matching section 4A, or None if no fault detected.
        """
        if signature is None:
            return None

        if not signature.get("fault_detected", False):
            # No fault — clear current tracking
            self._current_fault_id = None
            self._last_fault_label = None
            return None

        if timestamp is None:
            timestamp = time.time()

        # ── Infer fault label ─────────────────────────────────────────────────
        dominant = signature.get("dominant_channels", [])

        if active_fault and active_fault in _LABEL_DISPLAY:
            # Use the engine's known fault type as ground truth (mock advantage)
            primary_label = active_fault
        elif dominant:
            # Infer from top dominant channel
            top_channel = dominant[0][0] if isinstance(dominant[0], (list, tuple)) else dominant[0]
            primary_label = _CHANNEL_FAULT_MAP.get(top_channel, "unknown")
        else:
            primary_label = "unknown"

        # ── Fault ID (stable across ticks for same event) ─────────────────────
        if primary_label != self._last_fault_label:
            # New fault event
            self._fault_counter += 1
            self._current_fault_id = f"FAULT_{self._fault_counter:03d}"
            self._last_fault_label = primary_label

        # ── Confidence ────────────────────────────────────────────────────────
        severity = signature.get("severity", 0.5)
        base_confidence = 0.65 + 0.30 * min(1.0, severity)
        confidence = round(min(0.99, base_confidence + random.gauss(0, 0.03)), 2)

        # ── Top-k classes ─────────────────────────────────────────────────────
        # Primary gets the main confidence; distribute remainder among others
        other_labels = [l for l in FAULT_LABELS if l != primary_label]
        random.shuffle(other_labels)
        remaining = 1.0 - confidence
        top_k = [{"label": primary_label, "confidence": confidence}]

        for i, label in enumerate(other_labels[:2]):
            share = remaining * (0.6 if i == 0 else 0.4)
            top_k.append({"label": label, "confidence": round(share, 2)})

        # ── Explanation (SHAP-like feature attribution) ────────────────────────
        feature_vector = signature.get("feature_vector", {})
        total_magnitude = sum(abs(v) for v in feature_vector.values()) or 1.0

        features = {
            ch: round(abs(v) / total_magnitude, 2)
            for ch, v in feature_vector.items()
        }

        # ── Build payload ─────────────────────────────────────────────────────
        return {
            "timestamp":         round(timestamp, 3),
            "fault_label":       primary_label,
            "fault_id":          self._current_fault_id,
            "confidence":        confidence,
            "top_k_classes":     top_k,
            "explanation": {
                "method":        "shap",
                "features":      features,
            },
            "recommended_action": _RECOMMENDATIONS.get(primary_label, _RECOMMENDATIONS["unknown"]),
        }

    def reset(self):
        """Clear tracking state."""
        self._current_fault_id = None
        self._last_fault_label = None


# ── Self-test ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    classifier = MockClassifier()

    print("=" * 60)
    print("MOCK CLASSIFIER SELF-TEST")
    print("=" * 60)

    # No fault
    print("\n[1] NO FAULT (signature with fault_detected=False)")
    result = classifier.classify({"fault_detected": False, "severity": 0.02})
    print(f"  Result: {result}  (expected: None)")

    # Overheating fault
    print("\n[2] OVERHEATING FAULT")
    sig = {
        "feature_vector": {
            "rpm": 0.002, "cht": 0.15, "egt": 0.42, "oil_pressure": 0.001,
            "oil_temp": 0.08, "fuel_flow": 0.001, "vibration_amplitude": 0.003,
            "vibration_freq": 0.001,
        },
        "dominant_channels": [("egt", 0.42), ("cht", 0.15), ("oil_temp", 0.08)],
        "severity": 0.72,
        "fault_detected": True,
    }
    result = classifier.classify(sig, active_fault="overheating")
    if result:
        print(f"  fault_label:   {result['fault_label']}")
        print(f"  fault_id:      {result['fault_id']}")
        print(f"  confidence:    {result['confidence']}")
        print(f"  top_k:         {result['top_k_classes']}")
        print(f"  explanation:   method={result['explanation']['method']}")
        print(f"  action:        {result['recommended_action'][:60]}...")

    # Misfire fault (no active_fault hint, infer from channels)
    print("\n[3] MISFIRE (inferred from dominant channels, no hint)")
    sig2 = {
        "feature_vector": {
            "rpm": 0.35, "cht": 0.01, "egt": 0.08, "oil_pressure": 0.001,
            "oil_temp": 0.002, "fuel_flow": 0.001, "vibration_amplitude": 0.12,
            "vibration_freq": 0.001,
        },
        "dominant_channels": [("rpm", 0.35), ("vibration_amplitude", 0.12), ("egt", 0.08)],
        "severity": 0.55,
        "fault_detected": True,
    }
    result2 = classifier.classify(sig2)
    if result2:
        print(f"  fault_label:   {result2['fault_label']}")
        print(f"  fault_id:      {result2['fault_id']}  (should be FAULT_002, new event)")
        print(f"  confidence:    {result2['confidence']}")

    # Same fault again (stable fault_id)
    print("\n[4] SAME MISFIRE AGAIN (fault_id should be stable)")
    result3 = classifier.classify(sig2)
    if result3:
        print(f"  fault_id:      {result3['fault_id']}  (should still be FAULT_002)")

    print(f"\n[OK] All payloads match section 4A schema.\n")
