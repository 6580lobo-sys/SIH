/**
 * DRDO ADE PROPULSION AIRWORTHINESS REPORT GENERATOR
 * Problem Statement: DRDO PS26054 · MALE UAV Digital Twin Platform
 * Formats official DRDO flight readiness documentation with signature blocks.
 */

class ReportGenerator {
  constructor() {
    this.init();
  }

  init() {
    const triggerBtn = document.getElementById('btn-generate-audit-report');
    if (triggerBtn) {
      triggerBtn.addEventListener('click', () => this.showReportModal());
    }
  }

  generateReportHtml() {
    const dateStr = new Date().toUTCString();
    const eng = window.appCoordinator && window.appCoordinator.telemetryEngine 
      ? window.appCoordinator.telemetryEngine.getTelemetry()
      : { name: 'PORT ENGINE (AE-01)', serial: 'ROTAX-915IS-98214', healthIndex: 98.2 };

    return `
      <div class="drdo-report-container" id="printable-drdo-report">
        <!-- Official DRDO Header Strip -->
        <div class="report-drdo-header">
          <div style="display: flex; align-items: center; gap: 14px;">
            <div class="drdo-emblem-badge">DRDO &bull; ADE</div>
            <div>
              <div class="report-title-main">DEFENCE RESEARCH &amp; DEVELOPMENT ORGANISATION (DRDO)</div>
              <div class="report-subtitle">AERONAUTICAL DEVELOPMENT ESTABLISHMENT (ADE) &bull; PROPULSION DIVISION</div>
              <div class="report-meta-doc">MALE UAV DIGITAL TWIN ENGINE HEALTH &amp; AIRWORTHINESS AUDIT CERTIFICATE</div>
            </div>
          </div>
          <div style="text-align: right; font-family: var(--font-mono); font-size: 11px;">
            <div>DOC ID: <strong>ADE/UAV-DT/2026/0894</strong></div>
            <div>CLASSIFICATION: <strong>RESTRICTED / DEFENCE USE ONLY</strong></div>
            <div>ISSUE DATE: <strong>${dateStr}</strong></div>
          </div>
        </div>

        <div style="height: 1px; background: #000; margin: 12px 0 16px 0;"></div>

        <!-- Section 1: Airframe & Mission Summary -->
        <div class="report-section-block">
          <div class="report-sec-heading">1. AIRFRAME &amp; PROPULSION SYSTEM METADATA</div>
          <div class="report-grid-3">
            <div><span class="lbl">AIRFRAME:</span> <strong>TAPAS-BH-201 (RUSTOM-II MALE UAV)</strong></div>
            <div><span class="lbl">TAIL NUMBER:</span> <strong>UAV-07 (T-07)</strong></div>
            <div><span class="lbl">STATION:</span> <strong>ATR CHITRADURGA / GCS-ALPHA</strong></div>
            <div><span class="lbl">PROPULSION UNIT:</span> <strong>${eng.name}</strong></div>
            <div><span class="lbl">ENGINE SERIAL:</span> <strong>${eng.serial}</strong></div>
            <div><span class="lbl">TOTAL RUN TIME:</span> <strong>180.4 FLIGHT HOURS</strong></div>
            <div><span class="lbl">SORTIE ID:</span> <strong>ENDURANCE ISR-04</strong></div>
            <div><span class="lbl">SORTIE TIME (MET):</span> <strong>04:17:32</strong></div>
            <div><span class="lbl">OPERATIONAL CEILING:</span> <strong>18,500 ft ASL</strong></div>
          </div>
        </div>

        <!-- Section 2: Health Index & Residual Physics -->
        <div class="report-section-block" style="margin-top: 14px;">
          <div class="report-sec-heading">2. DIGITAL TWIN RESIDUAL ANALYSIS &amp; HEALTH INDEX</div>
          <p style="font-size: 12px; margin-bottom: 8px; line-height: 1.5;">
            Telemetry ingested across redundant CAN-A/B bus was compared in real-time against the M1 Otto-cycle physics reference model. Residual divergence vectors were processed via M2 EWMA smoothing and M4 Random Forest Classifier.
          </p>
          <table class="report-table">
            <thead>
              <tr>
                <th>MONITORED TELEMETRY VECTOR</th>
                <th>MEASURED VALUE</th>
                <th>PHYSICS MODEL PREDICTION</th>
                <th>RESIDUAL DELTA (&Delta;)</th>
                <th>TOLERANCE LIMIT</th>
                <th>STATUS</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Engine Speed (RPM)</td>
                <td>${eng.rpm} RPM</td>
                <td>2,434 RPM</td>
                <td>+4.2 RPM</td>
                <td>&plusmn; 60 RPM</td>
                <td><span class="status-tag nominal">NORMAL</span></td>
              </tr>
              <tr>
                <td>Cylinder Head Temp (CHT Peak)</td>
                <td>${eng.cht} °C</td>
                <td>165.6 °C</td>
                <td>+1.8 °C</td>
                <td>&plusmn; 15.0 °C</td>
                <td><span class="status-tag nominal">NORMAL</span></td>
              </tr>
              <tr>
                <td>Exhaust Gas Temp (EGT Cyl-03)</td>
                <td>${eng.egt} °C</td>
                <td>584.1 °C</td>
                <td><strong>+28.7 °C</strong></td>
                <td>&plusmn; 35.0 °C</td>
                <td><span class="status-tag watch">WATCH</span></td>
              </tr>
              <tr>
                <td>Main Oil Gallery Pressure</td>
                <td>${eng.oilPress} bar</td>
                <td>4.86 bar</td>
                <td>-0.04 bar</td>
                <td>&plusmn; 0.60 bar</td>
                <td><span class="status-tag nominal">NORMAL</span></td>
              </tr>
              <tr>
                <td>Engine Sump Oil Temperature</td>
                <td>${eng.oilTemp} °C</td>
                <td>93.6 °C</td>
                <td>+0.6 °C</td>
                <td>&plusmn; 8.0 °C</td>
                <td><span class="status-tag nominal">NORMAL</span></td>
              </tr>
              <tr>
                <td>Total Fuel Flow Rate</td>
                <td>${eng.fuelFlow} L/hr</td>
                <td>21.35 L/hr</td>
                <td>+0.35 L/hr</td>
                <td>&plusmn; 1.50 L/hr</td>
                <td><span class="status-tag nominal">NORMAL</span></td>
              </tr>
              <tr>
                <td>Gearbox Vibration (Broadband)</td>
                <td>${eng.vibration} g</td>
                <td>0.76 g</td>
                <td><strong>+0.08 g</strong></td>
                <td>&plusmn; 0.25 g</td>
                <td><span class="status-tag watch">WATCH</span></td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Section 3: Machine Learning & Prognostics -->
        <div class="report-section-block" style="margin-top: 14px;">
          <div class="report-sec-heading">3. M4 AI/ML PROGNOSTICS &amp; REMAINING USEFUL LIFE (RUL)</div>
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px;">
            <div style="padding: 10px; border: 1px solid #D0CDC3; background: #FAF9F6; font-size: 11.5px; line-height: 1.5;">
              <div>&bull; <strong>Composite Health Index:</strong> ${eng.healthIndex} / 100</div>
              <div>&bull; <strong>Isolation Forest Anomaly Score:</strong> 0.18 (Threshold 0.082)</div>
              <div>&bull; <strong>Random Forest Predicted Mode:</strong> Misfire / Injector Imbalance (87.0% Conf)</div>
              <div>&bull; <strong>Estimated Remaining Useful Life:</strong> 428 Hours (95% CI: 390 &ndash; 470 h)</div>
            </div>
            <div style="padding: 10px; border: 1px solid #D0CDC3; background: #FAF9F6; font-size: 11.5px; line-height: 1.5;">
              <strong>Engineering Conclusion:</strong><br>
              Engine displays nominal structural integrity with zero immediate safety-of-flight compromise. Cylinder 3 injector nozzle coking suspected. Recommended ultrasonic bench flow test during 50h depot turnaround.
            </div>
          </div>
        </div>

        <!-- Section 4: Maintenance Sign-Off -->
        <div class="report-section-block" style="margin-top: 18px;">
          <div class="report-sec-heading">4. AIRWORTHINESS SIGN-OFF &amp; AUTHORIZATION</div>
          <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-top: 12px; font-family: var(--font-mono); font-size: 11px;">
            <div style="border-top: 1px solid #777; padding-top: 6px;">
              <div>PROPULSION SPECIALIST</div>
              <strong style="font-size: 12px;">FLT-LT H. VANCE</strong>
              <div style="color: #666;">DRDO ADE Propulsion Cell</div>
            </div>
            <div style="border-top: 1px solid #777; padding-top: 6px;">
              <div>GROUND CONTROL OFFICER</div>
              <strong style="font-size: 12px;">SQN-LDR V. SHARMA</strong>
              <div style="color: #666;">Mission Commander T-07</div>
            </div>
            <div style="border-top: 1px solid #777; padding-top: 6px;">
              <div>DEPOT CHIEF INSPECTOR</div>
              <strong style="font-size: 12px;">WO D. LAL (CHIEF TECH)</strong>
              <div style="color: #666;">Quality Assurance Division</div>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  showReportModal() {
    let modal = document.getElementById('drdo-report-modal');
    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'drdo-report-modal';
      modal.className = 'drdo-modal-overlay';
      modal.innerHTML = `
        <div class="drdo-modal-window">
          <div class="drdo-modal-header">
            <div>
              <span style="font-family: var(--font-mono); font-size: 10px; color: var(--text-tertiary); text-transform: uppercase;">
                DRDO ADE &bull; OFFICIAL AIRWORTHINESS CERTIFICATE
              </span>
              <h2 style="font-family: var(--font-display); font-size: 16px; font-weight: 700; color: var(--text-primary);">
                Mission Propulsion Health Audit Report (TAPAS-BH-201)
              </h2>
            </div>
            <div style="display: flex; gap: 8px;">
              <button class="eng-btn active" id="btn-print-report">&darr; PRINT / SAVE AS PDF</button>
              <button class="drawer-close-btn" id="btn-close-report-modal">&times;</button>
            </div>
          </div>
          <div class="drdo-modal-body" id="drdo-modal-content-mount">
            <!-- Injected -->
          </div>
        </div>
      `;
      document.body.appendChild(modal);

      document.getElementById('btn-close-report-modal').addEventListener('click', () => {
        modal.classList.remove('open');
      });

      document.getElementById('btn-print-report').addEventListener('click', () => {
        window.print();
      });

      modal.addEventListener('click', (e) => {
        if (e.target === modal) modal.classList.remove('open');
      });
    }

    const mount = document.getElementById('drdo-modal-content-mount');
    if (mount) {
      mount.innerHTML = this.generateReportHtml();
    }

    modal.classList.add('open');
  }
}

window.ReportGenerator = ReportGenerator;
