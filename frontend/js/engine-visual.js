/**
 * AERO-PISTON ENGINE TECHNICAL CUTAWAY VISUALIZATION
 * Renders an engineered SVG cutaway of a 4-cylinder horizontally-opposed UAV aero-piston engine.
 * Supports mechanical component exploration, health annotations, and subsystem telemetry linking.
 */

class EngineVisualizer {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    this.selectedPart = null;
    this.activeMode = 'health'; // 'health', 'thermal', 'mechanical'
    this.init();
  }

  init() {
    if (!this.container) return;
    this.render();
    this.bindEvents();
  }

  render() {
    this.container.innerHTML = `
      <div class="engine-canvas-header">
        <div class="engine-id-badge">
          PROPULSION TWIN: ROTAX-915IS / AE-01 &bull; 4-CYL TURBO PISTON
        </div>
        <div class="engine-mode-toggles">
          <button class="engine-mode-btn ${this.activeMode === 'health' ? 'active' : ''}" data-mode="health">HEALTH OVERLAY</button>
          <button class="engine-mode-btn ${this.activeMode === 'thermal' ? 'active' : ''}" data-mode="thermal">THERMAL GRADIENT</button>
          <button class="engine-mode-btn ${this.activeMode === 'mechanical' ? 'active' : ''}" data-mode="mechanical">SCHEMATIC</button>
        </div>
      </div>

      <svg class="engine-svg" viewBox="0 0 740 390" preserveAspectRatio="xMidYMid meet">
        <defs>
          <!-- Faint grid pattern inside engine viewport -->
          <pattern id="engGrid" width="20" height="20" patternUnits="userSpaceOnUse">
            <path d="M 20 0 L 0 0 0 20" fill="none" stroke="rgba(0,0,0,0.03)" stroke-width="0.5"/>
          </pattern>
          
          <!-- Subtle mechanical gradients -->
          <linearGradient id="crankGrad" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stop-color="#CDC8BD"/>
            <stop offset="50%" stop-color="#B2ADA0"/>
            <stop offset="100%" stop-color="#9C978A"/>
          </linearGradient>

          <linearGradient id="cylGrad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stop-color="#E2DFD6"/>
            <stop offset="50%" stop-color="#D5D1C7"/>
            <stop offset="100%" stop-color="#C5C0B4"/>
          </linearGradient>

          <linearGradient id="cylWatchGrad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stop-color="#F2EBDC"/>
            <stop offset="50%" stop-color="#E5D9C2"/>
            <stop offset="100%" stop-color="#D9C9AA"/>
          </linearGradient>

          <!-- Marker for leader lines -->
          <marker id="dotMarker" viewBox="0 0 6 6" refX="3" refY="3" markerWidth="4" markerHeight="4">
            <circle cx="3" cy="3" r="2" fill="#727A82"/>
          </marker>
        </defs>

        <rect width="100%" height="100%" fill="url(#engGrid)"/>

        <!-- Background Engineering Construction Lines & Axis -->
        <g class="construction-lines">
          <!-- Horizontal centerline (Crankshaft Axis) -->
          <line x1="40" y1="185" x2="700" y2="185" class="tech-crosshair"/>
          <!-- Vertical center bore line -->
          <line x1="370" y1="30" x2="370" y2="340" class="tech-crosshair"/>
          <!-- Dimensional references -->
          <line x1="120" y1="20" x2="120" y2="350" stroke="rgba(0,0,0,0.04)" stroke-width="0.5"/>
          <line x1="620" y1="20" x2="620" y2="350" stroke="rgba(0,0,0,0.04)" stroke-width="0.5"/>
        </g>

        <!-- ================= MECHANICAL LAYERS ================= -->

        <!-- 1. Propeller Shaft & Reduction Gearbox (Left Side) -->
        <g class="engine-part-group" id="part-prop-shaft" data-name="Propeller Reduction Gearbox">
          <!-- Propeller flange -->
          <rect x="70" y="165" width="14" height="40" rx="1" fill="#757269" stroke="#504E47" stroke-width="1"/>
          <!-- Reduction drive casing -->
          <polygon points="84,155 135,145 145,145 145,225 135,225 84,215" fill="#C8C4B8" stroke="#9E9A8E" stroke-width="1.2"/>
          <circle cx="115" cy="185" r="14" fill="#B3AFA3" stroke="#7A766B" stroke-width="1"/>
          <circle cx="115" cy="185" r="5" fill="#6B675D"/>
        </g>

        <!-- 2. Central Crankcase Housing -->
        <g class="engine-part-group" id="part-crankcase" data-name="Crankcase Assembly">
          <path d="M 145,145 L 300,135 L 440,135 L 560,145 L 560,225 L 440,235 L 300,235 L 145,225 Z" 
                class="part-housing"/>
          
          <!-- Crankshaft Internal Axis & Journals -->
          <rect x="145" y="177" width="415" height="16" rx="2" fill="url(#crankGrad)" stroke="#7D796F" stroke-width="1"/>
          
          <!-- Crank throws & counterweights -->
          <rect x="235" y="168" width="16" height="34" rx="2" fill="#9C978A" stroke="#68645B" stroke-width="0.8"/>
          <rect x="330" y="168" width="16" height="34" rx="2" fill="#9C978A" stroke="#68645B" stroke-width="0.8"/>
          <rect x="425" y="168" width="16" height="34" rx="2" fill="#9C978A" stroke="#68645B" stroke-width="0.8"/>
          <rect x="505" y="168" width="16" height="34" rx="2" fill="#9C978A" stroke="#68645B" stroke-width="0.8"/>
        </g>

        <!-- 3. TOP CYLINDERS: CYL 01 (Left) & CYL 03 (Right - WATCH) -->
        <!-- CYL 01 (Nominal) -->
        <g class="engine-part-group state-nominal" id="part-cyl-01" data-name="Cylinder 01 (Port Forward)">
          <!-- Cylinder barrel with cooling fins -->
          <rect x="220" y="55" width="80" height="80" rx="2" fill="url(#cylGrad)" stroke="#9A9689" stroke-width="1"/>
          <!-- Cooling fin ridges -->
          <line x1="214" y1="65" x2="306" y2="65" class="part-cylinder-fin"/>
          <line x1="214" y1="75" x2="306" y2="75" class="part-cylinder-fin"/>
          <line x1="214" y1="85" x2="306" y2="85" class="part-cylinder-fin"/>
          <line x1="214" y1="95" x2="306" y2="95" class="part-cylinder-fin"/>
          <line x1="214" y1="105" x2="306" y2="105" class="part-cylinder-fin"/>
          <line x1="214" y1="115" x2="306" y2="115" class="part-cylinder-fin"/>
          <line x1="214" y1="125" x2="306" y2="125" class="part-cylinder-fin"/>
          <!-- Cylinder head -->
          <path d="M 218,55 L 302,55 L 298,40 L 222,40 Z" fill="#BDB9AC" stroke="#878376" stroke-width="1"/>
          <!-- Spark plug / sensor port -->
          <rect x="256" y="30" width="8" height="10" fill="#757267"/>
          <!-- Subtle green accent indicator (Nominal) -->
          <circle cx="260" cy="50" r="3" fill="#2B5738" stroke="#FFFFFF" stroke-width="1"/>
        </g>

        <!-- CYL 03 (Watch - Elevated EGT / Injector Imbalance) -->
        <g class="engine-part-group state-watch" id="part-cyl-03" data-name="Cylinder 03 (Port Aft - WATCH)">
          <!-- Cylinder barrel -->
          <rect x="410" y="55" width="80" height="80" rx="2" fill="url(#cylWatchGrad)" stroke="#B8860B" stroke-width="1.2"/>
          <!-- Cooling fins -->
          <line x1="404" y1="65" x2="496" y2="65" stroke="#C49B38" stroke-width="0.8"/>
          <line x1="404" y1="75" x2="496" y2="75" stroke="#C49B38" stroke-width="0.8"/>
          <line x1="404" y1="85" x2="496" y2="85" stroke="#C49B38" stroke-width="0.8"/>
          <line x1="404" y1="95" x2="496" y2="95" stroke="#C49B38" stroke-width="0.8"/>
          <line x1="404" y1="105" x2="496" y2="105" stroke="#C49B38" stroke-width="0.8"/>
          <line x1="404" y1="115" x2="496" y2="115" stroke="#C49B38" stroke-width="0.8"/>
          <line x1="404" y1="125" x2="496" y2="125" stroke="#C49B38" stroke-width="0.8"/>
          <!-- Cylinder head -->
          <path d="M 408,55 L 492,55 L 488,40 L 412,40 Z" fill="#D2C09A" stroke="#9C6E1E" stroke-width="1"/>
          <!-- Spark plug / sensor port -->
          <rect x="446" y="30" width="8" height="10" fill="#8A6B29"/>
          <!-- Muted Amber accent indicator (Watch State) -->
          <circle cx="450" cy="50" r="3.5" fill="#9C6E1E" stroke="#FFFFFF" stroke-width="1"/>
        </g>

        <!-- 4. BOTTOM CYLINDERS: CYL 02 (Left) & CYL 04 (Right - Nominal) -->
        <!-- CYL 02 (Nominal) -->
        <g class="engine-part-group state-nominal" id="part-cyl-02" data-name="Cylinder 02 (Starboard Forward)">
          <rect x="220" y="235" width="80" height="80" rx="2" fill="url(#cylGrad)" stroke="#9A9689" stroke-width="1"/>
          <line x1="214" y1="245" x2="306" y2="245" class="part-cylinder-fin"/>
          <line x1="214" y1="255" x2="306" y2="255" class="part-cylinder-fin"/>
          <line x1="214" y1="265" x2="306" y2="265" class="part-cylinder-fin"/>
          <line x1="214" y1="275" x2="306" y2="275" class="part-cylinder-fin"/>
          <line x1="214" y1="285" x2="306" y2="285" class="part-cylinder-fin"/>
          <line x1="214" y1="295" x2="306" y2="295" class="part-cylinder-fin"/>
          <line x1="214" y1="305" x2="306" y2="305" class="part-cylinder-fin"/>
          <!-- Head -->
          <path d="M 218,315 L 302,315 L 298,330 L 222,330 Z" fill="#BDB9AC" stroke="#878376" stroke-width="1"/>
          <rect x="256" y="330" width="8" height="10" fill="#757267"/>
          <circle cx="260" cy="320" r="3" fill="#2B5738" stroke="#FFFFFF" stroke-width="1"/>
        </g>

        <!-- CYL 04 (Nominal) -->
        <g class="engine-part-group state-nominal" id="part-cyl-04" data-name="Cylinder 04 (Starboard Aft)">
          <rect x="410" y="235" width="80" height="80" rx="2" fill="url(#cylGrad)" stroke="#9A9689" stroke-width="1"/>
          <line x1="404" y1="245" x2="496" y2="245" class="part-cylinder-fin"/>
          <line x1="404" y1="255" x2="496" y2="255" class="part-cylinder-fin"/>
          <line x1="404" y1="265" x2="496" y2="265" class="part-cylinder-fin"/>
          <line x1="404" y1="275" x2="496" y2="275" class="part-cylinder-fin"/>
          <line x1="404" y1="285" x2="496" y2="285" class="part-cylinder-fin"/>
          <line x1="404" y1="295" x2="496" y2="295" class="part-cylinder-fin"/>
          <line x1="404" y1="305" x2="496" y2="305" class="part-cylinder-fin"/>
          <!-- Head -->
          <path d="M 408,315 L 492,315 L 488,330 L 412,330 Z" fill="#BDB9AC" stroke="#878376" stroke-width="1"/>
          <rect x="446" y="330" width="8" height="10" fill="#757267"/>
          <circle cx="450" cy="320" r="3" fill="#2B5738" stroke="#FFFFFF" stroke-width="1"/>
        </g>

        <!-- 5. Fuel Injection Rail & Ingestion Paths -->
        <g class="engine-part-group" id="part-fuel-system" data-name="Dual Fuel Injection Rail & ECUs">
          <!-- Rail upper -->
          <line x1="200" y1="138" x2="520" y2="138" class="part-fuel-rail"/>
          <!-- Injector drops to CYL 01 & 03 -->
          <line x1="260" y1="138" x2="260" y2="128" stroke="#8C8472" stroke-width="2"/>
          <line x1="450" y1="138" x2="450" y2="128" stroke="#9C6E1E" stroke-width="2"/>
          
          <!-- Rail lower -->
          <line x1="200" y1="232" x2="520" y2="232" class="part-fuel-rail"/>
          <!-- Injector drops to CYL 02 & 04 -->
          <line x1="260" y1="232" x2="260" y2="242" stroke="#8C8472" stroke-width="2"/>
          <line x1="450" y1="232" x2="450" y2="242" stroke="#8C8472" stroke-width="2"/>
        </g>

        <!-- 6. Exhaust System (Runners & Turbo Manifold) -->
        <g class="engine-part-group" id="part-exhaust-system" data-name="Exhaust Manifold & Turbocharger">
          <!-- Upper exhaust runner -->
          <path d="M 230,42 L 180,42 L 180,110 L 590,110 L 590,165" fill="none" stroke="#A8A395" stroke-width="3"/>
          <path d="M 420,42 L 400,42 L 400,105 L 590,105" fill="none" stroke="#B8860B" stroke-width="3"/>
          <!-- Lower exhaust runner -->
          <path d="M 230,328 L 180,328 L 180,260 L 590,260 L 590,205" fill="none" stroke="#A8A395" stroke-width="3"/>
          <!-- Turbo turbine casing at rear -->
          <circle cx="615" cy="185" r="24" fill="#B3AFA3" stroke="#7A766B" stroke-width="1.2"/>
          <path d="M 615,165 A 20 20 0 0 1 635,185 L 615,185 Z" fill="#8C887C"/>
          <line x1="639" y1="185" x2="675" y2="185" stroke="#7A766B" stroke-width="8" stroke-linecap="round"/>
        </g>

        <!-- 7. Oil Circulation Loop (Pressurized & Scavenge Lines) -->
        <g class="engine-part-group" id="part-oil-loop" data-name="Lubrication & Scavenge Loop">
          <!-- Oil sump & pump -->
          <rect x="335" y="240" width="50" height="18" rx="2" fill="#7D9683" stroke="#4B6E54" stroke-width="1"/>
          <!-- Pressure feed lines -->
          <path d="M 345,240 L 345,195 L 160,195 L 160,150 L 310,150" class="part-oil-loop"/>
          <path d="M 375,240 L 375,195 L 540,195 L 540,150 L 400,150" class="part-oil-loop"/>
        </g>

        <!-- ================= ENGINEERING ANNOTATIONS & LEADER LINES ================= -->

        <!-- Annotation: CYL 01 -->
        <g class="eng-annotation" data-target="part-cyl-01">
          <path d="M 260,35 L 260,24 L 195,24" class="leader-line" marker-start="url(#dotMarker)"/>
          <rect x="110" y="14" width="85" height="20" rx="1" class="annotation-box"/>
          <text x="116" y="28" class="annotation-text-primary">CYL 01</text>
          <text x="156" y="28" class="annotation-text-secondary">167.4°C</text>
        </g>

        <!-- Annotation: CYL 03 (WATCH STATE) -->
        <g class="eng-annotation" data-target="part-cyl-03">
          <path d="M 450,35 L 450,24 L 515,24" class="leader-line" marker-start="url(#dotMarker)"/>
          <rect x="515" y="14" width="130" height="20" rx="1" class="annotation-box" stroke="#B8860B"/>
          <text x="522" y="28" class="annotation-text-primary">CYL 03</text>
          <text x="562" y="28" class="annotation-tag-watch">WATCH: EGT +28°C</text>
        </g>

        <!-- Annotation: OIL LOOP -->
        <g class="eng-annotation" data-target="part-oil-loop">
          <path d="M 340,195 L 340,165 L 305,165" class="leader-line" marker-start="url(#dotMarker)"/>
          <rect x="210" y="155" width="95" height="20" rx="1" class="annotation-box"/>
          <text x="216" y="169" class="annotation-text-primary">OIL LOOP</text>
          <text x="268" y="169" class="annotation-text-secondary">4.82 bar</text>
        </g>

        <!-- Annotation: FUEL INJECTION -->
        <g class="eng-annotation" data-target="part-fuel-system">
          <path d="M 360,138 L 360,118 L 340,118" class="leader-line" marker-start="url(#dotMarker)"/>
          <rect x="220" y="108" width="120" height="20" rx="1" class="annotation-box"/>
          <text x="226" y="122" class="annotation-text-primary">FUEL INJECTION</text>
          <text x="310" y="122" class="annotation-text-secondary">21.7 L/h</text>
        </g>

        <!-- Annotation: CRANKSHAFT -->
        <g class="eng-annotation" data-target="part-crankcase">
          <path d="M 520,185 L 565,185 L 565,165" class="leader-line" marker-start="url(#dotMarker)"/>
          <rect x="565" y="155" width="110" height="20" rx="1" class="annotation-box"/>
          <text x="571" y="169" class="annotation-text-primary">CRANKSHAFT</text>
          <text x="644" y="169" class="annotation-text-secondary">2,438 RPM</text>
        </g>

        <!-- Annotation: CYL 02 -->
        <g class="eng-annotation" data-target="part-cyl-02">
          <path d="M 260,335 L 260,352 L 195,352" class="leader-line" marker-start="url(#dotMarker)"/>
          <rect x="110" y="342" width="85" height="20" rx="1" class="annotation-box"/>
          <text x="116" y="356" class="annotation-text-primary">CYL 02</text>
          <text x="156" y="356" class="annotation-text-secondary">166.8°C</text>
        </g>

        <!-- Annotation: CYL 04 -->
        <g class="eng-annotation" data-target="part-cyl-04">
          <path d="M 450,335 L 450,352 L 515,352" class="leader-line" marker-start="url(#dotMarker)"/>
          <rect x="515" y="342" width="95" height="20" rx="1" class="annotation-box"/>
          <text x="522" y="356" class="annotation-text-primary">CYL 04</text>
          <text x="565" y="356" class="annotation-text-secondary">168.1°C</text>
        </g>

        <!-- Annotation: EXHAUST -->
        <g class="eng-annotation" data-target="part-exhaust-system">
          <path d="M 640,185 L 665,185 L 665,225" class="leader-line" marker-start="url(#dotMarker)"/>
          <rect x="620" y="225" width="90" height="20" rx="1" class="annotation-box"/>
          <text x="626" y="239" class="annotation-text-primary">EXHAUST</text>
          <text x="677" y="239" class="annotation-text-secondary">612.8°C</text>
        </g>
      </svg>

      <div class="engine-canvas-footer">
        <div class="engine-specs">
          <span>BORE/STROKE: <strong>84.0 / 61.0 mm</strong></span>
          <span>DISPLACEMENT: <strong>1,352 cc</strong></span>
          <span>COMPRESSION: <strong>10.5 : 1</strong></span>
          <span>REDUCTION RATIO: <strong>2.54 : 1</strong></span>
        </div>
        <div class="engine-inspect-status">
          <span id="eng-inspected-part-label">CLICK COMPONENT TO INSPECT DETAILED TELEMETRY</span>
        </div>
      </div>
    `;
  }

  bindEvents() {
    // Mode toggles
    this.container.querySelectorAll('.engine-mode-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        this.activeMode = e.target.getAttribute('data-mode');
        this.render();
        this.bindEvents();
      });
    });

    // Component clicks
    const partGroups = this.container.querySelectorAll('.engine-part-group');
    const annotations = this.container.querySelectorAll('.eng-annotation');

    const updateInspection = (name) => {
      const label = document.getElementById('eng-inspected-part-label');
      if (label) {
        label.innerHTML = `INSPECTING: <strong style="color: var(--text-primary);">${name.toUpperCase()}</strong>`;
      }
    };

    partGroups.forEach(grp => {
      grp.addEventListener('click', () => {
        const name = grp.getAttribute('data-name');
        updateInspection(name);
        
        // Highlight in subsystem list if applicable
        if (window.appCoordinator) {
          window.appCoordinator.onEnginePartSelected(grp.id);
        }
      });
    });

    annotations.forEach(ann => {
      ann.addEventListener('click', () => {
        const targetId = ann.getAttribute('data-target');
        const targetPart = document.getElementById(targetId);
        if (targetPart) {
          const name = targetPart.getAttribute('data-name') || targetId;
          updateInspection(name);
          if (window.appCoordinator) {
            window.appCoordinator.onEnginePartSelected(targetId);
          }
        }
      });
    });
  }

  applyFaultHighlight(faultKey) {
    const cyl1 = document.getElementById('part-cyl-01');
    const cyl2 = document.getElementById('part-cyl-02');
    const cyl3 = document.getElementById('part-cyl-03');
    const cyl4 = document.getElementById('part-cyl-04');
    const oilLoop = document.getElementById('part-oil-loop');
    const prop = document.getElementById('part-prop-shaft');
    const fuel = document.getElementById('part-fuel-system');
    const exhaust = document.getElementById('part-exhaust-system');

    [cyl1, cyl2, cyl3, cyl4, oilLoop, prop, fuel, exhaust].forEach(el => {
      if (el) el.classList.remove('state-watch', 'state-critical');
    });

    if (faultKey === 'overheating') {
      if (cyl1) cyl1.classList.add('state-watch');
      if (cyl2) cyl2.classList.add('state-watch');
      if (cyl3) cyl3.classList.add('state-critical');
      if (cyl4) cyl4.classList.add('state-watch');
      if (exhaust) exhaust.classList.add('state-critical');
    } else if (faultKey === 'oil_pressure_drop') {
      if (oilLoop) oilLoop.classList.add('state-critical');
    } else if (faultKey === 'vibration_bearing_fault') {
      if (prop) prop.classList.add('state-watch');
    } else if (faultKey === 'misfire_or_injector_fault') {
      if (cyl3) cyl3.classList.add('state-watch');
      if (fuel) fuel.classList.add('state-watch');
    } else if (faultKey === 'cooling_system_fault') {
      if (cyl1) cyl1.classList.add('state-watch');
      if (cyl3) cyl3.classList.add('state-watch');
    } else if (faultKey === 'fuel_mixture_drift') {
      if (fuel) fuel.classList.add('state-watch');
    }
  }
}

window.EngineVisualizer = EngineVisualizer;
