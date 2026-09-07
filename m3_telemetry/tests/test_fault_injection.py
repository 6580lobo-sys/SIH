"""Tests for the generated fault CSV datasets.

Loads each of the four fault CSVs produced by
``scripts/generate_fault_csvs.py`` and asserts:

1. Every row passes ``EngineTelemetryMessage`` Pydantic validation (faults
   must not produce physically impossible values).
2. During the labelled fault window, the primary affected sensor's mean
   differs from the pre-fault healthy baseline by more than a threshold
   (proves the fault has a measurable effect).
3. Outside the fault window, the ``active_faults`` column is empty
   (ground-truth labels are correct).

Usage::

    pytest tests/test_fault_injection.py -v
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

import pandas as pd
import pytest
from pydantic import ValidationError

from schema.telemetry_schema import EngineTelemetryMessage

# ── Configuration ───────────────────────────────────────────────────────────

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Each fault CSV was generated with:
#   30 s @ 10 Hz  →  300 rows
#   Fault window: [10.0 s, 20.0 s)  →  rows [100, 200)
#   Severity: 0.7

RATE_HZ         = 10.0
FAULT_START_S   = 10.0
FAULT_END_S     = 20.0
FAULT_START_ROW = int(FAULT_START_S * RATE_HZ)   # 100
FAULT_END_ROW   = int(FAULT_END_S   * RATE_HZ)   # 200


class FaultSpec(NamedTuple):
    """Description of one fault CSV for parametrised testing."""
    csv_name: str
    fault_label: str          # expected value in active_faults column
    primary_sensor: str       # the sensor most affected by this fault
    direction: str            # "up" or "down" — expected deviation direction
    min_delta_pct: float      # minimum % change from baseline to pass


FAULT_SPECS = [
    FaultSpec(
        csv_name="fault_misfire_01.csv",
        fault_label="misfire",
        primary_sensor="rpm",
        direction="down",
        min_delta_pct=10.0,   # RPM should drop >10 % during misfire
    ),
    FaultSpec(
        csv_name="fault_overheating_01.csv",
        fault_label="overheating",
        primary_sensor="cht",
        direction="up",
        min_delta_pct=5.0,    # CHT should rise >5 % during overheating
    ),
    FaultSpec(
        csv_name="fault_oil_pressure_drop_01.csv",
        fault_label="oil_pressure_drop_gradual",
        primary_sensor="oil_pressure",
        direction="down",
        min_delta_pct=20.0,   # Oil pressure should drop >20 %
    ),
    FaultSpec(
        csv_name="fault_injector_01.csv",
        fault_label="injector_fault",
        primary_sensor="fuel_flow",
        direction="down",
        min_delta_pct=15.0,   # Fuel flow should drop >15 %
    ),
]


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module", params=FAULT_SPECS, ids=lambda s: s.csv_name)
def fault_data(request) -> tuple[pd.DataFrame, FaultSpec]:
    """Load one fault CSV and return (DataFrame, FaultSpec)."""
    spec: FaultSpec = request.param
    path = DATA_DIR / spec.csv_name
    assert path.exists(), f"CSV not found: {path}"
    df = pd.read_csv(path)
    return df, spec


# ── Helper slices ───────────────────────────────────────────────────────────

def _pre_fault_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Rows before the fault window (healthy baseline)."""
    return df.iloc[:FAULT_START_ROW]


def _fault_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Rows inside the fault window."""
    return df.iloc[FAULT_START_ROW:FAULT_END_ROW]


def _post_fault_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Rows after the fault window (should be healthy again)."""
    return df.iloc[FAULT_END_ROW:]


# ── Schema fields (exclude non-schema columns for validation) ───────────────

SCHEMA_FIELDS = list(EngineTelemetryMessage.model_fields.keys())


# ── 1. Schema validation ───────────────────────────────────────────────────

class TestSchemaValidation:
    """Every row — including faulted rows — must still pass the Pydantic
    schema.  Faults should distort values, not break physical constraints."""

    def test_row_count(self, fault_data: tuple[pd.DataFrame, FaultSpec]) -> None:
        df, spec = fault_data
        assert len(df) == 300, (
            f"{spec.csv_name}: expected 300 rows, got {len(df)}"
        )

    def test_no_missing_schema_values(
        self, fault_data: tuple[pd.DataFrame, FaultSpec]
    ) -> None:
        df, spec = fault_data
        nan_count = df[SCHEMA_FIELDS].isnull().sum().sum()
        assert nan_count == 0, (
            f"{spec.csv_name}: found {nan_count} NaN cells in schema fields"
        )

    def test_all_rows_pass_pydantic(
        self, fault_data: tuple[pd.DataFrame, FaultSpec]
    ) -> None:
        """Instantiate EngineTelemetryMessage for every row; collect errors."""
        df, spec = fault_data
        errors: list[str] = []
        for idx, row in df.iterrows():
            try:
                EngineTelemetryMessage(
                    **{k: row[k] for k in SCHEMA_FIELDS}
                )
            except ValidationError as exc:
                errors.append(
                    f"Row {idx}: {exc.error_count()} error(s) -- {exc}"
                )
        assert not errors, (
            f"{spec.csv_name}: {len(errors)} row(s) failed schema "
            f"validation:\n" + "\n".join(errors[:5])
        )


# ── 2. Fault effect is measurable ──────────────────────────────────────────

class TestFaultEffect:
    """The primary affected sensor must deviate measurably from the healthy
    baseline during the fault window."""

    def test_primary_sensor_deviates(
        self, fault_data: tuple[pd.DataFrame, FaultSpec]
    ) -> None:
        df, spec = fault_data

        baseline_mean = _pre_fault_rows(df)[spec.primary_sensor].mean()
        fault_mean    = _fault_rows(df)[spec.primary_sensor].mean()

        # Percentage deviation
        if baseline_mean == 0:
            delta_pct = abs(fault_mean) * 100.0
        else:
            delta_pct = abs(fault_mean - baseline_mean) / abs(baseline_mean) * 100.0

        assert delta_pct >= spec.min_delta_pct, (
            f"{spec.csv_name} [{spec.primary_sensor}]: "
            f"fault deviation = {delta_pct:.1f}%, "
            f"expected >= {spec.min_delta_pct}%  "
            f"(baseline_mean={baseline_mean:.2f}, fault_mean={fault_mean:.2f})"
        )

    def test_deviation_direction(
        self, fault_data: tuple[pd.DataFrame, FaultSpec]
    ) -> None:
        """Verify the deviation goes in the physically expected direction."""
        df, spec = fault_data

        baseline_mean = _pre_fault_rows(df)[spec.primary_sensor].mean()
        fault_mean    = _fault_rows(df)[spec.primary_sensor].mean()

        if spec.direction == "up":
            assert fault_mean > baseline_mean, (
                f"{spec.csv_name}: expected {spec.primary_sensor} to rise "
                f"during fault, but baseline={baseline_mean:.2f} > "
                f"fault={fault_mean:.2f}"
            )
        else:
            assert fault_mean < baseline_mean, (
                f"{spec.csv_name}: expected {spec.primary_sensor} to drop "
                f"during fault, but baseline={baseline_mean:.2f} < "
                f"fault={fault_mean:.2f}"
            )


# ── 3. Ground-truth labels are correct ─────────────────────────────────────

class TestLabels:
    """The ``active_faults`` column must be empty outside the fault window
    and contain the correct fault name inside it."""

    def test_pre_fault_labels_empty(
        self, fault_data: tuple[pd.DataFrame, FaultSpec]
    ) -> None:
        df, spec = fault_data
        pre = _pre_fault_rows(df)["active_faults"]
        bad = pre[pre != "healthy"]
        assert bad.empty, (
            f"{spec.csv_name}: {len(bad)} pre-fault row(s) have non-healthy "
            f"labels: {bad.unique()}"
        )

    def test_fault_window_labels_correct(
        self, fault_data: tuple[pd.DataFrame, FaultSpec]
    ) -> None:
        df, spec = fault_data
        during = _fault_rows(df)["active_faults"]
        # All rows in the window must contain the fault label
        bad = during[~during.str.contains(spec.fault_label, na=False)]
        assert bad.empty, (
            f"{spec.csv_name}: {len(bad)} fault-window row(s) missing "
            f"label '{spec.fault_label}': {bad.unique()}"
        )

    def test_post_fault_labels_healthy(
        self, fault_data: tuple[pd.DataFrame, FaultSpec]
    ) -> None:
        """After the fault window (plus any recovery tail), labels should
        eventually return to healthy.

        ``OverheatingFault`` and ``OilPressureDropFault`` have physical
        recovery tails (exponential cooldown) that extend the ``is_active``
        window well beyond the nominal ``duration_s``.  For those faults we
        only assert that **at least some** post-nominal-window rows are still
        labelled (confirming the recovery tail exists).  For instant-off
        faults like ``MisfireFault`` and ``InjectorFault`` we assert the very
        first row after the window is already healthy.
        """
        df, spec = fault_data
        post = _post_fault_rows(df)["active_faults"]

        # Faults with recovery tails — just confirm at least 1 row in the
        # post-window region still carries the fault label (proving the
        # cooldown tail is being generated), and that the label is correct.
        has_recovery_tail = spec.fault_label in (
            "overheating",
            "oil_pressure_drop_gradual",
            "oil_pressure_drop_sudden",
        )

        if has_recovery_tail:
            still_faulted = post[post.str.contains(spec.fault_label, na=False)]
            assert not still_faulted.empty, (
                f"{spec.csv_name}: expected recovery-tail rows still labelled "
                f"'{spec.fault_label}' but found none"
            )
        else:
            # Instant-off faults: the very first row after the window must
            # already be healthy.
            first_post = post.iloc[0]
            assert first_post == "healthy", (
                f"{spec.csv_name}: first post-fault row is '{first_post}', "
                f"expected 'healthy'"
            )
