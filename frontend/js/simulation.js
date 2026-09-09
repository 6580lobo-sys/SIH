/**
 * THERMODYNAMIC MISSION SIMULATION WORKSPACE
 * Simulates aero-piston performance across operational envelopes (density altitude, ISA deviations,
 * throttle mapping, and heat dissipation).
 */

class SimulationWorkspace {
  constructor(canvasId) {
    this.canvasId = canvasId;

    // Simulation parameters
    this.params = {
      altitude: 18500, // ft
      temp: 31,       // °C ambient
      throttle: 67,   // %
      load: 74,       // %
      duration: 6.0,  // hours
      fuelOctane: 100 // RON
    };

    this.presets = {
      'high-alt': {
        name: 'High Altitude ISR',
        altitude: 26000,
        temp: -32,
        throttle: 78,
        load: 82,
        duration: 8.0,
        fuelOctane: 100
      },
      'endurance': {
        name: 'Max Endurance Loiter',
        altitude: 16000,
        temp: -12,
        throttle: 52,
        load: 58,
        duration: 14.0,
        fuelOctane: 100
      },
      'hot-weather': {
        name: 'Hot Weather Low-Level',
        altitude: 1500,
        temp: 46,
        throttle: 85,
        load: 89,
        duration: 3.5,
        fuelOctane: 98
      },
      'rapid-trans': {
        name: 'Rapid Throttle Transition',
        altitude: 8000,
        temp: 18,
        throttle: 96,
        load: 95,
        duration: 2.0,
        fuelOctane: 100
      }
    };

    this.init();
  }

  init() {
    this.bindInputs();
    this.runSimulation();
  }

  bindInputs() {
    const bindSlider = (id, key, suffix = '') => {
      const slider = document.getElementById(id);
      const readout = document.getElementById(`${id}-val`);
      if (slider && readout) {
        slider.value = this.params[key];
        readout.textContent = `${this.params[key]}${suffix}`;
        slider.addEventListener('input', (e) => {
          this.params[key] = parseFloat(e.target.value);
          readout.textContent = `${this.params[key]}${suffix}`;
          this.runSimulation();
        });
      }
    };

    bindSlider('sim-slider-alt', 'altitude', ' ft');
    bindSlider('sim-slider-temp', 'temp', ' °C');
    bindSlider('sim-slider-throttle', 'throttle', '%');
    bindSlider('sim-slider-load', 'load', '%');
    bindSlider('sim-slider-duration', 'duration', ' h');

    // Preset buttons
    document.querySelectorAll('.sim-preset-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const presetKey = e.currentTarget.getAttribute('data-preset');
        if (this.presets[presetKey]) {
          this.loadPreset(this.presets[presetKey]);
        }
      });
    });
  }

  loadPreset(preset) {
    this.params = { ...preset };
    
    // Update inputs
    const setVal = (id, val, suffix) => {
      const slider = document.getElementById(id);
      const readout = document.getElementById(`${id}-val`);
      if (slider) slider.value = val;
      if (readout) readout.textContent = `${val}${suffix}`;
    };

    setVal('sim-slider-alt', this.params.altitude, ' ft');
    setVal('sim-slider-temp', this.params.temp, ' °C');
    setVal('sim-slider-throttle', this.params.throttle, '%');
    setVal('sim-slider-load', this.params.load, '%');
    setVal('sim-slider-duration', this.params.duration, ' h');

    this.runSimulation();
  }

  runSimulation() {
    // Realistic aero-piston thermodynamic equations
    const altRatio = this.params.altitude / 30000;
    const densityRatio = Math.max(0.35, 1 - (altRatio * 0.65));
    
    // Predicted RPM with turbo-wastegate compensation
    const predRpm = Math.round(1800 + (this.params.throttle / 100) * 850 - (altRatio * 60));
    
    // Predicted EGT: increases with throttle, ambient heat, and lean mixture at high altitude
    const predEgt = Math.round(520 + (this.params.throttle * 1.3) + (this.params.temp * 0.9) + (altRatio * 35));
    
    // Predicted CHT: affected by cooling airflow and ambient temperature
    const predCht = +(140 + (this.params.load * 0.35) + (this.params.temp * 0.45)).toFixed(1);
    
    // Predicted Oil Temperature
    const predOilTemp = +(80 + (this.params.load * 0.22) + (this.params.temp * 0.25)).toFixed(1);
    
    // Predicted Fuel Flow (Liters per hour)
    const predFuelFlow = +(12.0 + (this.params.throttle * 0.16) * (1 / Math.sqrt(densityRatio))).toFixed(1);
    
    // Predicted Engine Mechanical Load %
    const predLoad = Math.min(100, Math.round(this.params.load * (0.95 + (this.params.temp > 35 ? 0.05 : 0))));

    // Update readouts in DOM
    const update = (id, text) => {
      const el = document.getElementById(id);
      if (el) el.textContent = text;
    };

    update('sim-out-rpm', `${predRpm} RPM`);
    update('sim-out-egt', `${predEgt} °C`);
    update('sim-out-cht', `${predCht} °C`);
    update('sim-out-oiltemp', `${predOilTemp} °C`);
    update('sim-out-fuelflow', `${predFuelFlow} L/hr`);
    update('sim-out-load', `${predLoad} %`);

    // Draw simulation comparison chart
    if (window.AeroCharts) {
      window.AeroCharts.drawSimulationComparison(
        this.canvasId,
        this.params.altitude,
        this.params.throttle,
        this.params.temp
      );
    }
  }
}

window.SimulationWorkspace = SimulationWorkspace;
