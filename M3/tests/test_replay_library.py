"""Tests for the full replay library dataset.

Reads the library manifest and parametrises tests over every CSV
to ensure schema compliance, basic data integrity, and correct
label transitions.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import NamedTuple

import pandas as pd
import pytest
from pydantic import ValidationError

from schema.telemetry_schema import EngineTelemetryMessage

# ── Configuration ───────────────────────────────────────────────────────────

LIBRARY_DIR = Path(__file__).resolve().parent.parent / "data" / "replay_library"
MANIFEST_PATH = LIBRARY_DIR / "manifest.csv"

RATE_HZ = 10.0


class ReplaySpec(NamedTuple):
    filename: str
    environment: str
    throttle_mode: str
    fault: str
    expected_rows: int
    category: str


def _load_manifest() -> list[ReplaySpec]:
    """Parse the manifest.csv file into a list of specs."""
    if not MANIFEST_PATH.exists():
        return []
    
    specs = []
    with open(MANIFEST_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            specs.append(ReplaySpec(
                filename=r["filename"],
                environment=r["environment"],
                throttle_mode=r["throttle_mode"],
                fault=r["fault"],
                expected_rows=int(r["rows"]),
                category=r.get("category", "training/test data"),
            ))
    return specs


SPECS = _load_manifest()
SCHEMA_FIELDS = list(EngineTelemetryMessage.model_fields.keys())


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module", params=SPECS, ids=lambda s: s.filename)
def replay_data(request) -> tuple[pd.DataFrame, ReplaySpec]:
    """Load one CSV from the manifest and return (DataFrame, ReplaySpec)."""
    spec: ReplaySpec = request.param
    path = LIBRARY_DIR / spec.filename
    assert path.exists(), f"CSV from manifest not found: {path}"
    df = pd.read_csv(path)
    return df, spec


# ── Tests ───────────────────────────────────────────────────────────────────

class TestReplayLibrary:
    
    def test_row_count(self, replay_data: tuple[pd.DataFrame, ReplaySpec]) -> None:
        """Confirm row count matches the manifest with a small tolerance."""
        df, spec = replay_data
        # Allow +/- 2 rows for slight timing variations in the harness
        assert abs(len(df) - spec.expected_rows) <= 2, (
            f"Expected ~{spec.expected_rows} rows, got {len(df)}"
        )

    def test_no_nans_or_duplicates(self, replay_data: tuple[pd.DataFrame, ReplaySpec]) -> None:
        """Confirm no NaNs and timestamps are strictly monotonically increasing."""
        df, _ = replay_data
        
        nan_count = df.isnull().sum().sum()
        assert nan_count == 0, f"Found {nan_count} NaN cells in the dataframe"
        
        diffs = df["timestamp"].diff().dropna()
        assert (diffs > 0).all(), "Timestamps are not strictly increasing (duplicates or out of order)"

    def test_schema_validation(self, replay_data: tuple[pd.DataFrame, ReplaySpec]) -> None:
        """Validate every row against EngineTelemetryMessage."""
        df, spec = replay_data
        errors: list[str] = []
        for idx, row in df.iterrows():
            try:
                EngineTelemetryMessage(**{k: row[k] for k in SCHEMA_FIELDS})
            except ValidationError as exc:
                errors.append(f"Row {idx}: {exc.error_count()} error(s) -- {exc}")
        
        assert not errors, (
            f"{spec.filename}: {len(errors)} row(s) failed schema validation:\n"
            + "\n".join(errors[:5])
        )

    def test_fault_labels(self, replay_data: tuple[pd.DataFrame, ReplaySpec]) -> None:
        """Confirm active_faults logic is correct for the specific run."""
        df, spec = replay_data
        
        # Fill NaNs with empty string to handle pandas parsing just in case
        labels = df["active_faults"].fillna("")
        
        if spec.fault == "none":
            # Healthy runs should have purely 'healthy' labels
            bad = labels[labels != "healthy"]
            assert bad.empty, f"Healthy run has faulted labels: {bad.unique()}"
            return
            
        # Determine nominal fault window for basic cases
        if "multi" in spec.filename or "demo" in spec.filename:
            # Multi-faults and demo scenarios have multiple complex windows
            # Just do a generic check that faults activate and healthy states exist
            assert any(l != "healthy" for l in labels), "Fault scenario never activated"
            assert any(l == "healthy" for l in labels), "Fault scenario never healthy"
            return
            
        if "stress" in spec.filename:
            start_s, end_s = 15.0, 25.0
        else:
            start_s, end_s = 10.0, 20.0
            
        start_row = int(start_s * RATE_HZ)
        end_row = int(end_s * RATE_HZ)
        
        # 1. Pre-fault window must be entirely healthy
        pre_fault = labels.iloc[:start_row]
        bad_pre = pre_fault[pre_fault != "healthy"]
        assert bad_pre.empty, f"Pre-fault rows contain non-healthy labels: {bad_pre.unique()}"
        
        # 2. During nominal window, active_faults must contain the fault
        window = labels.iloc[start_row:end_row]
        bad_window = window[window == "healthy"]
        assert bad_window.empty, f"Rows during nominal fault window are marked healthy"
        
        # 3. Post-fault: either snaps back to healthy or has a recovery tail
        post = labels.iloc[end_row:]
        has_recovery_tail = spec.fault in ("overheating", "oil_pressure_drop_gradual", "oil_pressure_drop_sudden", "oil_pressure_drop")
        
        if has_recovery_tail:
            # Should have at least one row still faulted
            still_faulted = post[post != "healthy"]
            assert not still_faulted.empty, "Expected recovery tail but labels snapped to healthy instantly"
        else:
            # Instant-off
            first_post = post.iloc[0]
            assert first_post == "healthy", f"Expected instant recovery, but first post-fault row is {first_post}"
