/**
 * DEFENCE TELEMETRY & PHYSICAL TWIN SIMULATION ENGINE (DRDO SIH26054 / M1-M2-M3)
 * Implements Otto-cycle physics models, M1 residual calculation, M2 EWMA smoothing,
 * M3 real-time fault injection, and dual-engine twin support (TAPAS-BH-201).
 */

class TelemetryEngine {
  constructor() {
    this.bufferLength = 32;

    // Active engine selection: 'ENG-1' (Port / AE-01) or 'ENG-2' (Starboard / AE-02)
    this.activeEngine = 'ENG-1';

    // Active M3 Fault Mode:
    // 'healthy', 'overheating', 'oil_pressure_drop', 'vibration_bearing_fault',
    // 'misfire_or_injector_fault', 'fuel_mixture_drift', 'cooling_system_fault', 'engine_overspeed'
    this.activeFault = 'misfire_or_injector_fault';

    // Baseline nominal operating state
    this.engines = {
      'ENG-1': {
        name: 'PORT ENGINE (AE-01)',
        serial: 'ROTAX-915IS-98214',
        totalHours: 180.4,
        rpm: 2438,
        cht: 167.4,
        egt: 612.8,
        oilPress: 4.82,
        oilTemp: 94.2,
        fuelFlow: 21.7,
        vibration: 0.84,
        batteryVolt: 28.4,
        alternatorAmp: 42.1,
        timing: 24.5,
        healthIndex: 98.2,
        // M1 Physics Residuals: Actual - Predicted
        residuals: {
          res_rpm: 4.2,
          res_cht: 1.8,
          res_egt: 28.7, // Watch on Cylinder 3
          res_oil_p: -0.04,
          res_oil_t: 0.6,
          res_fuel: 0.35,
          res_vib: 0.08
        }
      },
      'ENG-2': {
        name: 'STARBOARD ENGINE (AE-02)',
        serial: 'ROTAX-915IS-98215',
        totalHours: 180.4,
        rpm: 2435,
        cht: 165.8,
        egt: 609.4,
        oilPress: 4.86,
        oilTemp: 93.6,
        fuelFlow: 21.4,
        vibration: 0.76,
        batteryVolt: 28.4,
        alternatorAmp: 41.8,
        timing: 24.5,
        healthIndex: 99.4,
        residuals: {
          res_rpm: 1.1,
          res_cht: -0.4,
          res_egt: 1.2,
          res_oil_p: 0.02,
          res_oil_t: -0.2,
          res_fuel: 0.05,
          res_vib: 0.01
        }
      }
    };

    // System metrics
    this.system = {
      canPackets: 12481,
      latency: 18,
      packetLoss: 0.02,
      sensorSync: 99.4
    };

    // Ring buffers for historical traces
    this.history = {
      rpm: Array(this.bufferLength).fill(2435),
      cht: Array(this.bufferLength).fill(167.2),
      egt: Array(this.bufferLength).fill(611.0),
      oilPress: Array(this.bufferLength).fill(4.82),
      oilTemp: Array(this.bufferLength).fill(94.0),
      fuelFlow: Array(this.bufferLength).fill(21.6),
      vibration: Array(this.bufferLength).fill(0.83),
      batteryVolt: Array(this.bufferLength).fill(28.4),
      timing: Array(this.bufferLength).fill(24.5),
      // M1 Residual ring buffers
      res_egt: Array(this.bufferLength).fill(28.0),
      res_cht: Array(this.bufferLength).fill(1.8),
      res_oil_p: Array(this.bufferLength).fill(-0.04),
      res_vib: Array(this.bufferLength).fill(0.08)
    };

    this.timer = null;
    this.subscribers = [];
  }

  start() {
    if (this.timer) return;
    this.timer = setInterval(() => this.tick(), 1000);
  }

  stop() {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  subscribe(callback) {
    this.subscribers.push(callback);
  }

  setEngine(engId) {
    if (this.engines[engId]) {
      this.activeEngine = engId;
      this.tick();
    }
  }

  injectFault(faultType) {
    this.activeFault = faultType;
    fetch('http://localhost:8000/api/scenarios/select', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scenario_key: faultType })
    }).catch(() => {});
    this.tick();
  }

  async tick() {
    const jitter = (range) => (Math.random() - 0.5) * range;
    const eng = this.engines[this.activeEngine];

    let backendSynced = false;
    try {
      const res = await fetch('http://localhost:8000/api/telemetry/latest');
      if (res.ok) {
        const data = await res.json();
        if (data && data.rpm !== undefined) {
          eng.rpm = Math.round(data.rpm);
          eng.cht = +(data.cht).toFixed(1);
          eng.egt = +(data.egt).toFixed(1);
          eng.oilPress = +(data.oil_pressure * 0.0689476).toFixed(2);
          eng.oilTemp = +(data.oil_temp).toFixed(1);
          eng.fuelFlow = +(data.fuel_flow).toFixed(1);
          eng.vibration = +(data.vibration_amplitude).toFixed(2);
          eng.healthIndex = +(data.health_index).toFixed(1);

          eng.residuals.res_rpm = +(data.res_rpm).toFixed(1);
          eng.residuals.res_cht = +(data.res_cht).toFixed(1);
          eng.residuals.res_egt = +(data.res_egt).toFixed(1);
          eng.residuals.res_oil_p = +(data.res_oil_p).toFixed(2);
          eng.residuals.res_oil_t = +(data.res_oil_t).toFixed(1);
          eng.residuals.res_fuel = +(data.res_fuel).toFixed(2);
          eng.residuals.res_vib = +(data.res_vib).toFixed(3);

          this.system.backendConnected = true;
          this.system.latency = 8;
          backendSynced = true;
        }
      }
    } catch (_) {
      this.system.backendConnected = false;
    }

    if (!backendSynced) {
      // Base values modified dynamically by M3 Fault Injections
      let targetRpm = 2438;
      let targetCht = 167.4;
      let targetEgt = 612.8;
      let targetOilP = 4.82;
      let targetOilT = 94.2;
      let targetFuel = 21.7;
      let targetVib = 0.84;
      let targetHealth = 98.2;

      let resRpm = 2.0;
      let resCht = 1.2;
      let resEgt = 2.5;
      let resOilP = 0.0;
      let resOilT = 0.2;
      let resFuel = 0.1;
      let resVib = 0.02;

      switch (this.activeFault) {
        case 'abnormal_oil_temp':
          targetOilT = 126.5;
          targetOilP = 3.65;
          resOilT = 32.3;
          resOilP = -1.17;
          targetHealth = 76.4;
          break;

        case 'elevated_egt':
          targetEgt = 824.0;
          targetFuel = 24.2;
          resEgt = 211.2;
          resFuel = 2.5;
          targetHealth = 74.8;
          break;

        case 'cht_overheating':
        case 'overheating':
          targetCht = 218.6;
          targetEgt = 742.0;
          targetOilT = 118.4;
          resCht = 51.2;
          resEgt = 129.2;
          resOilT = 24.2;
          targetHealth = 54.6;
          break;

        case 'oil_pressure_drop':
          targetOilP = 1.38;
          targetOilT = 112.1;
          resOilP = -3.44;
          resOilT = 17.9;
          targetHealth = 58.1;
          break;

        case 'vibration_bearing_fault':
          targetVib = 3.82;
          resVib = 2.98;
          targetHealth = 64.4;
          break;

        case 'misfire_or_injector_fault':
          targetEgt = 641.5;
          targetFuel = 22.4;
          targetRpm = 2415;
          resEgt = 28.7;
          resFuel = 0.7;
          resRpm = -23.0;
          targetHealth = 94.2;
          break;

        case 'fuel_mixture_drift':
          targetEgt = 758.0;
          targetFuel = 28.8;
          resEgt = 145.2;
          resFuel = 7.1;
          targetHealth = 81.8;
          break;

        case 'cooling_system_fault':
          targetCht = 196.2;
          targetOilT = 109.6;
          resCht = 28.8;
          resOilT = 15.4;
          targetHealth = 78.5;
          break;

        case 'engine_overspeed':
          targetRpm = 2850;
          targetFuel = 26.4;
          resRpm = 412.0;
          resFuel = 4.7;
          targetHealth = 71.2;
          break;

        case 'compound_failure':
          targetOilP = 1.45;
          targetOilT = 129.0;
          targetCht = 226.0;
          targetVib = 3.65;
          resOilP = -3.37;
          resOilT = 34.8;
          resCht = 58.6;
          resVib = 2.81;
          targetHealth = 28.4;
          break;

        case 'healthy':
        default:
          targetHealth = 99.4;
          resRpm = 1.2;
          resCht = 0.4;
          resEgt = 1.5;
          resOilP = 0.01;
          resOilT = 0.1;
          resFuel = 0.05;
          resVib = 0.01;
          break;
      }

      // Apply micro-variations
      eng.rpm = Math.round(targetRpm + jitter(8));
      eng.cht = +(targetCht + jitter(0.4)).toFixed(1);
      eng.egt = +(targetEgt + jitter(1.4)).toFixed(1);
      eng.oilPress = +(targetOilP + jitter(0.04)).toFixed(2);
      eng.oilTemp = +(targetOilT + jitter(0.3)).toFixed(1);
      eng.fuelFlow = +(targetFuel + jitter(0.2)).toFixed(1);
      eng.vibration = +(targetVib + jitter(0.02)).toFixed(2);
      eng.healthIndex = +(targetHealth + jitter(0.2)).toFixed(1);

      eng.residuals.res_rpm = +(resRpm + jitter(1.5)).toFixed(1);
    }
    eng.residuals.res_cht = +(resCht + jitter(0.3)).toFixed(1);
    eng.residuals.res_egt = +(resEgt + jitter(0.8)).toFixed(1);
    eng.residuals.res_oil_p = +(resOilP + jitter(0.02)).toFixed(2);
    eng.residuals.res_oil_t = +(resOilT + jitter(0.2)).toFixed(1);
    eng.residuals.res_fuel = +(resFuel + jitter(0.1)).toFixed(2);
    eng.residuals.res_vib = +(resVib + jitter(0.01)).toFixed(3);

    // Update history buffers
    const pushBuf = (key, val) => {
      if (this.history[key]) {
        this.history[key].shift();
        this.history[key].push(val);
      }
    };

    pushBuf('rpm', eng.rpm);
    pushBuf('cht', eng.cht);
    pushBuf('egt', eng.egt);
    pushBuf('oilPress', eng.oilPress);
    pushBuf('oilTemp', eng.oilTemp);
    pushBuf('fuelFlow', eng.fuelFlow);
    pushBuf('vibration', eng.vibration);
    pushBuf('batteryVolt', eng.batteryVolt);
    pushBuf('timing', eng.timing);
    pushBuf('res_egt', eng.residuals.res_egt);
    pushBuf('res_cht', eng.residuals.res_cht);
    pushBuf('res_oil_p', eng.residuals.res_oil_p);
    pushBuf('res_vib', eng.residuals.res_vib);

    // Notify listeners
    this.subscribers.forEach(cb => cb(eng, this.history, this.activeFault, this.system));
  }

  async evaluateLiveProbe(probe) {
    try {
      const response = await fetch('http://localhost:8000/api/probe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          rpm: Number(probe.rpm || 2438),
          throttle: Number(probe.throttle || 65),
          oil_temp: Number(probe.oilTemp || 94.2),
          oil_pressure: Number(probe.oilPress || 4.82) * 14.5038,
          cht: Number(probe.cht || 167.4),
          egt: Number(probe.egt || 612.8),
          fuel_flow: Number(probe.fuelFlow || 21.7),
          vibration: Number(probe.vibration || 0.84),
          mission_duration_hours: Number(probe.missionDurationHours || 8.0)
        })
      });
      if (response.ok) {
        const data = await response.json();
        const m1 = data.m1_residuals || {};
        const m2 = data.m2_prognostics || {};
        const m4 = data.m4_ml_prediction || {};
        return {
          inputs: probe,
          residuals: {
            resRpm: +(m1.res_rpm || 0).toFixed(1),
            resCht: +(m1.res_cht || 0).toFixed(1),
            resEgt: +(m1.res_egt || 0).toFixed(1),
            resOilP: +(m1.res_oil_p || 0).toFixed(2),
            resOilT: +(m1.res_oil_t || 0).toFixed(1),
            resFuel: +(m1.res_fuel || 0).toFixed(2),
            resVib: +(m1.res_vib || 0).toFixed(3),
          },
          compositeScore: +(m2.composite_score || 0).toFixed(4),
          healthIndex: +(m2.health_index || 100).toFixed(1),
          severity: m2.severity_level || 'NORMAL',
          rul: {
            est: +(m2.rul_est !== undefined && !isNaN(m2.rul_est) ? m2.rul_est : 480).toFixed(1),
            lower: +(m2.rul_lower !== undefined && !isNaN(m2.rul_lower) ? m2.rul_lower : 440).toFixed(1),
            upper: +(m2.rul_upper !== undefined && !isNaN(m2.rul_upper) ? m2.rul_upper : 520).toFixed(1),
            status: m2.rul_status || 'estimable'
          },
          ml: {
            isAnomaly: Boolean(m4.is_anomaly),
            anomalyScore: +(m4.anomaly_score || 0).toFixed(4),
            predictedClass: m4.fault_type || 'healthy',
            confidence: +(m4.confidence || 0.95).toFixed(3),
            topFeatures: m4.top_features || ['health_index', 'baseline_rul']
          }
        };
      }
    } catch (_) {}

    const rpm = Number(probe.rpm || 2438);
    const throttle = Number(probe.throttle || 65);
    const oilTemp = Number(probe.oilTemp || 94.2);
    const oilPress = Number(probe.oilPress || 4.82);
    const cht = Number(probe.cht || 167.4);
    const egt = Number(probe.egt || 612.8);
    const fuelFlow = Number(probe.fuelFlow || 21.7);
    const vib = Number(probe.vibration || 0.84);
    const missionHours = Number(probe.missionDurationHours || 8.0);

    // M1 Physics Twin Expected Baseline
    const predRpm = 1400 + (throttle / 100) * 1600;
    const predCht = 90 + (throttle / 100) * 115;
    const predEgt = 520 + (throttle / 100) * 140;
    const predOilP = 2.5 + (throttle / 100) * 3.5;
    const predOilT = 60 + (throttle / 100) * 50;
    const predFuel = 3.0 + (throttle / 100) * 28;
    const predVib = 0.2 + (throttle / 100) * 0.9;

    // M1 Residuals (Actual - Predicted)
    const resRpm = +(rpm - predRpm).toFixed(1);
    const resCht = +(cht - predCht).toFixed(1);
    const resEgt = +(egt - predEgt).toFixed(1);
    const resOilP = +(oilPress - predOilP).toFixed(2);
    const resOilT = +(oilTemp - predOilT).toFixed(1);
    const resFuel = +(fuelFlow - predFuel).toFixed(2);
    const resVib = +(vib - predVib).toFixed(2);

    // M2 Normalization & Composite Score
    const normCht = Math.abs(resCht) / 15.0;
    const normEgt = Math.abs(resEgt) / 35.0;
    const normOilP = Math.abs(resOilP) / 0.8;
    const normOilT = Math.abs(resOilT) / 10.0;
    const normFuel = Math.abs(resFuel) / 2.5;
    const normVib = Math.abs(resVib) / 0.4;
    const normRpm = Math.abs(resRpm) / 120.0;

    const compositeScore = Math.sqrt(
      0.22 * (normOilP ** 2) +
      0.20 * (normCht ** 2) +
      0.18 * (normEgt ** 2) +
      0.16 * (normOilT ** 2) +
      0.14 * (normVib ** 2) +
      0.05 * (normFuel ** 2) +
      0.05 * (normRpm ** 2)
    );

    // M2 Health Index (Exponential decay HI = 100 * exp(-0.5 * D))
    const healthIndex = Math.max(0.0, Math.min(100.0, +(100.0 * Math.exp(-0.5 * compositeScore)).toFixed(1)));

    // ISO Severity
    let severity = 'NORMAL';
    if (healthIndex < 40.0 || compositeScore > 2.5) severity = 'CRITICAL_RTB';
    else if (healthIndex < 65.0 || compositeScore > 1.4) severity = 'WARNING';
    else if (healthIndex < 85.0 || compositeScore > 0.6) severity = 'ADVISORY';

    // RUL with 95% Confidence Interval
    const maxRulMin = missionHours * 60.0;
    let rulEst = maxRulMin;
    let rulLower = maxRulMin * 0.92;
    let rulUpper = maxRulMin * 1.08;

    if (healthIndex < 85.0) {
      const slope = Math.max(0.05, (85.0 - healthIndex) / 12.0);
      const estMin = Math.max(0.0, (healthIndex - 20.0) / slope);
      rulEst = Math.min(maxRulMin, +estMin.toFixed(1));
      const se = Math.max(4.0, rulEst * 0.12);
      rulLower = Math.max(0.0, +(rulEst - 1.96 * se).toFixed(1));
      rulUpper = Math.min(maxRulMin * 1.1, +(rulEst + 1.96 * se).toFixed(1));
    }

    // M4 Isolation Forest & Random Forest multi-class simulation
    let isAnomaly = compositeScore > 0.65;
    let anomalyScore = Math.min(1.0, Math.max(0.0, +(compositeScore / 2.8).toFixed(4)));

    let predictedClass = 'healthy';
    let confidence = 0.95;
    let topFeatures = ['health_index', 'baseline_rul', 'fuel_flow_min_30s'];

    if (oilPress < 2.5 || resOilP < -1.5) {
      isAnomaly = true;
      predictedClass = 'oil_pressure_drop';
      confidence = +(0.88 + Math.random() * 0.08).toFixed(3);
      topFeatures = ['res_oil_p', 'oil_temp_slope_30s', 'health_index'];
    } else if (cht > 200 || resCht > 35) {
      isAnomaly = true;
      predictedClass = 'overheating';
      confidence = +(0.89 + Math.random() * 0.07).toFixed(3);
      topFeatures = ['res_cht', 'egt_mean_30s', 'health_index'];
    } else if (egt > 780 || resEgt > 120) {
      isAnomaly = true;
      predictedClass = 'misfire_or_injector_fault';
      confidence = +(0.86 + Math.random() * 0.08).toFixed(3);
      topFeatures = ['res_egt', 'fuel_flow_min_30s', 'rpm_std_30s'];
    } else if (vib > 2.0 || resVib > 1.2) {
      isAnomaly = true;
      predictedClass = 'vibration_bearing_fault';
      confidence = +(0.91 + Math.random() * 0.06).toFixed(3);
      topFeatures = ['res_vib', 'vibration_std_30s', 'health_index'];
    } else if (oilTemp > 115 || resOilT > 20) {
      isAnomaly = true;
      predictedClass = 'cooling_system_fault';
      confidence = +(0.85 + Math.random() * 0.08).toFixed(3);
      topFeatures = ['res_oil_t', 'cht_slope_30s', 'health_index'];
    } else if (rpm > 2650 || resRpm > 250) {
      isAnomaly = true;
      predictedClass = 'engine_overspeed';
      confidence = +(0.93 + Math.random() * 0.05).toFixed(3);
      topFeatures = ['res_rpm', 'throttle_cmd', 'fuel_flow_max_30s'];
    }

    if (oilPress < 2.2 && (cht > 200 || vib > 2.0)) {
      predictedClass = 'compound_failure';
      confidence = 0.96;
      topFeatures = ['res_oil_p', 'res_cht', 'res_vib'];
    }

    return {
      inputs: probe,
      residuals: { resRpm, resCht, resEgt, resOilP, resOilT, resFuel, resVib },
      compositeScore: +compositeScore.toFixed(4),
      healthIndex,
      severity,
      rul: { est: rulEst, lower: rulLower, upper: rulUpper, status: healthIndex < 85 ? 'estimable' : 'beyond_horizon' },
      ml: {
        isAnomaly,
        anomalyScore,
        predictedClass,
        confidence,
        topFeatures
      }
    };
  }

  getTelemetry() {
    return { ...this.engines[this.activeEngine] };
  }

  getHistory() {
    return { ...this.history };
  }
}

window.TelemetryEngine = TelemetryEngine;
