# M1 Track — Digital Twin Core & Physics Model (Working Guide)

Your ownership per the plan: **Block A (twin architecture)**, the **analytical physics/thermo model**, and the **predicted-vs-actual residual engine (USP #1)**. You pair tightly with M2 on Days 1–2 (your model's signal shape is what the fault injector has to corrupt), and with M3 on Day 4 (residual sensitivity per fault type).

---

## 1. What the SI problem statement actually needs from your block

Stripping the SI doc down to what's *yours*:

- **A. Digital Twin Core Framework** — a virtual engine model that stays synchronized with live data, modular enough to extend later.
- **Health Monitoring parameters you must simulate/predict**: RPM, CHT, EGT, oil pressure & temperature, fuel flow, vibration signatures (battery/alternator health and injection timing are stretch/roadmap, not sprint-critical).
- **USP #1 (yours)**: the shift from *threshold-based* to *predicted-vs-actual residual* monitoring — this is the single most-judged technical differentiator, because it's literally what separates a "digital twin" from "a dashboard with alarms."

Everything else downstream (health index, RUL, mission scoring, explainability) is built **on top of your residual output**, so the schema you emit on Day 1 is a contract the rest of the team is blocked on. Treat it like an API you're shipping, not a script you're iterating privately.

---

## 2. The physics model — the approach that's actually tractable in a week

You don't need a full thermodynamic Otto/Diesel cycle simulation (that's explicitly deferred to Weeks 2–3 in the roadmap). What you need is a **semi-empirical, physics-informed analytical model**: real causal relationships between control inputs and engine parameters, driven by simple algebraic/first-order-lag equations rather than full combustion physics.

**Inputs (control/environment):**
- Throttle command (0–100%)
- Ambient temperature, altitude (for mission profiles later)
- Time (for transients)

**State variables you derive (in this rough causal order):**
1. **RPM** — first-order lag toward a throttle-commanded target RPM (`τ` = engine inertia time constant). This is your root variable; everything else is a function of RPM + load.
2. **Fuel flow** — function of RPM and throttle/load via a simplified BSFC (brake-specific fuel consumption) map — roughly linear-ish with load, with a small RPM² term for pumping losses.
3. **EGT** — function of fuel flow and air-fuel ratio; rises with load, has a lag relative to RPM changes (exhaust gas doesn't heat instantly).
4. **CHT** — slower first-order lag driven by combustion heat input (~fuel flow) minus cooling term (a function of airspeed/altitude you can stub as constant for the sprint).
5. **Oil pressure** — roughly proportional to RPM (pump-driven) with a temperature-dependent viscosity correction.
6. **Oil temperature** — slow first-order lag toward a steady-state value driven by CHT/friction (RPM²-ish term).
7. **Vibration** — base sinusoid at engine firing frequency (proportional to RPM) plus broadband noise; this channel is what most fault signatures (misfire, injector fault) will distort, so keep it structured (amplitude + frequency + phase), not just noise.

**Why this matters for the residual engine:** each of these should be expressible as `predicted = f(control_inputs, time)`. Your twin is just this same `f()` running continuously, fed the *same* control inputs as the live/faulted stream. Residual = `actual − predicted`, per channel, normalized (z-score or % of nominal range) so a composite anomaly score is comparable across RPM (thousands) and oil pressure (tens) scales.

**Schema you need to lock down with M2/M3 on Day 1** (this is the actual Day-1 deliverable, not just "a model exists"):
```
timestamp, rpm, cht, egt, oil_pressure, oil_temp, fuel_flow,
vibration_amplitude, vibration_freq, throttle_cmd, altitude, ambient_temp
```
Predicted and actual streams must share this exact schema so residuals are a trivial subtraction, and M3 can build the feature/health-index spec against a schema that won't shift under them later.

---

## 3. Day-by-day walkthrough (your seat)

| Day | What you're actually doing | Done-when |
|---|---|---|
| **1** | Build the analytical model above as a standalone Python module producing a live time series. Lock the schema with M2 (streaming harness) and M3 (feature spec) — this is a real meeting, not a Slack message. | You can run the model standalone and get a clean multi-channel time series; schema is written down somewhere everyone can see it. |
| **2** | Duplicate the model into a **second, independent instance** that runs off the *same control inputs* as the live/faulted stream. This is the twin scaffold — two parallel signal paths, not yet compared. | You have two time series running in lockstep (predicted vs. what will become actual) even before faults exist. |
| **3** | **Residual engine (USP #1)**: subtract predicted from actual per channel, normalize, produce a composite score. Feed both the faulted stream (from M2) and the clean stream through it so you can show the residual staying flat on healthy data and spiking on faulted data. | Residual is near-zero on healthy data and visibly spikes when M2's fault injector is toggled on, per channel and composite. |
| **4** | Tune per-channel residual sensitivity with M3 so each fault type (misfire, injector, overheating, oil-pressure drop, vibration spike) produces a distinguishable residual signature rather than one channel dominating. | Each of M2's 5 fault types produces a visually/numerically distinct residual pattern M3 can classify against. |
| **5** | Replay mode: same model, but instead of live control inputs it reads a logged CSV and reproduces predicted vs. actual against historical data. | Feeding a saved mission-log CSV back through the twin reproduces the same residual behavior as the live run did. |
| **6** | Integration pass: make sure your residual output survives contact with M2's finalized schema and M4's dashboard expectations without special-casing. | Full pipeline (fault injector → twin → residual → dashboard) runs end-to-end without you manually patching data shapes. |
| **7** | Buffer/bugfix + help M5 with the architecture diagram (you own this jointly — you're the one who actually knows the twin/residual loop well enough to draw it accurately). | Diagram exists and matches what's actually running, not what was planned Day 1. |

---

## 4. Antigravity build prompts — one step at a time

Use these in order. Each is scoped to one working session, produces something runnable/testable on its own, and each references what the previous step already built so Antigravity doesn't re-architect from scratch each time. Paste them one at a time; verify the "check" before moving to the next.

### Step 1 — Repo scaffold + steady-state engine maps
```
Set up a Python module `twin_core/` inside the existing project repo (align paths
with whatever M5 scaffolded — assume `src/twin_core/` if unsure, note it if you
create a new top-level folder).

Build `twin_core/engine_maps.py`: pure functions implementing steady-state
relationships for a small aero piston engine, given throttle (0-100) and RPM:
- fuel_flow(rpm, throttle) -> L/hr, roughly linear in throttle with a small RPM^2
  pumping-loss term
- egt_steady(rpm, fuel_flow) -> deg C, increases with fuel flow and RPM
- cht_steady(rpm, fuel_flow, ambient_temp) -> deg C
- oil_pressure_steady(rpm, oil_temp) -> psi, proportional to RPM with a
  viscosity correction from oil_temp
- oil_temp_steady(rpm, cht) -> deg C

Use realistic small-aero-piston-engine magnitude ranges (e.g. RPM 1500-6000,
CHT 90-260C, EGT 600-950C, oil pressure 20-90 psi, oil temp 60-120C, fuel flow
2-15 L/hr) — pull real reference ranges if you're unsure rather than guessing.

Write a small `if __name__ == "__main__"` block that prints these values at a
few RPM/throttle combos so I can sanity-check the ranges before moving on.

Check before I approve: run it and show me output at throttle=20,50,90 and
confirm the numbers look like a real small aero piston engine, not a car engine.
```

### Step 2 — Dynamic time-series simulator (state + lag + noise)
```
Extend twin_core/ with `dynamics.py`: a stateful EngineSimulator class that
turns the steady-state maps from engine_maps.py into a live time series using
first-order lag dynamics (state moves toward the steady-state target each
tick, at a channel-specific time constant — RPM fastest, oil_temp slowest).

Required behavior:
- .step(throttle_cmd, dt) advances internal state by dt seconds and returns a
  dict matching this exact schema:
  {timestamp, rpm, cht, egt, oil_pressure, oil_temp, fuel_flow,
   vibration_amplitude, vibration_freq, throttle_cmd}
- vibration_amplitude/freq: freq scales with RPM (engine firing frequency),
  amplitude = small base value + low broadband noise
- Add small realistic sensor noise to every channel (do NOT add noise inside
  engine_maps.py — that stays pure/deterministic; noise belongs in dynamics.py)
- .run(throttle_profile, dt) that steps through a list/array of throttle
  commands and returns the full time series as a list of dicts or a pandas
  DataFrame — I'll need this for both live and replay use later.

Check before I approve: run .run() over a throttle profile that ramps
20->80->20 over ~60 seconds and show me that RPM responds fast, CHT/oil_temp
visibly lag behind it, and nothing goes negative or NaN.
```

### Step 3 — Twin scaffold (two synchronized instances)
```
Add `twin_core/twin.py`. Build a DigitalTwin class that holds TWO
EngineSimulator instances — "reference" (the physics prediction) and a
pluggable "actual" source.

Requirements:
- reference always runs the pure model from dynamics.py against the given
  throttle_cmd stream.
- actual is injectable: for now, wire it to a second EngineSimulator instance
  fed the SAME throttle_cmd sequence (so with no fault, actual ≈ reference
  plus noise only). Design the interface so M2 can later swap this "actual"
  source for their live/faulted stream without changing DigitalTwin's API —
  e.g. actual_source should be any callable/generator yielding dicts matching
  our schema.
- DigitalTwin.step(throttle_cmd, dt) returns both dicts side by side:
  {"predicted": {...}, "actual": {...}}

Check before I approve: run it standalone with actual_source = a second
identical simulator, confirm predicted and actual track closely (only noise-
level divergence, no fault yet).
```

### Step 4 — Residual engine (USP #1)
```
Add `twin_core/residual.py`. Given a stream of {"predicted": {...}, "actual":
{...}} dicts from DigitalTwin, compute:

- Per-channel residual: (actual[ch] - predicted[ch]) normalized by that
  channel's nominal operating range (not raw units — RPM residual of 50 and
  oil-pressure residual of 5 need to be comparable).
- A rolling z-score or EWMA-normalized residual per channel to reduce
  false-positives from single-sample noise spikes.
- A composite anomaly score (e.g. weighted sum or max of |normalized
  residuals|) as a single 0-1+ severity number.
- Return per-tick output as: {timestamp, residuals: {channel: value, ...},
  composite_score}

This needs to work as a generator/streaming function (given one predicted/
actual pair at a time), not a batch-only function — M4's dashboard will
consume it live.

Check before I approve: feed it the twin from Step 3 (no fault) for 60s and
confirm composite_score stays near-zero the whole time with no drift.
```

### Step 5 — Fault-injection smoke test (coordinate with M2)
```
I don't own the fault injector (M2 does), but I need to validate my residual
engine against it. Write a temporary local fault stub in
`twin_core/_dev_fault_stub.py` (clearly marked as throwaway/dev-only, to be
deleted once M2's real injector is integrated): a wrapper around
EngineSimulator that, when a fault flag is set, corrupts ONE channel
(e.g. adds a step offset to EGT to simulate overheating) starting at a given
timestamp.

Wire this as the "actual" source into DigitalTwin from Step 3, run the
residual engine from Step 4 over a scenario where the fault turns on at
t=30s, and plot/print composite_score and the affected channel's residual
before/after t=30s.

Check before I approve: composite_score is flat near-zero before t=30s and
visibly jumps after — this is the core "it works" proof for USP #1 before
integration day.
```

### Step 6 — Per-fault sensitivity tuning (Day 4, with M3)
```
Once M2's real fault injector is integrated (misfire, injector fault,
overheating, oil-pressure drop, vibration spike — 5 types), extend
residual.py with per-channel weighting/thresholds so each fault type produces
a distinguishable residual SIGNATURE, not just "composite score went up."

Add a `signature()` function that returns which channel(s) deviated most and
by how much, formatted for M3 to consume as a classification feature vector
— confirm the exact field names/format M3 wants before finalizing this.

Check before I approve: run all 5 of M2's fault types through the pipeline
and show me that each produces a visibly different residual channel pattern
(e.g. overheating -> CHT/EGT dominant, oil-pressure drop -> oil_pressure
dominant), not five near-identical composite-score spikes.
```

### Step 7 — Replay mode
```
Add `twin_core/replay.py`: given a mission-log CSV in the schema M2 finalizes
on Day 4 (timestamp, rpm, cht, egt, oil_pressure, oil_temp, fuel_flow,
vibration_amplitude, vibration_freq, throttle_cmd, ...), replay it as the
"actual" source into the existing DigitalTwin + residual pipeline, generating
predicted values on the fly from the logged throttle_cmd column (NOT reading
a "predicted" column — the twin must regenerate the prediction from control
inputs, that's the whole point).

Check before I approve: feed it one of M2's saved fault-scenario CSVs and
confirm residual output matches what the live run originally produced for
that scenario (same fault window, same dominant channel).
```

### Step 8 — Integration pass (Day 6)
```
Run the full pipeline exactly as M4's dashboard and M3's classifier will call
it: fault injector (M2) -> DigitalTwin (mine) -> residual engine (mine) ->
[health index / classifier (M3), dashboard (M4)].

Fix any schema mismatches on MY side only — do not silently rename fields to
"make it work," flag any mismatch back to whoever owns that field.

Check before I approve: the full chain runs end-to-end with zero manual data
munging between my output and the next person's input.
```

### Step 9 — Architecture diagram content (with M5)
```
Summarize, in plain text I can hand to M5 for the README diagram: the exact
data flow through my block — control inputs -> reference model -> predicted
stream; control inputs -> actual source (live/faulted/replay) -> actual
stream; both streams -> residual engine -> {per-channel residuals, composite
score, signature}. List the 2-3 things about this loop that are easy to get
wrong when explaining it verbally, so the diagram compensates for those.
```

---

## 5. One thing to nail down before you start Step 1

Same decision the plan flags for the whole team: **analytical Python model vs. jumping straight to Simulink/Modelica.** Given you're solo-ish on this block under a 7-day clock, default to the analytical Python model — it's what unblocks M2/M3/M4 immediately, and the Simulink upgrade is already scoped for Weeks 2–3 if the project continues past the hackathon.
