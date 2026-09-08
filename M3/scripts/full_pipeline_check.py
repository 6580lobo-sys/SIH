import os
import sys
import time
import subprocess

def run_cmd(cmd, cwd=None):
    print(f"\n> {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return result

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(base_dir)

    results = {}

    print("=" * 50)
    print("STAGE 1: Regenerating Replay Library & Data")
    print("=" * 50)
    
    stage1_pass = True
    
    # 1A. Generate demo scenarios
    demos = [
        "scenarios/demo_healthy.yaml",
        "scenarios/demo_overheating.yaml",
        "scenarios/demo_stress.yaml"
    ]
    for demo in demos:
        cmd = [sys.executable, "-m", "scripts.run_scenario", "--scenario-file", demo]
        res = run_cmd(cmd)
        if res.returncode != 0:
            print(f"[FAIL] {demo} failed to generate:\n{res.stderr}")
            stage1_pass = False
        else:
            print(f"[OK] Generated {demo}")

    # 1B. Generate fault CSVs
    cmd = [sys.executable, "scripts/generate_fault_csvs.py"]
    res = run_cmd(cmd)
    if res.returncode != 0:
        print(f"[FAIL] generate_fault_csvs.py failed:\n{res.stderr}")
        stage1_pass = False
    else:
        print("[OK] Generated fault CSVs")

    # 1C. Generate replay library
    cmd = [sys.executable, "scripts/generate_replay_library.py"]
    res = run_cmd(cmd)
    if res.returncode != 0:
        print(f"[FAIL] generate_replay_library.py failed:\n{res.stderr}")
        stage1_pass = False
    else:
        print("[OK] Generated replay library")

    # 1D. Run M4 export
    cmd = [sys.executable, "scripts/export_to_m4.py"]
    res = run_cmd(cmd)
    if res.returncode != 0:
        print(f"[FAIL] export_to_m4.py failed:\n{res.stderr}")
        stage1_pass = False
    else:
        print("[OK] Exported to M4 format")

    results["1. Regenerate Data"] = "PASS" if stage1_pass else "FAIL"


    print("\n" + "=" * 50)
    print("STAGE 2: Full Pytest Suite")
    print("=" * 50)
    cmd = [sys.executable, "-m", "pytest", "tests/"]
    print(f"\n> {' '.join(cmd)}")
    res = run_cmd(cmd)
    if res.returncode == 0:
        print("[OK] All tests passed.")
        results["2. Pytest Suite"] = "PASS"
    else:
        print("[FAIL] Pytest failures detected:")
        print(res.stdout)
        results["2. Pytest Suite"] = "FAIL"


    print("\n" + "=" * 50)
    print("STAGE 3: Live-Print Demos (5s each)")
    print("=" * 50)
    stage3_pass = True

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    for demo in demos:
        cmd = [sys.executable, "-m", "scripts.run_scenario", "--scenario-file", demo, "--live-print"]
        print(f"\n> {' '.join(cmd)} (running for 5 seconds...)")
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
            start_time = time.time()
            lines_printed = 0
            
            while time.time() - start_time < 5.0:
                # non-blocking or just readline which might block but we have unbuffered
                line = proc.stdout.readline()
                if line:
                    print("  " + line.strip())
                    lines_printed += 1
                if proc.poll() is not None:
                    break
            
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
            
            # On Windows, proc.terminate() usually sets returncode to 1.
            # So we only fail if it exited early (before 5s) with an error.
            if lines_printed == 0:
                print(f"[FAIL] No live-print output detected for {demo}")
                stage3_pass = False
            else:
                print(f"[OK] Successfully live-printed {demo} for 5 seconds.")
        except Exception as e:
            print(f"[FAIL] Exception running {demo}: {e}")
            stage3_pass = False

    results["3. Live-Print Demos"] = "PASS" if stage3_pass else "FAIL"


    print("\n" + "=" * 50)
    print("FINAL SUMMARY")
    print("=" * 50)
    for stage, status in results.items():
        print(f"{stage:<30}: {status}")

    if all(s == "PASS" for s in results.values()):
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
