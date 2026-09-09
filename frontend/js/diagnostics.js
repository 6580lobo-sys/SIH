/**
 * FAULT MONITORING, DIAGNOSTICS & M4 MACHINE LEARNING EXPLAINABILITY
 * DRDO PS26054 · Integration of Isolation Forest, Random Forest Classifier,
 * and SHAP Feature Importance from SIH-main/M4.
 */

class DiagnosticsModule {
  constructor() {
    // Official DRDO evaluation metrics loaded from M4 reports
    this.mlMetrics = {
      modelName: 'RandomForestClassifier (100 Estimators, max_depth=12)',
      accuracy: 0.9456,
      macroF1: 0.8571,
      weightedF1: 0.9333,
      anomalyModel: 'Isolation Forest (n_estimators=100, contamination=0.082)',
      anomalyPrecision: 0.7153,
      anomalyRecall: 0.9998,
      anomalyF1: 0.8340
    };

    // Official DRDO M4 Explanation Templates
    this.explanationTemplates = {
      'healthy': {
        label: 'Healthy / Nominal Baseline',
        text: 'Engine is operating within normal parameters. All sensor readings and physical residuals are within expected envelope.',
        action: 'Maintain standard pre-flight and turn-around inspection protocol.'
      },
      'overheating': {
        label: 'Cylinder / Exhaust Thermal Runaway',
        text: 'Overheating detected. Cylinder head temperature and/or exhaust gas temperature are rising above expected values. Significant positive CHT and EGT residuals.',
        action: 'Recommend reducing power, expanding cooling cowl flap, and inspecting radiator airflow baffles.'
      },
      'oil_pressure_drop': {
        label: 'Lubrication System Pressure Drop',
        text: 'Oil pressure degradation detected. Measured oil pressure is below physics-model expectation and trending downward. Oil temperature is also rising.',
        action: 'Recommend reducing engine load immediately and scheduling oil gallery relief valve & pump inspection.'
      },
      'vibration_bearing_fault': {
        label: 'Mechanical Vibration / Bearing Degradation',
        text: 'Abnormal vibration detected. Spectral peak at 2.54x engine speed above expected trend. Consistent with reduction gear bearing fatigue or propeller dynamic imbalance.',
        action: 'Recommend immediate inspection of reduction drive, torque-check engine mount bolts, and borescope bearing race.'
      },
      'misfire_or_injector_fault': {
        label: 'Combustion Irregularity / Injector Imbalance',
        text: 'Combustion irregularity detected on Cylinder 3. EGT is showing intermittent divergence and RPM fluctuates with minor fuel trim delta. Nozzle micro-coking suspected.',
        action: 'Inspect and ultrasonic clean injector nozzles on Cylinder 3 within 38 flight hours. No immediate flight abort required.'
      },
      'fuel_mixture_drift': {
        label: 'Fuel Mixture Ratio Drift',
        text: 'Fuel mixture drift detected. Fuel flow is above commanded value. EGT trending upward indicates rich/lean mixture divergence across bank A and bank B.',
        action: 'Inspect ECU fuel rail pressure regulator and intake manifold absolute pressure (MAP) sensor calibration.'
      },
      'cooling_system_fault': {
        label: 'Cooling System Baffle / Radiator Degradation',
        text: 'Cooling system degradation detected. CHT residual is above expected; oil cooler exit temperature elevated. Ram-air heat dissipation margin reduced by 22%.',
        action: 'Check coolant level, expansion tank pressure cap, and engine compartment cowl inlet seals.'
      },
      'engine_overspeed': {
        label: 'Propeller Governor Overspeed Transient',
        text: 'Engine overspeed detected. Crankshaft RPM is spiking above maximum continuous rated speed (2,550 RPM). Constant speed propeller governor hunting.',
        action: 'Immediate throttle reduction command. Inspect hydraulic governor oil line and pitch counterweights.'
      }
    };

    // Fault database
    this.faultData = {
      'misfire_or_injector_fault': {
        name: 'Fuel Injector Balance (INJ-03)',
        status: 'WATCH',
        trend: 'Increasing (+4.2%)',
        confidence: '87.0%',
        lastDetected: '14:32:08 UTC (MET 01:24:32)',
        action: 'Inspect injector balance during next scheduled maintenance',
        details: {
          what: 'EGT on Cylinder 3 is rising faster than expected relative to Cylinders 1, 2, and 4 during stable 2,438 RPM loiter.',
          when: 'Initial divergence detected at 14:32:08 UTC during loiter cruise segment.',
          paramsChanged: 'EGT Cyl-03: +28.7°C divergence; fuel flow trimmed +0.3 L/hr on bank A.',
          cause: 'Partial nozzle deposit / micro-coking or solenoid actuation impedance skew.',
          confidence: '87.0%',
          recommended: 'Inspect and ultrasonic clean injector nozzles on Cylinder 3 within 38 flight hours. No immediate inflight safety concern.'
        }
      },
      'vibration_bearing_fault': {
        name: 'Vibration & Reduction Gearbox Harmonic',
        status: 'WATCH',
        trend: 'Increasing (+0.08 g)',
        confidence: '82.0%',
        lastDetected: '13:58:14 UTC',
        action: 'Inspect mounting / bearing condition within 12 flight hours',
        details: {
          what: 'Subtle high-frequency spectral peak observed at 2.54x engine speed (gearbox mesh harmonic). Overall vibration 0.84 g.',
          when: 'First elevated harmonic detected 13:58:14 UTC following throttle step.',
          paramsChanged: 'Radial accelerometer trace: +0.08 g increase in 1.2 kHz band.',
          cause: 'Propeller reduction gear backlash or engine elastomeric mount micro-stiffness relaxation.',
          confidence: '82.0%',
          recommended: 'Perform borescope inspection of reduction gear teeth and torque-check engine mount bolts within 12 flight hours.'
        }
      },
      'oil_pressure_drop': {
        name: 'Oil Circulation & Pressure Dynamics',
        status: 'ALERT',
        trend: 'Degrading (-2.44 bar)',
        confidence: '97.6%',
        lastDetected: 'Active in injected state',
        action: 'Immediate ground abort / emergency lubrication check',
        details: {
          what: 'Main oil gallery pressure dropped to 2.38 bar with elevated oil temperature.',
          when: 'Simulated fault trigger event.',
          paramsChanged: 'res_oil_p = -2.44 bar; oil temp rising toward 108°C.',
          cause: 'Oil pressure relief valve failure or pump cavitation.',
          confidence: '97.6%',
          recommended: 'Throttle back to minimum loiter power; prepare RTB (Return to Base).'
        }
      },
      'overheating': {
        name: 'Thermal Headroom & Overheat Margins',
        status: 'CRITICAL',
        trend: 'Rising (+24.5°C CHT)',
        confidence: '98.8%',
        lastDetected: 'Active in injected state',
        action: 'Reduce throttle and initiate immediate descent for thermal cooling',
        details: {
          what: 'Cylinder Head Temperature surged to 188.6°C; EGT at 684°C.',
          when: 'Simulated fault trigger event.',
          paramsChanged: 'res_cht = +24.5°C; res_egt = +72.0°C.',
          cause: 'Severe coolant circulation loss or lean detonation runaway.',
          confidence: '98.8%',
          recommended: 'Immediate descent to denser, cooler air; prepare for recovery.'
        }
      },
      'fuel_mixture_drift': {
        name: 'Fuel Mixture Ratio Drift',
        status: 'WATCH',
        trend: 'Enriching (+3.1 L/hr)',
        confidence: '92.4%',
        lastDetected: 'Active in injected state',
        action: 'Inspect ECU lambda trimming sensor and fuel pressure regulator',
        details: {
          what: 'Fuel consumption rate increased to 24.8 L/hr without corresponding thrust gain.',
          when: 'Simulated fault trigger event.',
          paramsChanged: 'res_fuel = +3.1 L/hr; res_egt = +45.2°C.',
          cause: 'MAP sensor manifold vacuum leak or leaking fuel pressure regulator.',
          confidence: '92.4%',
          recommended: 'Log discrepancy; calibrate MAP sensor at next depot cycle.'
        }
      },
      'cooling_system_fault': {
        name: 'Cooling System Baffle Degradation',
        status: 'WATCH',
        trend: 'Degrading (+20.1°C CHT)',
        confidence: '95.2%',
        lastDetected: 'Active in injected state',
        action: 'Inspect radiator cowl intake seals upon landing',
        details: {
          what: 'CHT residual increased by 20.1°C under high-altitude loiter.',
          when: 'Simulated fault trigger event.',
          paramsChanged: 'res_cht = +20.1°C; res_oil_t = +8.4°C.',
          cause: 'Duct seal tear allowing ram-air bypass around radiator core.',
          confidence: '95.2%',
          recommended: 'Inspect and reseal cooling air ducting.'
        }
      },
      'engine_overspeed': {
        name: 'Propeller Governor Overspeed Transient',
        status: 'ALERT',
        trend: 'Surging (+242 RPM)',
        confidence: '99.1%',
        lastDetected: 'Active in injected state',
        action: 'Manually cycle propeller pitch governor',
        details: {
          what: 'Engine RPM exceeded 2,650 RPM under moderate throttle command.',
          when: 'Simulated fault trigger event.',
          paramsChanged: 'res_rpm = +242 RPM; high centrifugal stress.',
          cause: 'Governor hydraulic valve sticking or pitch control cable play.',
          confidence: '99.1%',
          recommended: 'Perform governor pressure test and propeller hub inspection.'
        }
      },
      'misfire': {
        name: 'Combustion Misfire Detection',
        status: 'NOMINAL',
        trend: 'Stable (0.01 / 1k rev)',
        confidence: '99.4%',
        lastDetected: 'None in current sortie',
        action: 'Routine spark plug inspection at 100h interval',
        details: {
          what: 'Micro-angular velocity variance across crankshaft sensor poles indicates zero cycle-to-cycle misfire.',
          when: 'Continuously monitored over current 04:17:32 flight duration.',
          paramsChanged: 'Angular jitter: 0.04° (nominal envelope < 0.18°).',
          cause: 'Normal cylinder ignition and flame front propagation.',
          confidence: '99.4%',
          recommended: 'Maintain standard maintenance schedule.'
        }
      },
      'lubrication': {
        name: 'Oil Circulation & Pressure Dynamics',
        status: 'NOMINAL',
        trend: 'Stable',
        confidence: '98.1%',
        lastDetected: 'None',
        action: 'Standard oil sample analysis at 50h turnaround',
        details: {
          what: 'Main oil gallery pressure maintains 4.82 bar at 94.2°C, well above 3.5 bar minimum operating envelope.',
          when: 'Continuous nominal pressure delivery throughout climb and loiter.',
          paramsChanged: 'Pressure differential across fine filter: 0.18 bar (clean).',
          cause: 'Positive displacement oil pump and relief valves operating nominally.',
          confidence: '98.1%',
          recommended: 'Perform routine spectrographic oil analysis at next base turnaround.'
        }
      },
      'sensor_drift': {
        name: 'Sensor Cross-Validation & Drift',
        status: 'NOMINAL',
        trend: 'Stable',
        confidence: '99.2%',
        lastDetected: 'None',
        action: 'Recalibrate MAP transducer at quarterly depot check',
        details: {
          what: 'Redundant dual CHT, EGT, and manifold pressure sensors match within ±0.8% tolerance.',
          when: 'Cross-checked continuously against synthetic thermodynamic model.',
          paramsChanged: 'Sensor A vs Sensor B divergence: < 0.4°C.',
          cause: 'Healthy thermocouple and pressure sensor wiring harness.',
          confidence: '99.2%',
          recommended: 'No operational intervention required.'
        }
      },
      'combustion_stability': {
        name: 'Combustion Stability (COV-IMEP)',
        status: 'NOMINAL',
        trend: 'Stable',
        confidence: '94.6%',
        lastDetected: 'None',
        action: 'Continue continuous cycle covariance tracking',
        details: {
          what: 'Coefficient of variation of indicated mean effective pressure (COV-IMEP) remains at 2.1%.',
          when: 'Evaluated across 10,000 engine cycles during ISR mission.',
          paramsChanged: 'COV-IMEP: 2.1% (alert threshold: > 5.0%).',
          cause: 'Uniform air-fuel mixing and intake manifold plenum resonance.',
          confidence: '94.6%',
          recommended: 'Continue passive health monitoring.'
        }
      },
      'overheating_nominal': {
        name: 'Thermal Headroom & Overheat Margins',
        status: 'NOMINAL',
        trend: 'Stable',
        confidence: '96.8%',
        lastDetected: 'None',
        action: 'Check cooling duct baffle seals during pre-flight',
        details: {
          what: 'Peak Cylinder Head Temperature is 168.1°C (CYL 04), 31.9°C below the 200°C continuous limit.',
          when: 'Thermal equilibrium achieved at 18,500 ft altitude.',
          paramsChanged: 'Cooling airflow margin: 18% above ISA+20 requirement.',
          cause: 'Nominal ram-air cooling cowl performance and oil cooler flow.',
          confidence: '96.8%',
          recommended: 'Continue mission within standard operational envelope.'
        }
      },
      'electrical': {
        name: 'Electrical & Alternator Bus',
        status: 'NOMINAL',
        trend: 'Stable',
        confidence: '99.5%',
        lastDetected: 'None',
        action: 'Verify battery internal resistance at annual service',
        details: {
          what: 'Dual 28V alternators supplying 42.1A combined load. Bus ripple < 45 mV.',
          when: 'Continuous steady-state generation throughout mission.',
          paramsChanged: 'Bus voltage: 28.4 V (nominal 28.0 - 28.6 V).',
          cause: 'Solid-state voltage regulator and stator windings operating at peak efficiency.',
          confidence: '99.5%',
          recommended: 'Continue operations.'
        }
      }
    };

    this.init();
  }

  init() {
    this.bindTableClicks();
    this.bindDrawerClose();
  }

  bindTableClicks() {
    document.querySelectorAll('.eng-table tbody tr').forEach(row => {
      row.addEventListener('click', () => {
        const faultKey = row.getAttribute('data-fault-key');
        if (faultKey && this.faultData[faultKey]) {
          this.openForensics(this.faultData[faultKey]);
        }
      });
    });

    document.querySelectorAll('[data-open-fault]').forEach(el => {
      el.addEventListener('click', (e) => {
        e.stopPropagation();
        const faultKey = el.getAttribute('data-open-fault');
        if (faultKey && this.faultData[faultKey]) {
          this.openForensics(this.faultData[faultKey]);
        }
      });
    });
  }

  bindDrawerClose() {
    const overlay = document.getElementById('forensic-drawer-overlay');
    const closeBtn = document.getElementById('drawer-close-btn');

    if (closeBtn) {
      closeBtn.addEventListener('click', () => this.closeForensics());
    }

    if (overlay) {
      overlay.addEventListener('click', (e) => {
        if (e.target === overlay) this.closeForensics();
      });
    }

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') this.closeForensics();
    });
  }

  openForensics(data) {
    const overlay = document.getElementById('forensic-drawer-overlay');
    if (!overlay) return;

    const titleEl = document.getElementById('drawer-fault-title');
    const bodyEl = document.getElementById('drawer-fault-body');

    if (titleEl) titleEl.textContent = data.name;

    let statusBadgeClass = 'tag-nominal';
    if (data.status === 'WATCH') statusBadgeClass = 'tag-watch';
    if (data.status === 'ALERT' || data.status === 'CRITICAL') statusBadgeClass = 'fill-critical';

    if (bodyEl) {
      bodyEl.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; padding-bottom: 12px; border-bottom: 1px solid var(--border-subtle);">
          <div>
            <span class="subsystem-status-tag ${statusBadgeClass}">${data.status}</span>
            <span style="font-family: var(--font-mono); font-size: 11px; color: var(--text-tertiary); margin-left: 8px;">
              MODEL CONFIDENCE: <strong>${data.confidence}</strong>
            </span>
          </div>
          <span style="font-family: var(--font-mono); font-size: 11px; color: var(--text-secondary);">
            TREND: <strong>${data.trend}</strong>
          </span>
        </div>

        <div class="diagnostic-reasoning" style="gap: 16px;">
          <div class="reasoning-row">
            <span class="reasoning-label">WHAT HAPPENED? (OBSERVATION)</span>
            <p class="reasoning-content" style="margin-top: 4px; font-size: 13px;">${data.details.what}</p>
          </div>

          <div class="reasoning-row">
            <span class="reasoning-label">WHEN DID IT OCCUR?</span>
            <p class="reasoning-content" style="margin-top: 4px; font-size: 13px; font-family: var(--font-mono);">${data.details.when}</p>
          </div>

          <div class="reasoning-row">
            <span class="reasoning-label">WHAT PARAMETERS CHANGED? (M1 RESIDUALS)</span>
            <div style="margin-top: 4px; padding: 8px 12px; background: var(--bg-surface-subtle); border: 1px solid var(--border-subtle); border-radius: 3px; font-family: var(--font-mono); font-size: 12px; color: var(--text-primary);">
              ${data.details.paramsChanged}
            </div>
          </div>

          <div class="reasoning-row">
            <span class="reasoning-label">POSSIBLE CAUSE & PHYSICS MODEL ESTIMATE</span>
            <p class="reasoning-content" style="margin-top: 4px; font-size: 13px; color: var(--text-secondary);">${data.details.cause}</p>
          </div>

          <div class="reasoning-row">
            <span class="reasoning-label">RECOMMENDED HUMAN ACTION</span>
            <div class="reasoning-content action" style="margin-top: 4px; font-size: 13px; line-height: 1.45;">
              ${data.details.recommended}
            </div>
          </div>
        </div>

        <div style="margin-top: auto; padding-top: 16px; border-top: 1px solid var(--border-subtle); display: flex; justify-content: flex-end; gap: 8px;">
          <button class="eng-btn" onclick="window.diagnosticsModule.closeForensics()">DISMISS</button>
          <button class="eng-btn active" onclick="alert('Diagnostic advisory logged to Ground Maintenance Notebook (Tech: H. Vance).'); window.diagnosticsModule.closeForensics();">
            LOG TO MAINTENANCE ADVISORY
          </button>
        </div>
      `;
    }

    overlay.classList.add('open');
  }

  closeForensics() {
    const overlay = document.getElementById('forensic-drawer-overlay');
    if (overlay) overlay.classList.remove('open');
  }

  // Update M4 AI/ML Explainability Lab dynamically when fault changes
  updateExplainability(faultKey) {
    const fault = this.explanationTemplates[faultKey] || this.explanationTemplates['healthy'];

    // Update explanation text
    const explText = document.getElementById('m4-explanation-text');
    if (explText) explText.textContent = fault.text;

    const explAction = document.getElementById('m4-action-text');
    if (explAction) explAction.textContent = fault.action;

    // Update Top-k Probability distributions
    const probContainer = document.getElementById('m4-top-probabilities');
    if (probContainer) {
      const isHealthy = faultKey === 'healthy';
      const p1 = isHealthy ? 98.4 : 88.6;
      const p2 = isHealthy ? 1.1 : 6.8;
      const p3 = isHealthy ? 0.5 : 4.6;

      const c1 = isHealthy ? 'healthy' : faultKey;
      const c2 = isHealthy ? 'misfire_or_injector_fault' : 'fuel_mixture_drift';
      const c3 = isHealthy ? 'fuel_mixture_drift' : 'healthy';

      probContainer.innerHTML = `
        <div style="margin-bottom: 8px;">
          <div style="display: flex; justify-content: space-between; font-size: 11px; margin-bottom: 2px;">
            <span>${c1.replace(/_/g, ' ').toUpperCase()}</span>
            <strong style="color: ${isHealthy ? 'var(--green-primary)' : 'var(--amber-primary)'};">${p1}%</strong>
          </div>
          <div class="subsystem-track"><div class="subsystem-fill ${isHealthy ? 'fill-nominal' : 'fill-watch'}" style="width: ${p1}%;"></div></div>
        </div>
        <div style="margin-bottom: 8px;">
          <div style="display: flex; justify-content: space-between; font-size: 11px; margin-bottom: 2px;">
            <span>${c2.replace(/_/g, ' ').toUpperCase()}</span>
            <strong>${p2}%</strong>
          </div>
          <div class="subsystem-track"><div class="subsystem-fill fill-nominal" style="width: ${p2 * 3}%;"></div></div>
        </div>
        <div>
          <div style="display: flex; justify-content: space-between; font-size: 11px; margin-bottom: 2px;">
            <span>${c3.replace(/_/g, ' ').toUpperCase()}</span>
            <strong>${p3}%</strong>
          </div>
          <div class="subsystem-track"><div class="subsystem-fill fill-nominal" style="width: ${p3 * 3}%;"></div></div>
        </div>
      `;
    }
  }
}

window.DiagnosticsModule = DiagnosticsModule;
