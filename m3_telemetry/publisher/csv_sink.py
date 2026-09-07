"""CSV sink callback for the TelemetryPublisher.

Writes each ``EngineTelemetryMessage`` as a row to a CSV file, creating
the header automatically from the schema field names on the first call.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import IO

from schema.telemetry_schema import EngineTelemetryMessage


class CsvSink:
    """Publish callback that appends telemetry rows to a CSV file.

    Parameters
    ----------
    path : str | Path
        Destination CSV file.  Parent directories are created if needed.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file: IO[str] | None = None
        self._writer: csv.DictWriter | None = None
        self._fields: list[str] = (
            list(EngineTelemetryMessage.model_fields.keys()) + ["active_faults"]
        )

    # ── context-manager support ─────────────────────────────────────────

    def open(self) -> "CsvSink":
        self._file = open(self.path, "w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._file, fieldnames=self._fields)
        self._writer.writeheader()
        return self

    def close(self) -> None:
        if self._file and not self._file.closed:
            self._file.close()

    def __enter__(self) -> "CsvSink":
        return self.open()

    def __exit__(self, *exc) -> None:
        self.close()

    # ── publish callback ────────────────────────────────────────────────

    def __call__(self, msg: EngineTelemetryMessage, active_faults: str = "") -> None:
        """Write one telemetry message as a CSV row.

        Parameters
        ----------
        msg : EngineTelemetryMessage
            Validated telemetry frame.
        active_faults : str
            Ground-truth fault tag (comma-separated fault names, or empty
            string if healthy).  Written as the last column of each row.
            This is **not** part of the CAN schema.
        """
        if self._writer is None:
            self.open()
        row = msg.model_dump()
        row["active_faults"] = active_faults
        self._writer.writerow(row)  # type: ignore[union-attr]
