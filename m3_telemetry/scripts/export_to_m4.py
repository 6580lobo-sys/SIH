import os
import glob
import pandas as pd

def main():
    # Directories
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(base_dir, "data")
    replay_dir = os.path.join(data_dir, "replay_library")
    demo_dir = os.path.join(data_dir, "demo")
    export_dir = os.path.join(data_dir, "m4_export")

    os.makedirs(export_dir, exist_ok=True)

    # Gather CSV files
    csv_files = glob.glob(os.path.join(replay_dir, "*.csv")) + \
                glob.glob(os.path.join(demo_dir, "*.csv"))
                
    # Filter out manifest.csv
    csv_files = [f for f in csv_files if not f.endswith("manifest.csv")]

    print(f"Found {len(csv_files)} telemetry CSV files.")
    print(f"Exporting to: {export_dir}")

    # The subset of columns M3 provides that match M4's request
    m4_columns = [
        "timestamp", 
        "rpm", 
        "throttle", 
        "oil_pressure", 
        "oil_temp", 
        "cht", 
        "egt", 
        "vibration", 
        "fuel_flow", 
        "fault_type", 
        "fault_active"
    ]

    for file_path in csv_files:
        filename = os.path.basename(file_path)
        
        # Read original CSV
        df = pd.read_csv(file_path)
        
        # Create fault_active (1 if faulted, 0 if healthy)
        # Note: missing values (NaN) in active_faults are treated as empty string "" which != "healthy"
        # However, active_faults should always be "healthy" or the fault name.
        df["active_faults"] = df["active_faults"].fillna("healthy")
        df["fault_active"] = (df["active_faults"] != "healthy").astype(int)
        
        # Create fault_type (map "healthy" to "none")
        df["fault_type"] = df["active_faults"].replace({"healthy": "none"})
        
        # Rename columns to perfectly match M4's expectation
        rename_map = {
            "throttle_cmd": "throttle",
            "vibration_amplitude": "vibration"
        }
        df = df.rename(columns=rename_map)
        
        # Select exactly the columns we mapped
        # Check if all exist, if not, skip this file (e.g., manifest or unknown format)
        if not all(col in df.columns for col in m4_columns):
            print(f"Skipping {filename}: Missing expected columns.")
            continue
            
        export_df = df[m4_columns]
        
        # Save to m4_export
        out_path = os.path.join(export_dir, filename)
        export_df.to_csv(out_path, index=False)
        
    print(f"Export completed. {len(csv_files)} files processed.")

if __name__ == "__main__":
    main()
