"""Tests for the streaming harness and healthy CSV output.

Loads ``data/healthy_run_01.csv`` and validates every row against the
Pydantic schema, checks timestamp spacing, and asserts physically
plausible value ranges for each sensor channel.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

from schema.telemetry_schema import EngineTelemetryMessage

# ── Fixtures ────────────────────────────────────────────────────────────

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "healthy_run_01.csv"

EXPECTED_RATE_HZ = 10
EXPECTED_INTERVAL_S = 1.0 / EXPECTED_RATE_HZ  # 0.1 s
TIMING_TOLERANCE = 0.20  # 20 %


@pytest.fixture(scope="module")
def df() -> pd.DataFrame:
    """Load the healthy-run CSV once for all tests in this module."""
    assert CSV_PATH.exists(), f"CSV not found: {CSV_PATH}"
    return pd.read_csv(CSV_PATH)


# ── 1. Schema validation ───────────────────────────────────────────────

class TestSchemaValidation:
    """Every row must pass the Pydantic schema without errors."""

    def test_row_count(self, df: pd.DataFrame) -> None:
        assert len(df) == 300, f"Expected 300 rows, got {len(df)}"

    def test_no_missing_values(self, df: pd.DataFrame) -> None:
        total_nan = df.isnull().sum().sum()
        assert total_nan == 0, f"Found {total_nan} NaN cells"

    def test_all_rows_validate(self, df: pd.DataFrame) -> None:
        """Instantiate EngineTelemetryMessage for every row; collect any
        validation failures and report them all at once."""
        errors: list[str] = []
        for idx, row in df.iterrows():
            try:
                EngineTelemetryMessage(**row.to_dict())
            except ValidationError as exc:
                errors.append(f"Row {idx}: {exc.error_count()} error(s) — {exc}")
        assert not errors, (
            f"{len(errors)} row(s) failed schema validation:\n"
            + "\n".join(errors[:5])
        )


# ── 2. Timestamp spacing ───────────────────────────────────────────────

class TestTimestampSpacing:
    """Consecutive timestamp deltas must be within ±20 % of 100 ms."""

    def test_timestamps_monotonic(self, df: pd.DataFrame) -> None:
        diffs = df["timestamp"].diff().dropna()
        assert (diffs > 0).all(), "Timestamps are not strictly increasing"

    def test_timestamp_deltas_within_tolerance(self, df: pd.DataFrame) -> None:
        diffs = df["timestamp"].diff().dropna()
        lower = EXPECTED_INTERVAL_S * (1 - TIMING_TOLERANCE)  # 0.08 s
        upper = EXPECTED_INTERVAL_S * (1 + TIMING_TOLERANCE)  # 0.12 s
        out_of_band = diffs[(diffs < lower) | (diffs > upper)]
        assert out_of_band.empty, (
            f"{len(out_of_band)} gap(s) outside [{lower:.2f}, {upper:.2f}] s: "
            f"{out_of_band.values[:5]}"
        )


# ── 3. Physically plausible bounds ──────────────────────────────────────

# These are *operational* bounds — tighter than the schema hard-limits —
# representing what a healthy engine at 20-90 % throttle should produce.
PLAUSIBLE_BOUNDS: dict[str, tuple[float, float]] = {
    "rpm":              (500,   6_500),
    "cht":              (50,    300),
    "egt":              (300,   800),
    "oil_pressure":     (10,    100),
    "oil_temp":         (30,    220),
    "fuel_flow":        (1,     60),
    "vibration_amplitude":(0,   2),
    "vibration_freq":   (8,     110),
    "throttle_cmd":     (0,     100),
}


class TestPlausibleBounds:
    """Each sensor channel stays within physically plausible limits."""

    @pytest.mark.parametrize(
        "field, bounds",
        list(PLAUSIBLE_BOUNDS.items()),
        ids=list(PLAUSIBLE_BOUNDS.keys()),
    )
    def test_field_within_bounds(
        self, df: pd.DataFrame, field: str, bounds: tuple[float, float]
    ) -> None:
        lo, hi = bounds
        col = df[field]
        below = col[col < lo]
        above = col[col > hi]
        assert below.empty and above.empty, (
            f"{field}: {len(below)} below {lo}, {len(above)} above {hi}  "
            f"(actual range {col.min():.2f} – {col.max():.2f})"
        )
