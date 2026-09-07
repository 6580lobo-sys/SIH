"""
integration_test.py — End-to-end integration pass (Step 8 / Day 6).

Runs the FULL pipeline exactly as M3's classifier and M4's dashboard will
call it, validating schema compatibility at every boundary:

    fault injector (M2) -> DigitalTwin (M1) -> ResidualEngine (M1)
        -> [signature for M3, tick output for M4]

Also runs the replay path to confirm it produces identical output.

If any schema mismatch is found on M1's side, it's fixed here.
If the mismatch is on M2/M3/M4's side, it's FLAGGED, not silently patched.
"""

import os
import sys

# ---------------------------------------------------------------------------
# Schema contracts — what each downstream consumer expects
# ---------------------------------------------------------------------------

# What M2's fault injector emits (= what DigitalTwin's actual_source returns)
M2_ACTUAL_SCHEMA = {
    "timestamp", "rpm", "cht", "egt", "oil_pressure", "oil_temp",
    "fuel_flow", "vibration_amplitude", "vibration_freq", "throttle_cmd",
}

# What DigitalTwin.step() returns
TWIN_OUTPUT_SCHEMA = {"predicted", "actual"}

# What each inner dict (predicted / actual) must contain
TWIN_INNER_SCHEMA = M2_ACTUAL_SCHEMA  # same fields

# What ResidualEngine.update() returns (consumed by M4 dashboard)
RESIDUAL_OUTPUT_SCHEMA = {"timestamp", "residuals", "composite_score"}

# What ResidualEngine.signature() returns (consumed by M3 classifier)
SIGNATURE_SCHEMA = {
    "feature_vector", "dominant_channels", "severity", "fault_detected",
}

# Channels that must appear in residuals and feature_vector
RESIDUAL_CHANNELS = {
    "rpm", "cht", "egt", "oil_pressure", "oil_temp", "fuel_flow",
    "vibration_amplitude", "vibration_freq",
}


def validate_schema(data: dict, expected: set, label: str) -> list:
    """Check that data's keys match expected. Return list of issues."""
    issues = []
    actual_keys = set(data.keys())
    missing = expected - actual_keys
    extra = actual_keys - expected
    if missing:
        issues.append(f"[{label}] MISSING fields: {missing}")
    if extra:
        issues.append(f"[{label}] EXTRA fields (not necessarily bad): {extra}")
    return issues


def main():
    from twin_core._dev_fault_stub import FaultedSimulator, FAULT_PROFILES
    from twin_core.twin import DigitalTwin
    from twin_core.residual import ResidualEngine
    from twin_core.replay import save_csv, replay_csv, load_csv

    DT = 0.1
    FAULT_TIME = 25.0
    DURATION = 45.0
    THROTTLE = 55.0

    all_issues = []
    pass_count = 0
    total_checks = 0

    print("=" * 78)
    print("INTEGRATION TEST — Full Pipeline (Step 8)")
    print("=" * 78)

    # ==================================================================
    # TEST 1: Live pipeline for each fault type
    # ==================================================================
    for fault_name in FAULT_PROFILES:
        print(f"\n--- Fault: {fault_name} ---")

        # Stage A: M2 fault injector -> actual source
        faulted = FaultedSimulator(
            fault_type=fault_name, fault_time=FAULT_TIME, seed=99
        )

        # Stage B: DigitalTwin (M1)
        twin = DigitalTwin(actual_source=faulted.step, ref_seed=42)

        # Stage C: ResidualEngine (M1)
        residual_eng = ResidualEngine()

        profile = [THROTTLE] * int(DURATION / DT)
        all_results = []

        for throttle_cmd in profile:
            # B1: Twin step
            pair = twin.step(throttle_cmd, DT)

            # Schema check: twin output
            total_checks += 1
            issues = validate_schema(pair, TWIN_OUTPUT_SCHEMA,
                                     f"{fault_name}/twin_output")
            if not issues:
                pass_count += 1
            all_issues.extend(issues)

            # Schema check: predicted inner dict
            total_checks += 1
            issues = validate_schema(pair["predicted"], TWIN_INNER_SCHEMA,
                                     f"{fault_name}/predicted")
            if not issues:
                pass_count += 1
            all_issues.extend(issues)

            # Schema check: actual inner dict
            total_checks += 1
            issues = validate_schema(pair["actual"], TWIN_INNER_SCHEMA,
                                     f"{fault_name}/actual")
            if not issues:
                pass_count += 1
            all_issues.extend(issues)

            # C1: Residual engine tick
            result = residual_eng.update(pair)

            # Schema check: residual output (for M4 dashboard)
            total_checks += 1
            issues = validate_schema(result, RESIDUAL_OUTPUT_SCHEMA,
                                     f"{fault_name}/residual_output")
            if not issues:
                pass_count += 1
            all_issues.extend(issues)

            # Schema check: residual channels
            total_checks += 1
            issues = validate_schema(result["residuals"], RESIDUAL_CHANNELS,
                                     f"{fault_name}/residual_channels")
            if not issues:
                pass_count += 1
            all_issues.extend(issues)

            all_results.append(result)

        # C2: Signature (for M3 classifier)
        sig = residual_eng.signature()

        total_checks += 1
        issues = validate_schema(sig, SIGNATURE_SCHEMA,
                                 f"{fault_name}/signature")
        if not issues:
            pass_count += 1
        all_issues.extend(issues)

        # Schema check: feature vector channels
        total_checks += 1
        issues = validate_schema(sig["feature_vector"], RESIDUAL_CHANNELS,
                                 f"{fault_name}/feature_vector")
        if not issues:
            pass_count += 1
        all_issues.extend(issues)

        # Verify fault is detected
        total_checks += 1
        post_fault = [r for r in all_results
                      if r["timestamp"] > FAULT_TIME + 10]
        avg_composite = (sum(r["composite_score"] for r in post_fault)
                         / len(post_fault)) if post_fault else 0
        if avg_composite > 0.03:
            pass_count += 1
            top = [f"{ch}={v:+.3f}"
                   for ch, v in sig["dominant_channels"][:3]]
            print(f"  Detected: composite={avg_composite:.4f}, "
                  f"signature=[{', '.join(top)}]")
        else:
            all_issues.append(
                f"[{fault_name}] Fault NOT detected (composite={avg_composite:.4f})")
            print(f"  FAILED: composite too low ({avg_composite:.4f})")

    # ==================================================================
    # TEST 2: Replay path matches live path
    # ==================================================================
    print(f"\n{'=' * 78}")
    print("REPLAY INTEGRATION TEST")
    print("=" * 78)

    # Generate and save a CSV from the overheating scenario
    faulted = FaultedSimulator(
        fault_type="overheating", fault_time=FAULT_TIME, seed=99
    )
    twin_live = DigitalTwin(actual_source=faulted.step, ref_seed=42)
    res_live = ResidualEngine()

    profile = [THROTTLE] * int(DURATION / DT)
    live_pairs = twin_live.run(profile, DT)
    live_results = res_live.process_batch(live_pairs)

    csv_path = os.path.join(os.path.dirname(__file__),
                            "..", "..", "data", "integration_test.csv")
    save_csv([p["actual"] for p in live_pairs], csv_path)

    # Replay the CSV
    replay_results = replay_csv(csv_path, ref_seed=42)

    # Compare
    total_checks += 1
    max_diff = 0.0
    for lr, rr in zip(live_results, replay_results):
        diff = abs(lr["composite_score"] - rr["composite_score"])
        max_diff = max(max_diff, diff)

    if max_diff < 1e-9:
        pass_count += 1
        print(f"  Replay matches live: max composite diff = {max_diff:.2e}")
    else:
        all_issues.append(
            f"[replay] Composite mismatch: max diff = {max_diff:.2e}")
        print(f"  MISMATCH: max composite diff = {max_diff:.2e}")

    # ==================================================================
    # SUMMARY
    # ==================================================================
    print(f"\n{'=' * 78}")
    print(f"RESULTS: {pass_count}/{total_checks} checks passed")
    print("=" * 78)

    if all_issues:
        # Deduplicate (same issue repeats every tick)
        unique = sorted(set(all_issues))
        print(f"\n{len(unique)} unique issue(s):")
        for issue in unique:
            print(f"  ! {issue}")
        return 1
    else:
        print("\nAll schema boundaries clean. Zero manual data munging required.")
        print("M3 can consume signature() directly.")
        print("M4 can consume update() output directly.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
