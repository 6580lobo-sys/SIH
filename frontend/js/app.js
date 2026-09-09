/**
 * AEROSPACE DIGITAL TWIN & GCS APPLICATION CONTROLLER (DRDO SIH26054)
 * Coordinates dual-engine switching, M1 physics residuals, M3 fault injection,
 * M4 machine learning explainability, and report generation.
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

    // 2. Initialize Telemetry Engine (supports DRDO M1-M3)
    this.telemetryEngine = new TelemetryEngine();

    // 3. Initialize Engine SVG Visualizer
    this.engineVisualizer = new EngineVisualizer('engine-canvas-mount');

    // 4. Initialize Diagnostics & M4 ML Module
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

    // Health score
    updateVal('overview-health-score', eng.healthIndex);

    // M1 Physics Residuals readouts
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

      // M1 Residual sparklines
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
}

// Global initialization
document.addEventListener('DOMContentLoaded', () => {
  window.appCoordinator = new AppCoordinator();
});
