import pandas as pd
import pytest
import glob
import os
import sys

# Ensure we can import schema
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pydantic import ValidationError
from schema.telemetry_schema import EngineTelemetryMessage

SCHEMA_FIELDS = list(EngineTelemetryMessage.model_fields.keys())
CSVS = glob.glob(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data/demo_final/*.csv'))

@pytest.mark.parametrize("csv_path", CSVS)
def test_demo_final_schema_validation(csv_path):
    df = pd.read_csv(csv_path)
    errors = []
    for idx, row in df.iterrows():
        try:
            EngineTelemetryMessage(**{k: row[k] for k in SCHEMA_FIELDS})
        except ValidationError as exc:
            errors.append(f"Row {idx}: {exc.error_count()} error(s)")
    assert not errors, f"{csv_path}: {len(errors)} row(s) failed schema validation"

@pytest.mark.parametrize("csv_path", CSVS)
def test_demo_final_no_nans_or_duplicates(csv_path):
    df = pd.read_csv(csv_path)
    nan_count = df.isnull().sum().sum()
    assert nan_count == 0, f"Found {nan_count} NaN cells"
    diffs = df["timestamp"].diff().dropna()
    assert (diffs > 0).all(), "Timestamps are not strictly increasing"
