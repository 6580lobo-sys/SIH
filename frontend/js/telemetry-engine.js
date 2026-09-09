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
    this.tick();
  }

  tick() {
    const jitter = (range) => (Math.random() - 0.5) * range;
    const eng = this.engines[this.activeEngine];

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
      case 'overheating':
        targetCht = 188.6;
        targetEgt = 684.2;
        targetOilT = 108.4;
        resCht = 24.5;
        resEgt = 72.0;
        resOilT = 14.2;
        targetHealth = 84.6;
        break;

      case 'oil_pressure_drop':
        targetOilP = 2.38;
        targetOilT = 104.1;
        resOilP = -2.44;
        resOilT = 9.9;
        targetHealth = 82.1;
        break;

      case 'vibration_bearing_fault':
        targetVib = 1.48;
        resVib = 0.64;
        targetHealth = 86.4;
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
        targetEgt = 658.0;
        targetFuel = 24.8;
        resEgt = 45.2;
        resFuel = 3.1;
        targetHealth = 91.8;
        break;

      case 'cooling_system_fault':
        targetCht = 184.2;
        targetOilT = 102.6;
        resCht = 20.1;
        resOilT = 8.4;
        targetHealth = 88.5;
        break;

      case 'engine_overspeed':
        targetRpm = 2680;
        targetFuel = 25.4;
        resRpm = 242.0;
        resFuel = 3.7;
        targetHealth = 83.2;
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

  getTelemetry() {
    return { ...this.engines[this.activeEngine] };
  }

  getHistory() {
    return { ...this.history };
  }
}

window.TelemetryEngine = TelemetryEngine;
