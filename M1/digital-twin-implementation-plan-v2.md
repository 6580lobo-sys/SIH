# MALE UAV Aero Piston Engine Digital Twin — Team & Hackathon Implementation Plan (v2)

This revises the original plan for a **5-person team** and reframes it as a **fully deployable hackathon project** — meaning by demo time there is a live, hosted, clickable system (not a local script), and the USPs are built in from Day 1 rather than bolted on in month 2.

---

## 0. Team Structure (5 members)

Each block/USP needs an owner so nothing stalls waiting on a shared dependency. Two people pair on the hardest piece (the twin core), the rest run their tracks independently and integrate daily.

| # | Role | Owns | Primary USPs |
|---|---|---|---|
| **M1** | **Physics & Digital Twin Core Lead** | Block A (twin architecture), the analytical physics/thermo model, the predicted-vs-actual residual engine | USP #1 (residual twin) |
| **M2** | **Data & Fault Engineer** | Block B (sensor stream), Block C (fault injection), CAN-bus-style framing, replay/mission-log format | USP #7 (secure telemetry — doc only in hackathon phase) |
| **M3** | **AI/ML Engineer** | Block D — anomaly detection, RUL estimation, per-fault classification | USP #3 (explainability), USP #4 (uncertainty-quantified RUL) |
| **M4** | **Dashboard/HMI + Mission Lead** | Block E (replay/scenario sim), Block F (dashboard), maintenance advisory logic | USP #2 (mission-reliability scoring) |
| **M5** | **Integration / DevOps / Deployment Lead** | Repo structure, CI, containerization, cloud hosting, pitch deck, demo rehearsal, edge-AI feasibility writeup | USP #5 (edge AI feasibility doc), overall "is it actually deployed" ownership |

M1 and M2 pair closely on Days 1–2 since the fault injector needs to corrupt exactly the signal shape M1's simulator emits. M5 starts deployment plumbing (repo, Docker, hosting account) on Day 1 in parallel, not at the end — this is the main change from the original plan, which treated integration as a Day 6 activity. Waiting until Day 6 to find out the hosting platform can't run your stack is the single most common way hackathon teams end up demoing `localhost`.

---

## 1. Revised Hackathon Sprint (Days 1–7)

USP #1 and #2 are **non-negotiable core**, same call as the original doc — but now built in parallel starting Day 1–2 instead of introduced Day 5, since a 5-person team can afford to run them concurrently rather than sequentially. USP #3 and #4 are pulled forward into the sprint itself (not deferred to weeks 6–7) because they're cheap once a model exists and they're strong differentiators in a live demo.

| Day | M1 (Twin Core) | M2 (Data/Fault) | M3 (AI/ML) | M4 (Dashboard/Mission) | M5 (Integration/Deploy) |
|---|---|---|---|---|---|
| **1** | Analytical physics model: RPM, CHT, EGT, oil P/T, fuel flow, vibration as live time series | Streaming harness around M1's model (fixed-rate publisher); mock CAN-frame schema | Define feature schema + health-index spec with M1/M2 | Skeleton Streamlit app wired to the raw stream (no styling yet) | Repo scaffold, `requirements.txt`/Docker base image, GitHub Actions skeleton, pick hosting target (Streamlit Community Cloud / HF Spaces / Render) |
| **2** | Wire M1's model to run **in parallel** with the live stream (twin comparison scaffold, not just single-stream sim) | Fault injection module: misfire, injector fault, overheating, oil-pressure drop, vibration spike — toggleable | Baseline Isolation Forest / autoencoder on healthy data | Live parameter plots + fault-toggle controls in dashboard | Containerize the streaming + dashboard services; first deploy-to-staging dry run |
| **3** | **Residual engine (USP #1):** predicted-vs-actual divergence as the primary anomaly signal, not raw thresholds | Feed faulted stream into both raw-threshold and residual paths for comparison | Health index (0–100) + naive RUL curve from residual magnitude | Health-index gauge + fault alert panel | CI runs tests + linting on every push; staging URL live and shared with team |
| **4** | Tune residual sensitivity per fault type with M3 | Mission-log CSV format finalized; historical replay mode | Per-fault classification head (not just generic anomaly flag) | **Mission-reliability scoring (USP #2):** combine current health index + a chosen mission profile into a success-probability estimate | Persist run logs (lightweight DB or flat files) so replay/mission-reliability have real history to draw on |
| **5** | Replay mode: twin runs against a logged CSV, not just live data | Environmental scenario stubs (altitude, hot-weather, rapid-throttle) feeding the fault model | **Uncertainty-quantified RUL (USP #4):** ensemble or bootstrap interval, not a point estimate | **Explainability overlay (USP #3):** surface which sensor(s)/subsystem drove each alert, shown next to the alert panel | Deploy candidate build to production hosting target; smoke-test the public URL |
| **6** | Integration pass with M2/M3 on residual + replay + fault paths | Integration pass; finalize schema docs | Integration pass; validate explainability output against known injected faults | Full HMI pass — operator view + maintenance-advisory view + mission report; architecture diagram | Production deploy, custom domain/link if available, load-test the live demo path end-to-end |
| **7** | Buffer / bugfix | Buffer / bugfix | Buffer / bugfix | Rehearse live demo script on the deployed URL (not local) | Final deploy freeze, 5-slide architecture + USP deck, backup local demo in case of live network issues at venue |

**Still explicitly out of scope for the sprint:** real CAN bus/SocketCAN hardware integration, Simulink/Modelica-grade thermodynamics, live edge-hardware deployment, federated learning. These stay as documented roadmap/stretch items — see below.

---

## 2. USP Integration Summary

| # | USP | Sprint status | Owner |
|---|---|---|---|
| 1 | Physics-informed residual twin | **Built Day 2–3, core architecture** | M1 |
| 2 | Mission-reliability scoring | **Built Day 4, core architecture** | M4 |
| 3 | Explainable fault diagnosis (SHAP/attention overlay) | **Built Day 5, shipped in demo** | M3 |
| 4 | Uncertainty-quantified RUL | **Built Day 5, shipped in demo** | M3 |
| 5 | Edge AI / onboard inference | Documented feasibility study only (quantization plan, target hardware, expected latency) — no live hardware demo | M5 |
| 6 | Digital-twin self-recalibration | Stretch goal, only if Days 1–5 finish early | M1 |
| 7 | Secure telemetry architecture | Architecture diagram + threat-model slide, not implemented in sprint | M2 |
| 8 | Federated learning across simulated fleet | Deprioritized, mentioned only as future work in the deck | — |

Pulling #3 and #4 into the sprint (vs. the original weeks 6–7 placement) is the main lever for hackathon judging: it turns "we have a roadmap for explainability" into "here's the explainability overlay live on screen," which is what actually differentiates in a room full of anomaly-detection dashboards.

---

## 3. "Fully Deployable" Requirements

For a hackathon, "deployable" needs to mean judges can open a link on their own laptop mid-Q&A, not just watch your screen share. Concretely:

- **Containerized services** (M5): streaming/simulation service + dashboard as separate containers via `docker-compose`, so the same setup that runs locally runs on the host.
- **Public hosting** (M5): Streamlit Community Cloud, Hugging Face Spaces, or Render/Railway — pick whichever the team has an account on by Day 1, don't decide this on Day 6.
- **Persistent demo data** (M2/M5): a few pre-recorded fault scenarios saved as replay CSVs, so the live demo doesn't depend on the injector working perfectly in front of judges — replay is the safety net.
- **One-command reset** (M5): a button or script that resets the simulated engine to a healthy baseline, so back-to-back judge walkthroughs don't inherit a previous demo's injected faults.
- **README with architecture diagram** (M1 + M5): block diagram showing the twin/residual comparison loop, since this is the thing that needs the least verbal explanation if it's drawn well.
- **Backup local demo** (M5): venue wifi is the most common hackathon failure point — have the containerized stack runnable fully offline as a fallback.

---

## 4. 2.5-Month Roadmap (Weeks 2–10) — with owners

If this sprint becomes the seed for the longer build (per the original doc's Part 2), ownership carries forward roughly along the same lines, with M5 shifting from "deploy the hackathon build" to "own the ingestion pipeline and deployment roadmap":

| Weeks | Focus | Primary owner(s) |
|---|---|---|
| 2–3 | Proper thermodynamic cycle model, RPM–load–efficiency performance maps | M1, with M2 on data contracts |
| 4–5 | SocketCAN simulation, ECU/FADEC stubs, Kafka/MQTT → time-series DB ingestion | M2 + M5 |
| 6–7 | Per-fault classifiers, physics-informed loss constraints, mature #3/#4 further (confidence calibration, richer overlays) | M3 |
| 8 | Full mission-profile simulation (altitude, endurance, hot-weather, throttle transients) | M4 |
| 9 | Full HMI, maintenance advisory, mission-wise reports; revisit #6 (self-recalibration) and #7 (secure telemetry) as stretch | M4, M1 (recalibration), M2 (telemetry) |
| 10 | End-to-end testing, deployment roadmap doc, final packaging | M5 (with all hands for integration) |

---

## 5. One thing to decide before Day 1

Same open question as the original doc, now framed as a team decision: **does M1 build the Week-1 simulator as an analytical Python model, or start directly on a Simulink/Modelica model** if someone on the team has Simscape experience? Given the 5-person split above, defaulting to the analytical Python model is lower-risk for the sprint — it unblocks M2/M3/M4 immediately — with the Simulink upgrade path deferred to Weeks 2–3 as already scoped.
