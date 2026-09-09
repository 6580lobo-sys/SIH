"""Fixed-rate telemetry streaming harness.

Generates ``EngineTelemetryMessage`` frames at a configurable Hz rate using
the healthy-baseline signal models, optionally injects faults via the
class-based ``FaultManager`` framework, validates each frame against the
Pydantic schema, and dispatches it through a pluggable ``publish`` callback.

Run standalone::

    python -m publisher.streaming_harness --duration 10 --rate 10

Inject faults via CLI::

    python -m publisher.streaming_harness --duration 30 --rate 10 \\
        --inject misfire:5:10:0.7 \\
        --inject overheating:10::0.9 \\
        --output-csv telemetry_with_faults.csv
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import time
from typing import Callable, Optional

try:
    _M1_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "M1", "src"))
    if _M1_SRC not in sys.path:
        sys.path.insert(0, _M1_SRC)
    from twin_core.dynamics import EngineSimulator
    _HAVE_ENGINE_SIM = True
except Exception:
    _HAVE_ENGINE_SIM = False

from generator.environment import (
    ENVIRONMENT_PRESETS,
    EnvironmentProfile,
    get_environment,
)
from generator.signal_models import healthy_sample
from generator.fault_models import apply_faults
from generator.fault_injection import (
    FaultManager,
    InjectorFault,
    MisfireFault,
    NoOpFault,
    OilPressureDropFault,
    OverheatingFault,
)
from generator.throttle_profiles import (
    AVAILABLE_MODES as THROTTLE_MODES,
    generate_throttle_profile,
)
from schema.telemetry_schema import EngineTelemetryMessage


# ── Fault factory ───────────────────────────────────────────────────────────

# Registry mapping CLI fault names to their classes and any extra defaults.
FAULT_REGISTRY: dict[str, type] = {
    "misfire":             MisfireFault,
    "overheating":         OverheatingFault,
    "oil_drop_sudden":     OilPressureDropFault,
    "oil_drop_gradual":    OilPressureDropFault,
    "injector":            InjectorFault,
    "noop":                NoOpFault,
}


def _build_fault(spec: str) -> object:
    """Parse a CLI fault spec and return a ``FaultScenario`` instance.

    Format::

        <type>:<start_s>:<duration_s>:<severity>

    *   ``type`` — one of the keys in ``FAULT_REGISTRY``.
    *   ``start_s`` — float, defaults to ``0.0``.
    *   ``duration_s`` — float or empty for ``None`` (until end).
    *   ``severity`` — float 0-1, defaults to ``0.5``.

    Examples::

        misfire:5:10:0.7      # misfire from 5 s for 10 s, severity 0.7
        overheating:10::0.9   # overheating from 10 s until end, severity 0.9
        oil_drop_sudden:2:8:1 # sudden oil drop from 2 s for 8 s, severity 1
        injector:::0.3        # injector fault from 0 s until end, severity 0.3
    """
    parts = spec.split(":")
    if len(parts) < 1 or len(parts) > 4:
        raise argparse.ArgumentTypeError(
            f"Invalid fault spec {spec!r}. "
            f"Expected <type>:<start>:<duration>:<severity>"
        )

    fault_type = parts[0]
    if fault_type not in FAULT_REGISTRY:
        raise argparse.ArgumentTypeError(
            f"Unknown fault type {fault_type!r}. "
            f"Available: {', '.join(sorted(FAULT_REGISTRY))}"
        )

    start_s    = float(parts[1]) if len(parts) > 1 and parts[1] else 0.0
    duration_s = float(parts[2]) if len(parts) > 2 and parts[2] else None
    severity   = float(parts[3]) if len(parts) > 3 and parts[3] else 0.5

    cls = FAULT_REGISTRY[fault_type]

    # NoOpFault doesn't take severity
    if cls is NoOpFault:
        return cls(start_time_s=start_s, duration_s=duration_s)

    # OilPressureDropFault needs a mode and requires duration_s
    if cls is OilPressureDropFault:
        mode = "sudden" if fault_type == "oil_drop_sudden" else "gradual"
        dur = duration_s if duration_s is not None else 30.0
        return cls(
            severity=severity,
            mode=mode,
            start_time_s=start_s,
            duration_s=dur,
        )

    # OverheatingFault requires duration_s
    if cls is OverheatingFault:
        dur = duration_s if duration_s is not None else 30.0
        return cls(
            severity=severity,
            start_time_s=start_s,
            duration_s=dur,
        )

    # MisfireFault, InjectorFault — standard signature
    return cls(
        severity=severity,
        start_time_s=start_s,
        duration_s=duration_s,
    )


# ── Publisher ───────────────────────────────────────────────────────────────


class TelemetryPublisher:
    """Emit validated telemetry frames at a fixed rate.

    Parameters
    ----------
    rate_hz : float
        Target publish rate in messages per second.
    publish_cb : callable, optional
        ``f(msg: EngineTelemetryMessage, active_faults: str) -> None``.
        Defaults to printing the JSON representation to stdout.
        The *active_faults* argument is the ground-truth tag produced by
        ``FaultManager.fault_label()`` — it is **not** part of the CAN
        schema and is passed out-of-band for labelled-data generation.
    fault_manager : FaultManager, optional
        Class-based fault manager.  When supplied, the legacy
        ``active_faults`` / ``fault_start_s`` parameters in :meth:`run`
        are ignored.
    environment_name : str
        Key into ``ENVIRONMENT_PRESETS`` (default: ``"standard_day"``).
        Sets the altitude and ambient temperature for the entire run.
    throttle_mode : str
        Throttle profile mode passed to ``generate_throttle_profile()``
        (default: ``"smooth"``).
    """

    def __init__(
        self,
        rate_hz: float = 10.0,
        publish_cb: Callable[[EngineTelemetryMessage, str], None] | None = None,
        fault_manager: Optional[FaultManager] = None,
        environment_name: str = "standard_day",
        throttle_mode: str = "smooth",
    ) -> None:
        self.rate_hz = rate_hz
        self.interval = 1.0 / rate_hz
        self.publish_cb = publish_cb or self._default_publish
        self.fault_manager = fault_manager if fault_manager is not None else FaultManager()
        self.environment: EnvironmentProfile = get_environment(environment_name)
        self.environment_name = environment_name
        self.throttle_mode = throttle_mode
        self._tick = 0
        self._sim = EngineSimulator(ambient_temp=self.environment.ambient_temp_c, seed=99) if _HAVE_ENGINE_SIM else None

    def reset_engine(self) -> None:
        """Reset internal physical simulator state to nominal baseline."""
        if _HAVE_ENGINE_SIM:
            self._sim = EngineSimulator(ambient_temp=self.environment.ambient_temp_c, seed=99)

    # ── publish callback ────────────────────────────────────────────────

    @staticmethod
    def _default_publish(msg: EngineTelemetryMessage, active_faults: str) -> None:
        label = active_faults if active_faults else "healthy"
        print(f"[{label}] {msg.model_dump_json()}")

    # ── main loop ───────────────────────────────────────────────────────

    def run(
        self,
        duration_s: float,
        active_faults: list[str] | None = None,
        fault_start_s: float = 0.0,
    ) -> None:
        """Run the publish loop for *duration_s* seconds.

        Timing is maintained by computing the *next* target wall-clock time
        and sleeping only the remaining delta, so accumulated drift stays
        small even over long runs.
        """
        total_ticks = int(duration_s * self.rate_hz)
        t_start = time.perf_counter()
        msg_count = 0
        active_faults = active_faults or []

        # Log configuration
        fm_info = (
            f"FaultManager with {len(self.fault_manager)} scenario(s)"
            if len(self.fault_manager) > 0
            else "no faults"
        )
        print(
            f"[harness] starting  rate={self.rate_hz} Hz  "
            f"duration={duration_s} s  expected_msgs={total_ticks}\n"
            f"[harness] environment={self.environment_name}  "
            f"throttle_mode={self.throttle_mode}\n"
            f"[harness] {fm_info}",
            file=sys.stderr,
        )
        for s in self.fault_manager.scenarios:
            print(f"[harness]   - {s}", file=sys.stderr)

        for i in range(total_ticks):
            tick_target = t_start + i * self.interval
            elapsed_s = i * self.interval

            # --- build throttle & sensor values --------------------------
            throttle = generate_throttle_profile(elapsed_s, self.throttle_mode)
            altitude = self.environment.altitude_m
            ambient  = self.environment.ambient_temp_c

            if self._sim is not None:
                sim_out = self._sim.step(throttle, self.interval)
                sample = {
                    "rpm": sim_out["rpm"],
                    "cht_c": sim_out["cht"],
                    "egt_c": sim_out["egt"],
                    "oil_pressure_kpa": sim_out["oil_pressure"] * 6.8948,
                    "oil_temp_c": sim_out["oil_temp"],
                    "fuel_flow_lph": sim_out["fuel_flow"],
                    "vibration_g": sim_out["vibration_amplitude"],
                    "throttle_pct": throttle,
                    "ambient_temp_c": ambient,
                    "altitude_m": altitude,
                }
            else:
                sample = healthy_sample(
                    throttle,
                    altitude_m=altitude,
                    ambient_temp_c=ambient,
                )
                sample["altitude_m"] = altitude

            # --- fault injection (class-based framework) -----------------
            if len(self.fault_manager) > 0:
                sample = self.fault_manager.apply_all(elapsed_s, sample)
                fault_label = self.fault_manager.fault_label(elapsed_s)
            # --- legacy fault injection (string-based, for back-compat) --
            elif elapsed_s >= fault_start_s and active_faults:
                fault_duration_s = elapsed_s - fault_start_s
                sample = apply_faults(sample, active_faults, fault_duration_s)
                fault_label = ",".join(active_faults)
            else:
                fault_label = "healthy"

            # --- map to new schema (adapter layer) -----------------------
            mapped_sample = {
                "rpm": sample["rpm"],
                "cht": sample["cht_c"],
                "egt": sample["egt_c"],
                "oil_pressure": sample["oil_pressure_kpa"] / 6.8948,
                "oil_temp": sample["oil_temp_c"],
                "fuel_flow": sample["fuel_flow_lph"],
                "vibration_amplitude": sample["vibration_g"],
                "vibration_freq": sample["rpm"] / 60.0,
                "throttle_cmd": sample["throttle_pct"],
            }

            # --- assemble & validate via Pydantic ------------------------
            msg = EngineTelemetryMessage(
                timestamp=elapsed_s,
                msg_id=f"ENG_TELEM_{(i % 100):02d}",
                **mapped_sample,
            )

            # --- dispatch (active_faults is out-of-band, not in schema) --
            self.publish_cb(msg, fault_label)
            msg_count += 1

            # --- pace control --------------------------------------------
            now = time.perf_counter()
            sleep_for = tick_target + self.interval - now
            if sleep_for > 0:
                time.sleep(sleep_for)

        t_end = time.perf_counter()
        wall = t_end - t_start
        achieved_hz = msg_count / wall if wall > 0 else 0

        print(
            f"\n[harness] finished  msgs={msg_count}  "
            f"wall={wall:.3f} s  achieved_rate={achieved_hz:.2f} Hz",
            file=sys.stderr,
        )


# ── CLI entry-point ─────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stream synthetic engine telemetry at a fixed rate.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Fault injection examples:
  --inject misfire:5:10:0.7        Misfire from 5 s for 10 s, severity 0.7
  --inject overheating:10::0.9     Overheating from 10 s until end, severity 0.9
  --inject oil_drop_sudden:2:8:1   Sudden oil drop from 2 s for 8 s, severity 1.0
  --inject oil_drop_gradual:0:20:0.6  Gradual oil drop from 0 s for 20 s, sev 0.6
  --inject injector:::0.3          Injector fault from 0 s until end, severity 0.3
  --inject noop:0:5                NoOp (testing) from 0 s for 5 s

Multiple --inject flags can be combined to simulate overlapping faults.
Format: <type>:<start_s>:<duration_s>:<severity>
  - Omit duration for "until end" (e.g. misfire:5::0.7)
  - Omit severity for default 0.5 (e.g. misfire:5:10)

Available fault types:
  misfire, overheating, oil_drop_sudden, oil_drop_gradual, injector, noop
""",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=10.0,
        help="How many seconds to stream (default: 10).",
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=10.0,
        help="Target publish rate in Hz (default: 10).",
    )
    parser.add_argument(
        "--output-csv",
        type=str,
        default=None,
        metavar="PATH",
        help="Write telemetry rows to a CSV file instead of stdout.",
    )
    parser.add_argument(
        "--inject",
        type=str,
        action="append",
        metavar="SPEC",
        help=(
            "Inject a fault.  Format: <type>:<start_s>:<duration_s>:<severity>.  "
            "Can be specified multiple times.  See --help for examples."
        ),
    )
    parser.add_argument(
        "--environment",
        type=str,
        default="standard_day",
        choices=sorted(ENVIRONMENT_PRESETS.keys()),
        help=(
            "Environment preset controlling altitude and ambient temperature "
            "(default: standard_day)."
        ),
    )
    parser.add_argument(
        "--throttle-mode",
        type=str,
        default="smooth",
        choices=THROTTLE_MODES,
        help=(
            "Throttle profile shape "
            "(default: smooth)."
        ),
    )

    # ── Legacy fault flags (kept for backwards compatibility) ────────
    parser.add_argument(
        "--fault",
        type=str,
        action="append",
        choices=["oil_pressure_drop", "overheat", "misfire", "vibration_spike"],
        help="(Legacy) Inject a fault via the old string-based system.",
    )
    parser.add_argument(
        "--fault-start",
        type=float,
        default=0.0,
        help="(Legacy) Time in seconds when legacy faults begin (default: 0).",
    )
    args = parser.parse_args()

    # ── Build FaultManager from --inject specs ──────────────────────
    fault_manager = FaultManager()
    if args.inject:
        for spec in args.inject:
            scenario = _build_fault(spec)
            fault_manager.add(scenario)

    # ── Set up sink ─────────────────────────────────────────────────
    csv_sink = None
    publish_cb = None

    if args.output_csv:
        from publisher.csv_sink import CsvSink

        csv_sink = CsvSink(args.output_csv)
        csv_sink.open()
        publish_cb = csv_sink

    publisher = TelemetryPublisher(
        rate_hz=args.rate,
        publish_cb=publish_cb,
        fault_manager=fault_manager,
        environment_name=args.environment,
        throttle_mode=args.throttle_mode,
    )
    try:
        publisher.run(
            duration_s=args.duration,
            active_faults=args.fault,
            fault_start_s=args.fault_start,
        )
    except KeyboardInterrupt:
        print("\n[harness] Streaming interrupted by user. Shutting down cleanly...", file=sys.stderr)
    finally:
        if csv_sink is not None:
            csv_sink.close()
            print(f"[harness] CSV written to {csv_sink.path}", file=sys.stderr)


if __name__ == "__main__":
    main()
