"""
replay.py — Replay a mission-log CSV through the digital-twin + residual
pipeline.

The CSV provides the "actual" sensor readings. The twin regenerates
**predicted** values on the fly from the logged ``throttle_cmd`` column —
it does NOT read a "predicted" column from the file.  This is the whole
point: the twin's physics model re-derives what the engine *should* have
done, and any divergence from what it *actually* did shows up as a
residual.
"""

import csv
import os
from typing import List, Optional

from twin_core.dynamics import EngineSimulator
from twin_core.twin import DigitalTwin
from twin_core.residual import ResidualEngine


# Schema columns that the CSV must contain (matches the agreed schema)
REQUIRED_COLUMNS = [
    "timestamp", "rpm", "cht", "egt", "oil_pressure", "oil_temp",
    "fuel_flow", "vibration_amplitude", "vibration_freq", "throttle_cmd",
]


# ---------------------------------------------------------------------------
# CSV I/O helpers
# ---------------------------------------------------------------------------

def load_csv(path: str) -> List[dict]:
    """Load a mission-log CSV into a list of dicts with float values.

    Parameters
    ----------
    path : str
        Path to the CSV file.

    Returns
    -------
    list[dict]
        One dict per row, all values cast to float.

    Raises
    ------
    ValueError
        If required columns are missing.
    """
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        missing = [c for c in REQUIRED_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise ValueError(
                f"CSV is missing required columns: {missing}. "
                f"Found: {reader.fieldnames}"
            )
        rows = []
        for row in reader:
            rows.append({k: float(v) for k, v in row.items()
                         if k in REQUIRED_COLUMNS})
    return rows


def save_csv(rows: List[dict], path: str) -> None:
    """Save a list of schema dicts to CSV.

    Parameters
    ----------
    rows : list[dict]
        Time series in the agreed schema.
    path : str
        Output file path.
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=REQUIRED_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, 0.0) for k in REQUIRED_COLUMNS})


# ---------------------------------------------------------------------------
# Replay actual source
# ---------------------------------------------------------------------------

class CsvReplaySource:
    """An actual-source callable that yields rows from a loaded CSV.

    Conforms to the ``(throttle_cmd, dt) -> dict`` interface expected by
    :class:`DigitalTwin`, but ignores both arguments — the "actual"
    readings come from the file, not from a simulator.

    Parameters
    ----------
    rows : list[dict]
        Loaded CSV rows (output of :func:`load_csv`).
    """

    def __init__(self, rows: List[dict]):
        self._rows = rows
        self._index = 0

    def step(self, throttle_cmd: float, dt: float) -> dict:
        """Return the next CSV row.

        ``throttle_cmd`` and ``dt`` are accepted for API compatibility
        but ignored — the actual data is pre-recorded.
        """
        if self._index >= len(self._rows):
            raise StopIteration("CSV replay exhausted — no more rows.")
        row = self._rows[self._index]
        self._index += 1
        return row

    def reset(self) -> None:
        """Rewind to the start of the CSV."""
        self._index = 0


# ---------------------------------------------------------------------------
# High-level replay function
# ---------------------------------------------------------------------------

def replay_csv(csv_path: str,
               ambient_temp: float = 25.0,
               ref_seed: int = 42,
               ewma_alpha: float = 0.10) -> List[dict]:
    """Replay a mission-log CSV through the twin + residual pipeline.

    Parameters
    ----------
    csv_path : str
        Path to the mission-log CSV.
    ambient_temp : float
        Ambient temperature for the reference model.
    ref_seed : int
        Seed for the reference simulator (must match the original run
        for exact comparison).
    ewma_alpha : float
        EWMA smoothing factor for the residual engine.

    Returns
    -------
    list[dict]
        Residual output per tick, same schema as
        :meth:`ResidualEngine.update`.
    """
    rows = load_csv(csv_path)
    source = CsvReplaySource(rows)

    twin = DigitalTwin(
        actual_source=source.step,
        ambient_temp=ambient_temp,
        ref_seed=ref_seed,
    )
    residual_eng = ResidualEngine(ewma_alpha=ewma_alpha)

    results = []
    for i, row in enumerate(rows):
        throttle_cmd = row["throttle_cmd"]
        # Compute dt from timestamps (fall back to 0.1 for first row)
        if i > 0:
            dt = row["timestamp"] - rows[i - 1]["timestamp"]
        else:
            dt = 0.1
        pair = twin.step(throttle_cmd, dt)
        result = residual_eng.update(pair)
        results.append(result)

    return results


# ---------------------------------------------------------------------------
# Sanity check: generate a fault CSV from live run, replay it, compare
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from twin_core.m3_fault_source import FaultedSimulator

    DT = 0.1
    FAULT_TIME = 30.0
    DURATION = 50.0
    THROTTLE = 60.0
    CSV_PATH = os.path.join(os.path.dirname(__file__),
                            "..", "..", "data", "test_overheating.csv")

    # === Phase 1: Generate a fault scenario and save as CSV ===============
    print("=== Phase 1: Live run (overheating fault at t=30s) ===")
    faulted = FaultedSimulator(
        fault_type="overheating", fault_time=FAULT_TIME, seed=99
    )
    twin_live = DigitalTwin(actual_source=faulted.step, ref_seed=42)
    residual_live = ResidualEngine()

    profile = [THROTTLE] * int(DURATION / DT)
    live_pairs = twin_live.run(profile, DT)
    live_results = residual_live.process_batch(live_pairs)

    # Save the "actual" stream as a CSV (this is what M2 would produce)
    actual_rows = [p["actual"] for p in live_pairs]
    save_csv(actual_rows, CSV_PATH)
    print(f"  Saved {len(actual_rows)} rows to {CSV_PATH}")

    # Grab live signature at end
    live_sig = residual_live.signature()

    # === Phase 2: Replay the CSV ==========================================
    print("\n=== Phase 2: Replay from CSV ===")
    replay_results = replay_csv(CSV_PATH, ref_seed=42)
    print(f"  Replayed {len(replay_results)} rows")

    # === Phase 3: Compare =================================================
    print("\n=== Comparison: Live vs. Replay ===")
    channels = ["rpm", "egt", "cht", "oil_pressure", "oil_temp",
                "fuel_flow", "vibration_amplitude", "vibration_freq"]

    print(f"\n{'t(s)':>6}  {'Live comp':>10}  {'Replay comp':>12}  "
          f"{'Live EGT res':>13}  {'Replay EGT res':>15}")
    print("-" * 70)

    sample_every = int(5.0 / DT)
    for i in range(0, min(len(live_results), len(replay_results)),
                   sample_every):
        lr = live_results[i]
        rr = replay_results[i]
        print(f"{lr['timestamp']:6.1f}  "
              f"{lr['composite_score']:10.6f}  "
              f"{rr['composite_score']:12.6f}  "
              f"{lr['residuals'].get('egt', 0):13.6f}  "
              f"{rr['residuals'].get('egt', 0):15.6f}")

    # Check dominant channel matches
    # Rebuild residual engine state at end of replay for signature
    replay_source2 = CsvReplaySource(load_csv(CSV_PATH))
    twin_replay2 = DigitalTwin(actual_source=replay_source2.step, ref_seed=42)
    res_eng2 = ResidualEngine()
    rows2 = load_csv(CSV_PATH)
    for i, row in enumerate(rows2):
        dt = row["timestamp"] - rows2[i-1]["timestamp"] if i > 0 else 0.1
        pair = twin_replay2.step(row["throttle_cmd"], dt)
        res_eng2.update(pair)
    replay_sig = res_eng2.signature()

    live_top = [ch for ch, _ in live_sig["dominant_channels"][:3]]
    replay_top = [ch for ch, _ in replay_sig["dominant_channels"][:3]]

    print(f"\nLive  dominant channels: {live_top}")
    print(f"Replay dominant channels: {replay_top}")

    if live_top == replay_top:
        print("\nPASS: Replay reproduces the same fault signature.")
    else:
        print("\nWARNING: Dominant channels differ — investigate.")

    # Cleanup note
    print(f"\nTest CSV saved at: {os.path.abspath(CSV_PATH)}")
