import argparse
import subprocess
import time

STEPS = [
    ("Data Generation",      "python -m src.data_generator"),
    ("Feature Engineering",  "python -m src.feature_engineering"),
    ("Anomaly Detector",     "python -m src.train_anomaly_detector"),
    ("Fault Classifier",     "python -m src.train_fault_classifier"),
    ("Evaluation",           "python -m src.evaluate"),
]

def run_step(name, cmd):
    print(f"\n{'='*60}\nSTEP: {name}\nCMD:  {cmd}\n{'='*60}")
    t0 = time.time()
    subprocess.run(cmd, shell=True, check=True)
    elapsed = time.time() - t0
    print(f"DONE: {name} ({elapsed:.1f}s)")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-data",  action="store_true")
    parser.add_argument("--skip-train", action="store_true")
    args = parser.parse_args()
    
    for name, cmd in STEPS:
        if args.skip_data and "data_generator" in cmd:
            continue
        if args.skip_train and ("anomaly" in cmd or "classifier" in cmd):
            continue
        run_step(name, cmd)
    print("\nM4 BASELINE PIPELINE COMPLETE")
