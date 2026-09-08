# M6 Integration Contract: M3 Telemetry Publisher

This document serves as the formal integration contract for the M6 Orchestrator team to consume the M3 Telemetry stream. Since the full M1/M2 simulation dependencies are not available in this local repository, this contract guarantees the interface and behavior of the M3 subsystem so integration can proceed unblocked.

## 1. Clean Public API (`m3_telemetry.publisher.api`)

M6 should **not** instantiate `TelemetryPublisher` directly. Instead, import and use the clean programmatic API located in `m3_telemetry.publisher.api`:

### `create_publisher(environment, throttle_mode, faults=None)`
Creates and configures the telemetry stream.
- **`environment`** (`str`): Options: `"standard_day"`, `"hot_day"`, `"high_altitude"`.
- **`throttle_mode`** (`str`): Options: `"smooth"`, `"rapid_transient"`, `"idle_to_cruise"`, etc.
- **`faults`** (`list[dict]`): Optional list of initial fault dictionaries to schedule. E.g. `[{"type": "misfire", "start_s": 5.0, "duration_s": 10.0, "severity": 0.8}]`.
- **Returns**: A configured `TelemetryPublisher` instance.

### `start_stream(publisher, callback, duration_s=None)`
Starts the stream loop and dispatches messages to your callback.
- **`publisher`**: The instance returned by `create_publisher()`.
- **`callback`** (`Callable[[EngineTelemetryMessage, str], None]`): Your orchestrator's ingestion function. Receives the validated Pydantic message and the ground-truth fault label.
- **`duration_s`** (`float`): How long to run the simulation (in seconds). If `None`, runs indefinitely.
- **Note**: This is a blocking call. If M6 needs to inject faults asynchronously mid-run, this should be executed in a background thread.

### `load_replay_csv(path)`
Yields historical M3 telemetry records from a CSV file.
- **`path`** (`str`): Absolute or relative path to the CSV file.
- **Returns**: An iterator that yields `EngineTelemetryMessage` instances.

---

## 2. Dynamic Fault Injection (Mid-Run)

M6's Orchestrator can inject faults dynamically while `start_stream` is running.

**Mechanism:** Access the `fault_manager` on the publisher instance.
```python
from m3_telemetry.generator.fault_injection import MisfireFault

# Inside M6's event loop or API handler:
new_fault = MisfireFault(severity=0.8, start_time_s=10.0, duration_s=5.0)
publisher.fault_manager.add(new_fault)
```
*(See `m3_telemetry/scripts/test_m6_integration.py` for a working, thread-safe example).*

---

## 3. Data Schema Guarantees

M3 guarantees that every emitted `EngineTelemetryMessage` object strictly adheres to the requested M1/M2/M4 naming conventions.

| M3 Field Attribute | Type | Unit / Description |
| :--- | :--- | :--- |
| `timestamp` | `float` | Simulation seconds from start. |
| `rpm` | `float` | Engine RPM. |
| `cht` | `float` | Cylinder Head Temperature (°C). |
| `egt` | `float` | Exhaust Gas Temperature (°C). |
| `oil_pressure` | `float` | **PSI** (Converted from internal kPa). |
| `oil_temp` | `float` | Oil Temperature (°C). |
| `fuel_flow` | `float` | Fuel Flow (L/hr). |
| `vibration_amplitude`| `float` | Vibration magnitude (g). |
| `throttle_cmd` | `float` | Throttle percentage (0-100%). |
| `msg_id` | `str` | Internal CAN frame ID. |
| `vibration_freq` | `float` | Vibration frequency (Hz). |

*(Note: `altitude_m` and `ambient_temp_c` are stripped from the output as requested by M1/M2).*

---

## 4. Suggested Orchestrator Updates

In `orchestrator.py`, replace your direct instantiation in `_run_live_loop` with the new API:

```diff
-        publisher = TelemetryPublisher(
-            rate_hz          = self._rate_hz,
-            publish_cb       = _cb,
-            fault_manager    = self._fault_manager,
-            environment_name = self._environment,
-            throttle_mode    = self._throttle_mode,
-        )
-        publisher.run(duration_s=duration_s if duration_s is not None else 86400.0)

+        from m3_telemetry.publisher.api import create_publisher, start_stream
+        
+        publisher = create_publisher(
+            environment=self._environment,
+            throttle_mode=self._throttle_mode
+        )
+        # Re-attach the orchestrator's existing fault manager reference
+        publisher.fault_manager = self._fault_manager
+        
+        start_stream(
+            publisher=publisher, 
+            callback=_cb, 
+            duration_s=duration_s if duration_s is not None else 86400.0
+        )
```
