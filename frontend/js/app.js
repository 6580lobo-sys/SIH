/**
 * AEROSPACE DIGITAL TWIN & GCS APPLICATION CONTROLLER (DRDO SIH26054)
 * Coordinates dual-engine switching, physics residuals, fault injection,
 * machine learning explainability, and report generation.
 */

class AppCoordinator {
  constructor() {
    this.currentView = 'view-overview';
    this.telemetryEngine = null;
    this.engineVisualizer = null;
    this.missionReplay = null;
    this.simulationWorkspace = null;
    this.diagnosticsModule = null;
    this.reportGenerator = null;

    this.init();
  }

  init() {
    // 1. Start UTC Clock
    this.startClock();

    // 2. Initialize Telemetry Engine (supports DRDO propulsion physics)
    this.telemetryEngine = new TelemetryEngine();

    // 3. Initialize Engine SVG Visualizer
    this.engineVisualizer = new EngineVisualizer('engine-canvas-mount');

    // 4. Initialize Diagnostics & ML Module
    this.diagnosticsModule = new DiagnosticsModule();
    window.diagnosticsModule = this.diagnosticsModule;

    // 5. Initialize Subsystems, Replay, and Report Generator
    this.missionReplay = new MissionReplayModule('replay-traces-canvas');
    this.simulationWorkspace = new SimulationWorkspace('simulation-chart-canvas');
    this.reportGenerator = new ReportGenerator();
    window.reportGenerator = this.reportGenerator;

    // 6. Bind Navigation Rail & Top Controls
    this.bindNavigation();
    this.bindEngineSwitcher();
    this.bindFaultInjector();
    this.bindAirframeModal();
    this.bindScenarioManager();
    this.bindProbeSandbox();

    // 7. Bind Subsystem Health Items
    this.bindSubsystems();

    // 8. Subscribe to Live Telemetry Feed
    this.telemetryEngine.subscribe((eng, history, faultKey, system) => {
      this.onTelemetryTick(eng, history, faultKey, system);
    });
    this.telemetryEngine.start();

    // 9. Initial Charts Draw
    setTimeout(() => {
      this.drawAllCharts();
      this.runProbeEvaluation();
    }, 100);

    window.addEventListener('resize', () => {
      this.drawAllCharts();
    });
  }

  startClock() {
    const updateUtc = () => {
      const now = new Date();
      const pad = (n) => String(n).padStart(2, '0');
      const timeStr = `${pad(now.getUTCHours())}:${pad(now.getUTCMinutes())}:${pad(now.getUTCSeconds())} UTC`;
      const el = document.getElementById('utc-clock-readout');
      if (el) el.textContent = timeStr;
    };
    updateUtc();
    setInterval(updateUtc, 1000);
  }

  bindNavigation() {
    const navButtons = document.querySelectorAll('.nav-button');
    navButtons.forEach(btn => {
      btn.addEventListener('click', () => {
        const targetView = btn.getAttribute('data-view');
        if (targetView) {
          this.switchView(targetView, btn);
        }
      });
    });
  }

  bindEngineSwitcher() {
    const portBtn = document.getElementById('btn-engine-port');
    const stbdBtn = document.getElementById('btn-engine-stbd');

    if (portBtn && stbdBtn) {
      portBtn.addEventListener('click', () => {
        portBtn.classList.add('active');
        stbdBtn.classList.remove('active');
        this.telemetryEngine.setEngine('ENG-1');
        this.updateEngineHeader('PORT ENGINE (AE-01)', 'ROTAX-915IS-98214');
      });

      stbdBtn.addEventListener('click', () => {
        stbdBtn.classList.add('active');
        portBtn.classList.remove('active');
        this.telemetryEngine.setEngine('ENG-2');
        this.updateEngineHeader('STARBOARD ENGINE (AE-02)', 'ROTAX-915IS-98215');
      });
    }
  }

  updateEngineHeader(name, serial) {
    const nameEl = document.getElementById('top-engine-name');
    if (nameEl) nameEl.textContent = name;
  }

  bindFaultInjector() {
    const selector = document.getElementById('m3-fault-selector');
    if (selector) {
      selector.addEventListener('change', (e) => {
        const faultKey = e.target.value;
        this.telemetryEngine.injectFault(faultKey);
        if (this.engineVisualizer) {
          this.engineVisualizer.applyFaultHighlight(faultKey);
        }
        if (this.diagnosticsModule) {
          this.diagnosticsModule.updateExplainability(faultKey);
        }
      });
    }
  }

  bindAirframeModal() {
    const btn = document.getElementById('btn-view-airframe-specs');
    const modal = document.getElementById('tapas-airframe-modal');
    const closeBtn = document.getElementById('btn-close-airframe-modal');

    if (btn && modal) {
      btn.addEventListener('click', () => modal.classList.add('open'));
    }
    if (closeBtn && modal) {
      closeBtn.addEventListener('click', () => modal.classList.remove('open'));
    }
    if (modal) {
      modal.addEventListener('click', (e) => {
        if (e.target === modal) modal.classList.remove('open');
      });
    }
  }

  switchView(viewId, activeBtn) {
    this.currentView = viewId;

    document.querySelectorAll('.nav-button').forEach(b => b.classList.remove('active'));
    if (activeBtn) activeBtn.classList.add('active');

    document.querySelectorAll('.view-panel').forEach(panel => {
      panel.classList.remove('active');
    });

    const targetPanel = document.getElementById(viewId);
    if (targetPanel) {
      targetPanel.classList.add('active');
    }

    setTimeout(() => {
      this.drawAllCharts();
      if (viewId === 'view-replay' && this.missionReplay) {
        this.missionReplay.updateDisplay();
      }
      if (viewId === 'view-simulation' && this.simulationWorkspace) {
        this.simulationWorkspace.runSimulation();
      }
    }, 50);
  }

  bindSubsystems() {
    const items = document.querySelectorAll('.subsystem-item');
    items.forEach(item => {
      item.addEventListener('click', () => {
        items.forEach(i => i.classList.remove('selected'));
        item.classList.add('selected');

        const partId = item.getAttribute('data-part-id');
        if (partId) {
          const svgPart = document.getElementById(partId);
          if (svgPart) {
            svgPart.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
          }
        }
      });
    });
  }

  onEnginePartSelected(partId) {
    const items = document.querySelectorAll('.subsystem-item');
    items.forEach(item => {
      if (item.getAttribute('data-part-id') === partId) {
        item.classList.add('selected');
      } else {
        item.classList.remove('selected');
      }
    });
  }

  onTelemetryTick(eng, history, faultKey, system) {
    const updateVal = (id, text) => {
      const el = document.getElementById(id);
      if (el) el.textContent = text;
    };

    // Primary Overview readouts
    updateVal('telem-val-rpm', eng.rpm.toLocaleString());
    updateVal('telem-val-cht', eng.cht);
    updateVal('telem-val-egt', eng.egt);
    updateVal('telem-val-oilp', eng.oilPress);
    updateVal('telem-val-oilt', eng.oilTemp);
    updateVal('telem-val-fuel', eng.fuelFlow);
    updateVal('telem-val-vib', eng.vibration);
    updateVal('telem-val-elec', `${eng.batteryVolt} / ${eng.alternatorAmp}`);
    updateVal('telem-val-time', eng.timing);

    // Health score & dynamic statements
    updateVal('overview-health-score', eng.healthIndex);
    updateVal('overview-tri-health', `${eng.healthIndex} / 100`);

    const healthEl = document.getElementById('overview-health-score');
    const badgeEl = document.getElementById('overview-health-badge');
    const primaryEl = document.getElementById('overview-health-primary');
    const secondaryEl = document.getElementById('overview-health-secondary');
    const triHealthEl = document.getElementById('overview-tri-health');

    const score = Number(eng.healthIndex);
    let scoreColor = 'var(--green-primary)';
    if (score >= 85) {
      scoreColor = 'var(--green-primary)';
      if (badgeEl) {
        badgeEl.textContent = 'ENGINE STATUS: NOMINAL';
        badgeEl.style.color = 'var(--green-primary)';
        badgeEl.style.borderColor = 'var(--green-primary)';
      }
      if (primaryEl) primaryEl.textContent = 'No critical abnormalities detected.';
      if (secondaryEl) secondaryEl.textContent = 'All primary propulsion parameters remain inside expected operating envelope. Otto-cycle digital twin synchronized.';
    } else if (score >= 60) {
      scoreColor = 'var(--amber-text)';
      if (badgeEl) {
        badgeEl.textContent = 'ENGINE STATUS: CAUTION / DEGRADATION';
        badgeEl.style.color = 'var(--amber-text)';
        badgeEl.style.borderColor = 'var(--amber-text)';
      }
      if (primaryEl) primaryEl.textContent = `Anomaly signature detected: ${faultKey.replace(/_/g, ' ').toUpperCase()}`;
      if (secondaryEl) secondaryEl.textContent = 'Subsystem physics model indicates abnormal drift. Predictive RUL window decreasing. Maintenance inspection advised.';
    } else {
      scoreColor = 'var(--red-primary)';
      if (badgeEl) {
        badgeEl.textContent = 'ENGINE STATUS: CRITICAL FAULT / RTB';
        badgeEl.style.color = 'var(--red-primary)';
        badgeEl.style.borderColor = 'var(--red-primary)';
      }
      if (primaryEl) primaryEl.textContent = `CRITICAL FAILURE ACTIVE: ${faultKey.replace(/_/g, ' ').toUpperCase()}`;
      if (secondaryEl) secondaryEl.textContent = 'Residual breach exceeds safe flight margins. Isolation Forest & Random Forest classify urgent risk. Immediate RTB recommended.';
    }

    if (healthEl) healthEl.style.color = scoreColor;
    if (triHealthEl) triHealthEl.style.color = scoreColor;

    // Physics Residuals readouts
    updateVal('res-val-rpm', (eng.residuals.res_rpm >= 0 ? '+' : '') + eng.residuals.res_rpm + ' RPM');
    updateVal('res-val-cht', (eng.residuals.res_cht >= 0 ? '+' : '') + eng.residuals.res_cht + ' °C');
    updateVal('res-val-egt', (eng.residuals.res_egt >= 0 ? '+' : '') + eng.residuals.res_egt + ' °C');
    updateVal('res-val-oilp', (eng.residuals.res_oil_p >= 0 ? '+' : '') + eng.residuals.res_oil_p + ' bar');
    updateVal('res-val-oilt', (eng.residuals.res_oil_t >= 0 ? '+' : '') + eng.residuals.res_oil_t + ' °C');
    updateVal('res-val-fuel', (eng.residuals.res_fuel >= 0 ? '+' : '') + eng.residuals.res_fuel + ' L/h');
    updateVal('res-val-vib', (eng.residuals.res_vib >= 0 ? '+' : '') + eng.residuals.res_vib + ' g');

    // Bottom status strip
    updateVal('stat-can-pkts', `${system.canPackets.toLocaleString()} / MIN`);
    updateVal('stat-latency', `${system.latency} ms`);

    // Top Command Bar Backend Connection Badge
    const beText = document.getElementById('backend-status-text');
    const beDot = document.getElementById('backend-status-dot');
    const beBadge = document.getElementById('backend-status-badge');
    if (beText && beDot && beBadge) {
      if (system.backendConnected) {
        beText.textContent = 'LIVE STREAM (PORT 8000)';
        beDot.style.background = 'var(--green-primary)';
        beBadge.style.color = 'var(--green-primary)';
      } else {
        beText.textContent = 'CLIENT PHYSICS (OFFLINE)';
        beDot.style.background = 'var(--amber-text)';
        beBadge.style.color = 'var(--amber-text)';
      }
    }

    // Redraw sparklines
    if (window.AeroCharts) {
      window.AeroCharts.drawSparkline('sparkline-rpm', history.rpm, { min: 2400, max: 2480 });
      window.AeroCharts.drawSparkline('sparkline-cht', history.cht, { min: 160, max: 175 });
      window.AeroCharts.drawSparkline('sparkline-egt', history.egt, { min: 600, max: 690, isWatch: eng.egt > 625 });
      window.AeroCharts.drawSparkline('sparkline-oilp', history.oilPress, { min: 2.0, max: 5.2, isWatch: eng.oilPress < 3.5 });
      window.AeroCharts.drawSparkline('sparkline-oilt', history.oilTemp, { min: 88, max: 112 });
      window.AeroCharts.drawSparkline('sparkline-fuel', history.fuelFlow, { min: 20, max: 26 });
      window.AeroCharts.drawSparkline('sparkline-vib', history.vibration, { min: 0.7, max: 1.6, isWatch: eng.vibration > 1.0 });
      window.AeroCharts.drawSparkline('sparkline-elec', history.batteryVolt, { min: 27, max: 29 });
      window.AeroCharts.drawSparkline('sparkline-time', history.timing, { min: 23, max: 26 });

      // Physics Residual sparklines
      window.AeroCharts.drawSparkline('sparkline-res-egt', history.res_egt, { min: -10, max: 80, isWatch: true });
      window.AeroCharts.drawSparkline('sparkline-res-cht', history.res_cht, { min: -5, max: 30 });
      window.AeroCharts.drawSparkline('sparkline-res-oilp', history.res_oil_p, { min: -3, max: 1, isWatch: eng.residuals.res_oil_p < -1 });
      window.AeroCharts.drawSparkline('sparkline-res-vib', history.res_vib, { min: -0.05, max: 0.7, isWatch: eng.residuals.res_vib > 0.3 });
    }
  }

  drawAllCharts() {
    if (!window.AeroCharts) return;

    window.AeroCharts.drawDegradationTrend('degradation-trend-canvas');
    window.AeroCharts.drawDegradationTrend('predictions-degradation-canvas');

    if (this.telemetryEngine) {
      const history = this.telemetryEngine.getHistory();
      window.AeroCharts.drawSparkline('sparkline-rpm', history.rpm, { min: 2400, max: 2480 });
      window.AeroCharts.drawSparkline('sparkline-cht', history.cht, { min: 160, max: 175 });
      window.AeroCharts.drawSparkline('sparkline-egt', history.egt, { min: 600, max: 690, isWatch: true });
      window.AeroCharts.drawSparkline('sparkline-oilp', history.oilPress, { min: 2.0, max: 5.2 });
      window.AeroCharts.drawSparkline('sparkline-oilt', history.oilTemp, { min: 88, max: 112 });
      window.AeroCharts.drawSparkline('sparkline-fuel', history.fuelFlow, { min: 20, max: 26 });
      window.AeroCharts.drawSparkline('sparkline-vib', history.vibration, { min: 0.7, max: 1.6, isWatch: true });
      window.AeroCharts.drawSparkline('sparkline-elec', history.batteryVolt, { min: 27, max: 29 });
      window.AeroCharts.drawSparkline('sparkline-time', history.timing, { min: 23, max: 26 });
    }
  }

  bindScenarioManager() {
    const chips = document.querySelectorAll('.scenario-chip');
    const faultSelector = document.getElementById('m3-fault-selector');

    const selectScenario = (scenarioKey) => {
      document.querySelectorAll('.scenario-chip').forEach(c => {
        if (c.getAttribute('data-scenario') === scenarioKey) {
          c.classList.add('active');
        } else {
          c.classList.remove('active');
        }
      });

      if (faultSelector) {
        faultSelector.value = scenarioKey;
      }

      this.telemetryEngine.injectFault(scenarioKey);

      if (this.engineVisualizer) {
        this.engineVisualizer.applyFaultHighlight(scenarioKey);
      }
      if (this.diagnosticsModule) {
        this.diagnosticsModule.updateExplainability(scenarioKey);
      }
    };

    chips.forEach(chip => {
      chip.addEventListener('click', () => {
        const key = chip.getAttribute('data-scenario');
        if (key) selectScenario(key);
      });
    });

    if (faultSelector) {
      faultSelector.addEventListener('change', (e) => {
        selectScenario(e.target.value);
      });
    }

    // Modal bindings for Save Custom Config
    const openBtn = document.getElementById('btn-open-save-config');
    const modal = document.getElementById('save-scenario-modal');
    const closeBtn = document.getElementById('btn-close-save-modal');
    const cancelBtn = document.getElementById('btn-cancel-save-scenario');
    const confirmBtn = document.getElementById('btn-confirm-save-scenario');

    if (openBtn && modal) openBtn.addEventListener('click', () => modal.classList.add('open'));
    if (closeBtn && modal) closeBtn.addEventListener('click', () => modal.classList.remove('open'));
    if (cancelBtn && modal) cancelBtn.addEventListener('click', () => modal.classList.remove('open'));

    if (confirmBtn && modal) {
      confirmBtn.addEventListener('click', () => {
        const nameInput = document.getElementById('input-scenario-name');
        const faultInput = document.getElementById('input-scenario-fault');
        const descInput = document.getElementById('input-scenario-desc');

        const name = nameInput && nameInput.value.trim() ? nameInput.value.trim() : 'Custom Scenario';
        const fault = faultInput ? faultInput.value : 'healthy';

        const container = document.getElementById('scenario-chips-container');
        if (container) {
          const newChip = document.createElement('button');
          newChip.className = 'scenario-chip fault-active';
          newChip.setAttribute('data-scenario', fault);
          newChip.textContent = `★ ${name.toUpperCase()}`;
          newChip.addEventListener('click', () => selectScenario(fault));
          container.appendChild(newChip);
        }

        modal.classList.remove('open');
        selectScenario(fault);
        if (nameInput) nameInput.value = '';
        if (descInput) descInput.value = '';
      });
    }
  }

  bindProbeSandbox() {
    const sliders = [
      { id: 'slider-probe-rpm', disp: 'disp-probe-rpm', unit: ' RPM' },
      { id: 'slider-probe-throttle', disp: 'disp-probe-throttle', unit: ' %' },
      { id: 'slider-probe-oil-temp', disp: 'disp-probe-oil-temp', unit: ' °C' },
      { id: 'slider-probe-oil-press', disp: 'disp-probe-oil-press', unit: ' bar' },
      { id: 'slider-probe-cht', disp: 'disp-probe-cht', unit: ' °C' },
      { id: 'slider-probe-egt', disp: 'disp-probe-egt', unit: ' °C' },
      { id: 'slider-probe-fuel', disp: 'disp-probe-fuel', unit: ' L/h' },
      { id: 'slider-probe-vib', disp: 'disp-probe-vib', unit: ' g' },
      { id: 'slider-probe-duration', disp: 'disp-probe-duration', unit: ' h' },
    ];

    sliders.forEach(s => {
      const el = document.getElementById(s.id);
      const disp = document.getElementById(s.disp);
      if (el && disp) {
        el.addEventListener('input', () => {
          disp.textContent = `${el.value}${s.unit}`;
        });
      }
    });

    const setSliders = (vals) => {
      if (vals.rpm !== undefined) {
        const el = document.getElementById('slider-probe-rpm');
        if (el) { el.value = vals.rpm; document.getElementById('disp-probe-rpm').textContent = `${vals.rpm} RPM`; }
      }
      if (vals.throttle !== undefined) {
        const el = document.getElementById('slider-probe-throttle');
        if (el) { el.value = vals.throttle; document.getElementById('disp-probe-throttle').textContent = `${vals.throttle} %`; }
      }
      if (vals.oilTemp !== undefined) {
        const el = document.getElementById('slider-probe-oil-temp');
        if (el) { el.value = vals.oilTemp; document.getElementById('disp-probe-oil-temp').textContent = `${vals.oilTemp} °C`; }
      }
      if (vals.oilPress !== undefined) {
        const el = document.getElementById('slider-probe-oil-press');
        if (el) { el.value = vals.oilPress; document.getElementById('disp-probe-oil-press').textContent = `${vals.oilPress} bar`; }
      }
      if (vals.cht !== undefined) {
        const el = document.getElementById('slider-probe-cht');
        if (el) { el.value = vals.cht; document.getElementById('disp-probe-cht').textContent = `${vals.cht} °C`; }
      }
      if (vals.egt !== undefined) {
        const el = document.getElementById('slider-probe-egt');
        if (el) { el.value = vals.egt; document.getElementById('disp-probe-egt').textContent = `${vals.egt} °C`; }
      }
      if (vals.fuel !== undefined) {
        const el = document.getElementById('slider-probe-fuel');
        if (el) { el.value = vals.fuel; document.getElementById('disp-probe-fuel').textContent = `${vals.fuel} L/h`; }
      }
      if (vals.vib !== undefined) {
        const el = document.getElementById('slider-probe-vib');
        if (el) { el.value = vals.vib; document.getElementById('disp-probe-vib').textContent = `${vals.vib} g`; }
      }
      this.runProbeEvaluation();
    };

    const btnNom = document.getElementById('btn-probe-quick-nominal');
    if (btnNom) btnNom.addEventListener('click', () => setSliders({ rpm: 2438, throttle: 65, oilTemp: 94.2, oilPress: 4.82, cht: 167.4, egt: 612.8, fuel: 21.7, vib: 0.84 }));

    const btnOil = document.getElementById('btn-probe-quick-oil');
    if (btnOil) btnOil.addEventListener('click', () => setSliders({ oilPress: 1.35, oilTemp: 116.0 }));

    const btnCht = document.getElementById('btn-probe-quick-cht');
    if (btnCht) btnCht.addEventListener('click', () => setSliders({ cht: 236.0, egt: 760.0 }));

    const btnEgt = document.getElementById('btn-probe-quick-egt');
    if (btnEgt) btnEgt.addEventListener('click', () => setSliders({ egt: 865.0, fuel: 28.5 }));

    const btnVib = document.getElementById('btn-probe-quick-vib');
    if (btnVib) btnVib.addEventListener('click', () => setSliders({ vib: 3.85 }));

    const evalBtn = document.getElementById('btn-evaluate-live-probe');
    if (evalBtn) {
      evalBtn.addEventListener('click', () => this.runProbeEvaluation());
    }
  }

  async runProbeEvaluation() {
    const getVal = (id, def) => {
      const el = document.getElementById(id);
      return el ? Number(el.value) : def;
    };

    const probe = {
      rpm: getVal('slider-probe-rpm', 2438),
      throttle: getVal('slider-probe-throttle', 65),
      oilTemp: getVal('slider-probe-oil-temp', 94.2),
      oilPress: getVal('slider-probe-oil-press', 4.82),
      cht: getVal('slider-probe-cht', 167.4),
      egt: getVal('slider-probe-egt', 612.8),
      fuelFlow: getVal('slider-probe-fuel', 21.7),
      vibration: getVal('slider-probe-vib', 0.84),
      missionDurationHours: getVal('slider-probe-duration', 8.0),
    };

    const res = await this.telemetryEngine.evaluateLiveProbe(probe);

    const verdictEl = document.getElementById('probe-out-verdict');
    if (verdictEl) {
      verdictEl.textContent = res.ml.isAnomaly ? 'ANOMALOUS (FAULT DETECTED)' : 'NOMINAL (HEALTHY)';
      verdictEl.className = `outcome-badge ${res.ml.isAnomaly ? (res.severity === 'CRITICAL_RTB' ? 'critical' : 'warning') : 'normal'}`;
    }

    const scoreEl = document.getElementById('probe-out-anomaly-score');
    if (scoreEl) scoreEl.textContent = res.ml.anomalyScore.toFixed(4);

    const classEl = document.getElementById('probe-out-class');
    if (classEl) {
      classEl.textContent = res.ml.predictedClass.replace(/_/g, ' ').toUpperCase();
      classEl.style.color = res.ml.isAnomaly ? 'var(--amber-primary)' : 'var(--green-primary)';
    }

    const confEl = document.getElementById('probe-out-conf');
    if (confEl) confEl.textContent = `${(res.ml.confidence * 100).toFixed(1)}%`;

    const featEl = document.getElementById('probe-out-top-features');
    if (featEl) featEl.textContent = res.ml.topFeatures.join(', ');

    const resEl = document.getElementById('probe-out-residuals');
    if (resEl) {
      resEl.textContent = `ΔCHT: ${res.residuals.resCht > 0 ? '+' : ''}${res.residuals.resCht}°C | ΔOilP: ${res.residuals.resOilP > 0 ? '+' : ''}${res.residuals.resOilP} bar | ΔEGT: ${res.residuals.resEgt > 0 ? '+' : ''}${res.residuals.resEgt}°C`;
    }

    const hiEl = document.getElementById('probe-out-hi');
    if (hiEl) {
      hiEl.textContent = `${res.healthIndex.toFixed(1)} %`;
      hiEl.style.color = res.healthIndex > 80 ? 'var(--green-primary)' : (res.healthIndex > 50 ? 'var(--amber-primary)' : 'var(--red-primary)');
    }

    const sevEl = document.getElementById('probe-out-severity');
    if (sevEl) {
      sevEl.textContent = res.severity;
      sevEl.className = `outcome-badge ${res.severity === 'NORMAL' ? 'normal' : (res.severity === 'CRITICAL_RTB' ? 'critical' : 'warning')}`;
    }

    const rulEl = document.getElementById('probe-out-rul');
    if (rulEl) {
      rulEl.textContent = `${res.rul.est.toFixed(1)} min (${(res.rul.est / 60).toFixed(1)} h)`;
    }

    const ciEl = document.getElementById('probe-out-ci');
    if (ciEl) {
      ciEl.textContent = `[${res.rul.lower.toFixed(1)} min — ${res.rul.upper.toFixed(1)} min] (95% CI)`;
    }

    const timeEl = document.getElementById('probe-run-timestamp');
    if (timeEl) {
      const now = new Date();
      timeEl.textContent = `Evaluated at ${now.toLocaleTimeString()} UTC · Verification: Model reliably classified ${res.ml.predictedClass.replace(/_/g, ' ').toUpperCase()} (${(res.ml.confidence*100).toFixed(1)}%).`;
    }
  }
}

// Global initialization
document.addEventListener('DOMContentLoaded', () => {
  window.appCoordinator = new AppCoordinator();
});
