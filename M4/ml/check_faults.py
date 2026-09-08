import pandas as pd
import glob

missing = []
unique_faults = set()

for f in glob.glob('data/raw/*.csv'):
    try:
        df = pd.read_csv(f)
        if 'fault_type' in df.columns:
            unique_faults.update(df['fault_type'].dropna().unique())
        else:
            missing.append(f)
    except Exception as e:
        print(f"Error reading {f}: {e}")

print("FILES MISSING fault_type COLUMN:")
for m in missing:
    print(m)

print("\nUNIQUE FAULT TYPES:")
for ft in unique_faults:
    print(ft)
