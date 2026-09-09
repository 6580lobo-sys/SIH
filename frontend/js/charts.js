/**
 * AEROSPACE INSTRUMENTATION CHARTING ENGINE
 * Pure lightweight Canvas implementation tailored for defence telemetry.
 * Zero external libraries, high DPI crispness, precision hairline rendering.
 */

class AeroCharts {
  static setupCanvas(canvas) {
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    if (canvas.width !== Math.floor(rect.width * dpr) || canvas.height !== Math.floor(rect.height * dpr)) {
      canvas.width = Math.floor(rect.width * dpr);
      canvas.height = Math.floor(rect.height * dpr);
    }
    const ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { ctx, width: rect.width, height: rect.height };
  }

  /**
   * Compact engineering telemetry sparkline
   */
  static drawSparkline(canvasId, data, options = {}) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const { ctx, width, height } = this.setupCanvas(canvas);

    ctx.clearRect(0, 0, width, height);

    if (!data || data.length < 2) return;

    const min = options.min !== undefined ? options.min : Math.min(...data);
    const max = options.max !== undefined ? options.max : Math.max(...data);
    const range = (max - min) || 1;

    const strokeColor = options.strokeColor || '#4A5868';
    const isWatch = options.isWatch || false;

    // Optional reference threshold band
    if (options.threshold) {
      const threshY = height - ((options.threshold - min) / range) * height;
      ctx.beginPath();
      ctx.strokeStyle = 'rgba(156, 110, 30, 0.25)';
      ctx.setLineDash([2, 2]);
      ctx.lineWidth = 1;
      ctx.moveTo(0, threshY);
      ctx.lineTo(width, threshY);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // Draw sparkline trace
    ctx.beginPath();
    ctx.strokeStyle = isWatch ? '#9C6E1E' : strokeColor;
    ctx.lineWidth = 1.2;
    ctx.lineJoin = 'round';

    const step = width / (data.length - 1);
    data.forEach((val, i) => {
      const x = i * step;
      const y = height - ((val - min) / range) * (height - 4) - 2;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();

    // Draw current end pin
    const lastVal = data[data.length - 1];
    const lastX = width;
    const lastY = height - ((lastVal - min) / range) * (height - 4) - 2;

    ctx.beginPath();
    ctx.fillStyle = isWatch ? '#9C6E1E' : '#2D5438';
    ctx.arc(lastX - 2, lastY, 2, 0, Math.PI * 2);
    ctx.fill();
  }

  /**
   * Section 8: DEGRADATION TREND CHART
   * Displays Historical health, Current condition (NOW), Model prediction, Uncertainty range,
   * Predicted threshold, and Estimated service window.
   */
  static drawDegradationTrend(canvasId) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const { ctx, width, height } = this.setupCanvas(canvas);

    ctx.clearRect(0, 0, width, height);

    const padLeft = 40;
    const padRight = 30;
    const padTop = 24;
    const padBottom = 26;

    const plotW = width - padLeft - padRight;
    const plotH = height - padTop - padBottom;

    // Timeline split: Past 60%, Forecast 40%
    const nowX = padLeft + plotW * 0.58;

    // Faint grid lines
    ctx.strokeStyle = '#EAE8E0';
    ctx.lineWidth = 1;

    // Horizontal grid lines (Health %: 100%, 95%, 90%, 85%, 80%)
    const gridLevels = [
      { pct: 100, label: '100%' },
      { pct: 95, label: '95%' },
      { pct: 90, label: '90%' },
      { pct: 85, label: '85%' },
      { pct: 80, label: '80%' }
    ];

    ctx.font = '10px "IBM Plex Mono", monospace';
    ctx.fillStyle = '#8C939A';
    ctx.textAlign = 'right';

    gridLevels.forEach(lvl => {
      const y = padTop + ((100 - lvl.pct) / 20) * plotH;
      ctx.beginPath();
      ctx.moveTo(padLeft, y);
      ctx.lineTo(width - padRight, y);
      ctx.stroke();
      ctx.fillText(lvl.label, padLeft - 6, y + 3);
    });

    // Service Limit Threshold Line (at 85% health)
    const threshY = padTop + ((100 - 85) / 20) * plotH;
    ctx.beginPath();
    ctx.strokeStyle = 'rgba(161, 52, 52, 0.45)';
    ctx.setLineDash([4, 3]);
    ctx.lineWidth = 1;
    ctx.moveTo(padLeft, threshY);
    ctx.lineTo(width - padRight, threshY);
    ctx.stroke();
    ctx.setLineDash([]);

    ctx.fillStyle = '#A13434';
    ctx.textAlign = 'left';
    ctx.fillText('PREDICTED SERVICE THRESHOLD (85.0%)', padLeft + 6, threshY - 5);

    // Vertical "NOW" indicator line
    ctx.beginPath();
    ctx.strokeStyle = '#2B5738';
    ctx.lineWidth = 1.2;
    ctx.setLineDash([3, 2]);
    ctx.moveTo(nowX, padTop);
    ctx.lineTo(nowX, height - padBottom);
    ctx.stroke();
    ctx.setLineDash([]);

    // "NOW" label badge
    ctx.fillStyle = '#2B5738';
    ctx.fillRect(nowX - 22, padTop - 18, 44, 15);
    ctx.fillStyle = '#FFFFFF';
    ctx.font = '700 9px "IBM Plex Mono", monospace';
    ctx.textAlign = 'center';
    ctx.fillText('NOW', nowX, padTop - 7);

    // Section Labels: HISTORICAL (Past) vs FORECAST
    ctx.font = '600 9px "IBM Plex Mono", monospace';
    ctx.fillStyle = '#7C838A';
    ctx.textAlign = 'left';
    ctx.fillText('HISTORICAL HEALTH [0 - 180 FLT HRS]', padLeft + 6, height - 8);

    ctx.textAlign = 'right';
    ctx.fillText('MODEL FORECAST [+ 428 HRS TO LIMIT]', width - padRight - 6, height - 8);

    // Generate degradation curve points
    // Past points (from 100 down to 98.2 with realistic sensor noise)
    const pastSteps = 40;
    const pastPoints = [];
    for (let i = 0; i <= pastSteps; i++) {
      const t = i / pastSteps;
      const x = padLeft + t * (nowX - padLeft);
      // Gentle wear curve with subtle telemetry noise
      const noise = (Math.sin(i * 1.8) * 0.15) + (Math.cos(i * 3.1) * 0.1);
      const health = 100 - (1.8 * Math.pow(t, 1.3)) + noise;
      const y = padTop + ((100 - health) / 20) * plotH;
      pastPoints.push({ x, y, health });
    }

    // Forecast points (from 98.2 down to 82.0 at end of timeline)
    const forecastSteps = 30;
    const forecastCenter = [];
    const forecastUpper = [];
    const forecastLower = [];

    for (let i = 0; i <= forecastSteps; i++) {
      const t = i / forecastSteps;
      const x = nowX + t * (width - padRight - nowX);
      const meanDrop = 1.8 + (15.5 * Math.pow(t, 1.25));
      const meanHealth = 98.2 - (meanDrop - 1.8);
      const uncertainty = 0.8 + 2.2 * t; // spreads out with time

      const yMean = padTop + ((100 - meanHealth) / 20) * plotH;
      const yUpper = padTop + ((100 - (meanHealth + uncertainty)) / 20) * plotH;
      const yLower = padTop + ((100 - (meanHealth - uncertainty)) / 20) * plotH;

      forecastCenter.push({ x, y: yMean });
      forecastUpper.push({ x, y: yUpper });
      forecastLower.push({ x, y: yLower });
    }

    // 1. Draw Forecast Uncertainty Band (Shaded Envelope)
    ctx.beginPath();
    ctx.fillStyle = 'rgba(74, 88, 104, 0.07)';
    ctx.moveTo(forecastUpper[0].x, forecastUpper[0].y);
    forecastUpper.forEach(pt => ctx.lineTo(pt.x, pt.y));
    for (let i = forecastLower.length - 1; i >= 0; i--) {
      ctx.lineTo(forecastLower[i].x, forecastLower[i].y);
    }
    ctx.closePath();
    ctx.fill();

    // Upper and lower envelope boundary lines
    ctx.beginPath();
    ctx.strokeStyle = 'rgba(74, 88, 104, 0.25)';
    ctx.lineWidth = 0.8;
    ctx.setLineDash([2, 2]);
    forecastUpper.forEach((pt, i) => i === 0 ? ctx.moveTo(pt.x, pt.y) : ctx.lineTo(pt.x, pt.y));
    forecastLower.forEach((pt, i) => i === 0 ? ctx.moveTo(pt.x, pt.y) : ctx.lineTo(pt.x, pt.y));
    ctx.stroke();
    ctx.setLineDash([]);

    // 2. Draw Past Historical Trace
    ctx.beginPath();
    ctx.strokeStyle = '#2B5738';
    ctx.lineWidth = 1.6;
    pastPoints.forEach((pt, i) => i === 0 ? ctx.moveTo(pt.x, pt.y) : ctx.lineTo(pt.x, pt.y));
    ctx.stroke();

    // 3. Draw Forecast Predicted Trace
    ctx.beginPath();
    ctx.strokeStyle = '#4A5868';
    ctx.lineWidth = 1.4;
    ctx.setLineDash([4, 2]);
    forecastCenter.forEach((pt, i) => i === 0 ? ctx.moveTo(pt.x, pt.y) : ctx.lineTo(pt.x, pt.y));
    ctx.stroke();
    ctx.setLineDash([]);

    // 4. Current State Pin at NOW
    const currentPt = pastPoints[pastPoints.length - 1];
    ctx.beginPath();
    ctx.fillStyle = '#2B5738';
    ctx.arc(currentPt.x, currentPt.y, 4, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = '#FFFFFF';
    ctx.lineWidth = 1.5;
    ctx.stroke();

    // Callout text at current point
    ctx.fillStyle = '#181B1E';
    ctx.font = '700 10px "IBM Plex Mono", monospace';
    ctx.textAlign = 'left';
    ctx.fillText('98.2 INDEX', currentPt.x + 8, currentPt.y - 4);

    // Estimated Service Window intersection bracket
    const serviceIntersectionX = nowX + (width - padRight - nowX) * 0.76;
    ctx.fillStyle = '#7A530C';
    ctx.font = '600 9px "IBM Plex Mono", monospace';
    ctx.textAlign = 'center';
    ctx.fillText('ESTIMATED SERVICE WINDOW: 390 - 470 HRS', serviceIntersectionX, threshY + 16);
  }

  /**
   * Section 13: MISSION REPLAY MULTI-PARAM TRACES
   */
  static drawMissionReplayTimeline(canvasId, playbackFraction, markers = []) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const { ctx, width, height } = this.setupCanvas(canvas);

    ctx.clearRect(0, 0, width, height);

    const padLeft = 45;
    const padRight = 20;
    const padTop = 15;
    const padBottom = 25;

    const plotW = width - padLeft - padRight;
    const plotH = height - padTop - padBottom;

    // Background tracks (6 synchronized parameters)
    const traces = [
      { name: 'RPM', color: '#2B5738', base: 0.15, amp: 0.12, label: '2,450' },
      { name: 'EGT', color: '#9C6E1E', base: 0.32, amp: 0.14, label: '612°C' },
      { name: 'CHT', color: '#4A5868', base: 0.50, amp: 0.10, label: '168°C' },
      { name: 'OIL P', color: '#5A626A', base: 0.68, amp: 0.08, label: '4.82b' },
      { name: 'FUEL', color: '#727A82', base: 0.85, amp: 0.07, label: '21.7L' }
    ];

    // Draw baseline channels
    traces.forEach(trace => {
      const yBase = padTop + trace.base * plotH;
      ctx.beginPath();
      ctx.strokeStyle = '#EAE8E1';
      ctx.lineWidth = 1;
      ctx.moveTo(padLeft, yBase);
      ctx.lineTo(width - padRight, yBase);
      ctx.stroke();

      ctx.fillStyle = trace.color;
      ctx.font = '700 9px "IBM Plex Mono", monospace';
      ctx.textAlign = 'right';
      ctx.fillText(trace.name, padLeft - 6, yBase + 3);

      // Draw synthetic mission data line
      ctx.beginPath();
      ctx.strokeStyle = trace.color;
      ctx.lineWidth = 1.2;
      const pts = 80;
      for (let i = 0; i <= pts; i++) {
        const u = i / pts;
        const x = padLeft + u * plotW;
        
        // Flight phase shape: Climb (0-0.2), Cruise (0.2-0.7), Anomaly glitch at 0.35, Descent (0.7-1.0)
        let modifier = 0;
        if (u < 0.2) modifier = u * 2.5; // climb
        else if (u >= 0.2 && u < 0.7) modifier = 0.5 + Math.sin(u * 20) * 0.05;
        else modifier = 0.5 * (1 - (u - 0.7) / 0.3);

        // Inject intentional EGT anomaly at u ~ 0.34
        if (trace.name === 'EGT' && Math.abs(u - 0.34) < 0.06) {
          modifier += (0.06 - Math.abs(u - 0.34)) * 3.5;
        }

        const y = yBase - (modifier * trace.amp * plotH);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
    });

    // Draw Flight Markers along the top
    markers.forEach(m => {
      const mx = padLeft + m.pos * plotW;
      ctx.beginPath();
      ctx.strokeStyle = m.type === 'anomaly' ? '#9C6E1E' : '#959DA4';
      ctx.setLineDash([2, 2]);
      ctx.lineWidth = 1;
      ctx.moveTo(mx, padTop);
      ctx.lineTo(mx, height - padBottom);
      ctx.stroke();
      ctx.setLineDash([]);

      // Marker tag
      ctx.fillStyle = m.type === 'anomaly' ? '#FBF4E4' : '#F0EFEA';
      ctx.fillRect(mx - 18, padTop - 12, 36, 12);
      ctx.strokeRect(mx - 18, padTop - 12, 36, 12);

      ctx.fillStyle = m.type === 'anomaly' ? '#946816' : '#4A5158';
      ctx.font = '700 8px "IBM Plex Mono", monospace';
      ctx.textAlign = 'center';
      ctx.fillText(m.name, mx, padTop - 3);
    });

    // Draw Current Playhead Scrubber Position
    const scrubX = padLeft + playbackFraction * plotW;
    ctx.beginPath();
    ctx.strokeStyle = '#181B1E';
    ctx.lineWidth = 1.5;
    ctx.moveTo(scrubX, padTop - 4);
    ctx.lineTo(scrubX, height - padBottom + 4);
    ctx.stroke();

    // Playhead head marker
    ctx.fillStyle = '#181B1E';
    ctx.beginPath();
    ctx.moveTo(scrubX - 4, padTop - 4);
    ctx.lineTo(scrubX + 4, padTop - 4);
    ctx.lineTo(scrubX, padTop + 2);
    ctx.closePath();
    ctx.fill();
  }

  /**
   * Section 14: SIMULATION COMPARISON CHART
   */
  static drawSimulationComparison(canvasId, altitude, throttle, temp) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const { ctx, width, height } = this.setupCanvas(canvas);

    ctx.clearRect(0, 0, width, height);

    const padLeft = 45;
    const padRight = 20;
    const padTop = 20;
    const padBottom = 25;

    const plotW = width - padLeft - padRight;
    const plotH = height - padTop - padBottom;

    // Grid lines
    ctx.strokeStyle = '#EAE8E0';
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const y = padTop + (i / 4) * plotH;
      ctx.beginPath();
      ctx.moveTo(padLeft, y);
      ctx.lineTo(width - padRight, y);
      ctx.stroke();
    }

    ctx.font = '9px "IBM Plex Mono", monospace';
    ctx.fillStyle = '#8C939A';
    ctx.textAlign = 'right';
    ctx.fillText('750°C', padLeft - 6, padTop + 4);
    ctx.fillText('600°C', padLeft - 6, padTop + plotH * 0.5 + 4);
    ctx.fillText('450°C', padLeft - 6, padTop + plotH + 4);

    // Baseline EGT curve (nominal standard day 15°C, sea-level)
    ctx.beginPath();
    ctx.strokeStyle = '#959DA4';
    ctx.lineWidth = 1.2;
    ctx.setLineDash([3, 2]);
    for (let i = 0; i <= 30; i++) {
      const t = i / 30;
      const x = padLeft + t * plotW;
      const baseEgt = 560 + 100 * Math.sin(t * Math.PI);
      const y = padTop + ((750 - baseEgt) / 300) * plotH;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
    ctx.setLineDash([]);

    // Simulated EGT response based on user parameters
    // Higher altitude -> lower density -> leaner or richer depending on ECU, higher EGT with high throttle
    const altFactor = (altitude / 25000) * 45;
    const throttleFactor = (throttle / 100) * 120;
    const tempFactor = (temp - 15) * 1.2;

    ctx.beginPath();
    ctx.strokeStyle = '#9C6E1E';
    ctx.lineWidth = 1.8;
    for (let i = 0; i <= 30; i++) {
      const t = i / 30;
      const x = padLeft + t * plotW;
      const simEgt = 520 + throttleFactor + altFactor + tempFactor + (30 * Math.sin(t * 3.5));
      const clampedEgt = Math.min(740, Math.max(460, simEgt));
      const y = padTop + ((750 - clampedEgt) / 300) * plotH;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();

    // Chart Legend
    ctx.font = '600 9px "IBM Plex Mono", monospace';
    ctx.fillStyle = '#727A82';
    ctx.textAlign = 'left';
    ctx.fillText('--- BASELINE (STANDARD ATMOSPHERE)', padLeft + 10, padTop - 6);

    ctx.fillStyle = '#9C6E1E';
    ctx.fillText('── PREDICTED RESPONSE CURVE', padLeft + 220, padTop - 6);
  }
}

window.AeroCharts = AeroCharts;
