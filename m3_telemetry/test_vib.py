import numpy as np

from generator.signal_models import healthy_sample
from generator.fault_injection import VibrationSpikeFault, MisfireFault, FaultManager

duration_s = 10.0
rate_hz = 10
n_steps = int(duration_s * rate_hz)
t_array = np.linspace(0, duration_s, n_steps)

# Scenarios
scenarios = {
    "intermittent": FaultManager([VibrationSpikeFault("intermittent", severity=0.8, start_time_s=1.0, duration_s=8.0)]),
    "sustained": FaultManager([VibrationSpikeFault("sustained", severity=0.8, start_time_s=1.0, duration_s=8.0)]),
    "misfire": FaultManager([MisfireFault(severity=0.8, start_time_s=1.0, duration_s=8.0)]),
}



print(f"{'Time':>5} | {'Intermittent (g)':>16} | {'Sustained (g)':>13} | {'Misfire (g)':>13}")
print("-" * 55)

history = {k: {"vib": [], "rpm": []} for k in scenarios}

for t in t_array:
    row_str = f"{t:5.1f} |"
    for name, mgr in scenarios.items():
        sample = healthy_sample(throttle_pct=75.0)
        faulted = mgr.apply_all(t, sample)
        history[name]["vib"].append(faulted["vibration_g"])
        history[name]["rpm"].append(faulted["rpm"])
        
        if t % 1.0 == 0:
            row_str += f" {faulted['vibration_g']:16.2f} |"
    if t % 1.0 == 0:
        print(row_str)

def sparkline(data, max_val=5.0):
    chars = " .,-~=*#@"
    line = ""
    for v in data:
        idx = int((v / max_val) * (len(chars) - 1))
        idx = max(0, min(len(chars) - 1, idx))
        line += chars[idx]
    return line

print("\n--- Sparklines (Vibration) ---")
for name in scenarios:
    print(f"{name:15}: |{sparkline(history[name]['vib'])}|")

print("\n--- Sparklines (RPM) ---")
for name in scenarios:
    # normalize RPM around ~4458
    # range 4400 to 4500 maps to 0 to 5.0
    rpm_norm = [(r - 4400) / 100 * 5.0 for r in history[name]['rpm']]
    print(f"{name:15}: |{sparkline(rpm_norm)}|")

