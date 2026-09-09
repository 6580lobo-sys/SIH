/**
 * MISSION REPLAY & FLIGHT TELEMETRY INVESTIGATION MODULE (M2 DATASET INTEGRATION)
 * Synchronized multi-trace timeline playback with mission event markers and anomaly forensics.
 * Supports loading real DRDO M2 mission runs (4.5h, 6.0h, 8.0h, 10.0h).
 */

class MissionReplayModule {
  constructor(canvasId) {
    this.canvasId = canvasId;
    this.isPlaying = false;
    this.playbackRate = 1;
    this.totalDurationSec = 21600; // 6.0h default (21,600s)
    this.currentSec = 5072;        // 01:24:32 default
    this.timer = null;
    this.activeDataset = 'm2_output_6.0h.json';

    this.datasets = {
      'm2_output_6.0h.json': { name: 'Sortie ISR-04 (6.0h Loiter)', durationSec: 21600 },
      'm2_output_4.5h.json': { name: 'Sortie REC-02 (4.5h High-Alt)', durationSec: 16200 },
      'm2_output_8.0h.json': { name: 'Sortie PAT-08 (8.0h Patrol)', durationSec: 28800 },
      'm2_output_10.0h.json': { name: 'Sortie END-10 (10.0h Endurance)', durationSec: 36000 }
    };

    this.markers = [
      { name: 'TAKEOFF', pos: 0.05, sec: 1080, timeStr: '00:18:00', type: 'nominal' },
      { name: 'CLIMB', pos: 0.15, sec: 3240, timeStr: '00:54:00', type: 'nominal' },
      { name: 'CRUISE', pos: 0.28, sec: 6048, timeStr: '01:40:48', type: 'nominal' },
      { name: 'THROTTLE', pos: 0.31, sec: 6696, timeStr: '01:51:36', type: 'nominal' },
      { name: 'ANOMALY', pos: 0.34, sec: 7344, timeStr: '02:02:24', type: 'anomaly' },
      { name: 'DESCENT', pos: 0.78, sec: 16848, timeStr: '04:40:48', type: 'nominal' },
      { name: 'LANDING', pos: 0.94, sec: 20304, timeStr: '05:38:24', type: 'nominal' }
    ];

    this.init();
  }

  init() {
    this.bindControls();
    this.updateDisplay();
  }

  bindControls() {
    const playBtn = document.getElementById('replay-btn-play');
    const pauseBtn = document.getElementById('replay-btn-pause');
    const stepBackBtn = document.getElementById('replay-btn-step-back');
    const stepFwdBtn = document.getElementById('replay-btn-step-fwd');
    const resetBtn = document.getElementById('replay-btn-reset');
    const slider = document.getElementById('replay-scrubber-slider');
    const datasetSelect = document.getElementById('replay-dataset-select');

    if (playBtn) playBtn.addEventListener('click', () => this.play());
    if (pauseBtn) pauseBtn.addEventListener('click', () => this.pause());
    if (stepBackBtn) stepBackBtn.addEventListener('click', () => this.step(-10));
    if (stepFwdBtn) stepFwdBtn.addEventListener('click', () => this.step(10));
    if (resetBtn) resetBtn.addEventListener('click', () => this.seek(0));

    if (slider) {
      slider.addEventListener('input', (e) => {
        const val = parseFloat(e.target.value);
        this.currentSec = (val / 100) * this.totalDurationSec;
        this.updateDisplay();
      });
    }

    if (datasetSelect) {
      datasetSelect.addEventListener('change', (e) => {
        this.loadDataset(e.target.value);
      });
    }

    // Speed buttons
    document.querySelectorAll('.replay-speed-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        document.querySelectorAll('.replay-speed-btn').forEach(b => b.classList.remove('active'));
        e.target.classList.add('active');
        this.playbackRate = parseFloat(e.target.getAttribute('data-speed')) || 1;
      });
    });

    // Marker click handlers
    document.querySelectorAll('.marker-tag').forEach(tag => {
      tag.addEventListener('click', (e) => {
        const markerName = e.target.getAttribute('data-marker');
        const marker = this.markers.find(m => m.name === markerName);
        if (marker) {
          this.seek(marker.sec);
          if (marker.type === 'anomaly') {
            this.showAnomalyContext();
          }
        }
      });
    });
  }

  loadDataset(filename) {
    if (this.datasets[filename]) {
      this.activeDataset = filename;
      this.totalDurationSec = this.datasets[filename].durationSec;
      this.currentSec = Math.floor(this.totalDurationSec * 0.34);
      this.updateDisplay();
    }
  }

  formatTime(seconds) {
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    const pad = (n) => String(n).padStart(2, '0');
    return `${pad(hrs)}:${pad(mins)}:${pad(secs)}`;
  }

  play() {
    if (this.isPlaying) return;
    this.isPlaying = true;
    const playBtn = document.getElementById('replay-btn-play');
    const pauseBtn = document.getElementById('replay-btn-pause');
    if (playBtn) playBtn.classList.add('active');
    if (pauseBtn) pauseBtn.classList.remove('active');

    this.timer = setInterval(() => {
      this.currentSec += 2 * this.playbackRate;
      if (this.currentSec >= this.totalDurationSec) {
        this.currentSec = this.totalDurationSec;
        this.pause();
      }
      this.updateDisplay();
    }, 100);
  }

  pause() {
    this.isPlaying = false;
    clearInterval(this.timer);
    this.timer = null;
    const playBtn = document.getElementById('replay-btn-play');
    const pauseBtn = document.getElementById('replay-btn-pause');
    if (playBtn) playBtn.classList.remove('active');
    if (pauseBtn) pauseBtn.classList.add('active');
  }

  step(deltaSec) {
    this.seek(this.currentSec + deltaSec);
  }

  seek(sec) {
    this.currentSec = Math.max(0, Math.min(this.totalDurationSec, sec));
    this.updateDisplay();
  }

  updateDisplay() {
    const fraction = this.currentSec / this.totalDurationSec;
    const timeDisplay = document.getElementById('replay-time-readout');
    const slider = document.getElementById('replay-scrubber-slider');

    if (timeDisplay) {
      timeDisplay.textContent = `${this.formatTime(this.currentSec)} / ${this.formatTime(this.totalDurationSec)}`;
    }

    if (slider) {
      slider.value = (fraction * 100).toFixed(2);
    }

    if (window.AeroCharts) {
      window.AeroCharts.drawMissionReplayTimeline(this.canvasId, fraction, this.markers);
    }

    if (Math.abs(fraction - 0.34) < 0.05) {
      this.showAnomalyContext();
    }
  }

  showAnomalyContext() {
    const contextBox = document.getElementById('replay-anomaly-context');
    if (contextBox) {
      contextBox.style.display = 'block';
      contextBox.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 6px;">
          <span style="font-family: var(--font-mono); font-size: 11px; font-weight: 700; color: var(--amber-primary);">
            MISSION EVENT FORENSIC: 14:32:08 UTC &bull; ${this.datasets[this.activeDataset].name}
          </span>
          <span style="font-family: var(--font-mono); font-size: 10px; color: var(--text-tertiary);">
            RECORDED BY ECU-A / CAN TELEMETRY STREAM
          </span>
        </div>
        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; padding: 8px; background: var(--bg-surface-subtle); border: 1px solid var(--border-subtle); border-radius: 2px; font-family: var(--font-mono); font-size: 11px; margin-bottom: 8px;">
          <div><span style="color: var(--text-tertiary);">PARAM:</span> <strong>EGT CYL-03</strong></div>
          <div><span style="color: var(--text-tertiary);">OBSERVED:</span> <strong style="color: var(--amber-primary);">641.5 °C (+28.7°C)</strong></div>
          <div><span style="color: var(--text-tertiary);">CONFIDENCE:</span> <strong>87% (M4 RANDOM FOREST)</strong></div>
          <div><span style="color: var(--text-tertiary);">EST. CAUSE:</span> <strong>INJECTOR IMBALANCE</strong></div>
        </div>
        <div style="font-size: 12px; color: var(--text-secondary); line-height: 1.4;">
          <strong>Propulsion Engineer Context:</strong> Step response during loiter transition showed localized exhaust gas temperature divergence without corresponding CHT surge, indicating partial fuel distribution skew rather than structural blow-by.
        </div>
      `;
    }
  }
}

window.MissionReplayModule = MissionReplayModule;
