import numpy as np
import pandas as pd
import joblib
from sklearn.preprocessing import StandardScaler
from pathlib import Path
from src.config import *

def load_and_merge_csv(filepath):
    df = pd.read_csv(filepath)
    return df

def clean_dataframe(df):
    df = df.ffill().bfill()
    for col in SENSOR_COLS:
        min_val, max_val = NORMAL_RANGES[col]
        width = max_val - min_val
        df[col] = df[col].clip(min_val - 3*width, max_val + 3*width)
    df = df.sort_values(by="timestamp", ascending=True).reset_index(drop=True)
    return df

def encode_mission_phase(df):
    for phase in MISSION_PHASES:
        df[f"mission_phase_{phase}"] = (df["mission_phase"] == phase).astype(int)
    df = df.drop(columns=["mission_phase"])
    return df

def compute_rolling_features(df, window=WINDOW_SIZE):
    cols_to_roll = [c for c in SENSOR_COLS + RESIDUAL_COLS if c not in ["health_index", "baseline_rul"]]
    rolled = df[cols_to_roll].rolling(window=window, min_periods=1)
    
    df_mean = rolled.mean().add_suffix(f'_mean_{window}s')
    df_std = rolled.std().fillna(0).add_suffix(f'_std_{window}s')
    df_min = rolled.min().add_suffix(f'_min_{window}s')
    df_max = rolled.max().add_suffix(f'_max_{window}s')
    df_last = df[cols_to_roll].add_suffix('_last')
    
    df = pd.concat([df, df_mean, df_std, df_min, df_max, df_last], axis=1)
    return df

def compute_slope_features(df, window=WINDOW_SIZE):
    for col in SLOPE_COLS:
        if col in df.columns:
            df[f"{col}_slope_{window}s"] = df[col].rolling(window=window, min_periods=1).apply(
                lambda x: np.polyfit(np.arange(len(x)), x, 1)[0] if len(x) > 1 else 0.0,
                raw=True
            )
    return df

def create_labels(df):
    df["label_anomaly"] = df["fault_active"].astype(int)
    df["label_fault_int"] = df["fault_type"].map(FAULT_TYPE_TO_INT)
    return df

def drop_warmup_rows(df, window=WINDOW_SIZE):
    return df.iloc[window:].reset_index(drop=True)

def get_feature_columns(df):
    exclude = ["timestamp", "fault_type", "fault_active", "fault_severity",
               "fault_start_time", "fault_end_time", "label_anomaly", "label_fault_int", "run_id"]
    return [c for c in df.columns if c not in exclude]

def build_feature_matrix(csv_paths):
    frames = []
    for i, csv_path in enumerate(csv_paths):
        df = load_and_merge_csv(csv_path)
        df = clean_dataframe(df)
        df = encode_mission_phase(df)
        df = compute_rolling_features(df)
        df = compute_slope_features(df)
        df = create_labels(df)
        df = drop_warmup_rows(df)
        df["run_id"] = i
        frames.append(df)
        
    combined = pd.concat(frames, ignore_index=True)
    feature_names = get_feature_columns(combined)
    
    return {
        "X": combined[feature_names].values,
        "y_anomaly": combined["label_anomaly"].values,
        "y_fault": combined["label_fault_int"].values,
        "run_ids": combined["run_id"].values,
        "feature_names": feature_names,
        "combined_df": combined
    }

def split_by_run(data_dict, healthy_csvs, fault_csvs, all_csvs):
    df = data_dict["combined_df"]
    
    train_runs = []
    val_runs = []
    test_runs = []
    
    # Healthy runs: 01, 02 -> train, 03 -> val
    for i, f in enumerate(all_csvs):
        if "healthy" in f.name:
            if "01" in f.name or "02" in f.name:
                train_runs.append(i)
            elif "03" in f.name:
                val_runs.append(i)
        else:
            if "01" in f.name:
                train_runs.append(i)
            elif "02" in f.name:
                val_runs.append(i)

    # Some faults might only have 01.csv. Split the 01 run 70/15/15 if no 02 exists? 
    # Or just use the run splitting. To be simple, we just use random split for test set from train runs for faults if needed.
    # Actually, the instructions say: 
    # "Fault runs: _01.csv -> train (70%), _02.csv -> val, else val from same run last 15%"
    
    train_frames = []
    val_frames = []
    test_frames = []
    
    feature_names = data_dict["feature_names"]
    
    for i in train_runs:
        run_df = df[df["run_id"] == i]
        n = len(run_df)
        # If it's a fault run and there is no corresponding 02 run, we need to split it
        fname = all_csvs[i].name
        if "healthy" not in fname:
            # check if 02 exists
            has_02 = any(f.name == fname.replace("01", "02") for f in all_csvs)
            if not has_02:
                train_frames.append(run_df.iloc[:int(n*0.7)])
                val_frames.append(run_df.iloc[int(n*0.7):int(n*0.85)])
                test_frames.append(run_df.iloc[int(n*0.85):])
            else:
                train_frames.append(run_df.iloc[:int(n*0.85)])
                test_frames.append(run_df.iloc[int(n*0.85):])
        else:
            train_frames.append(run_df.iloc[:int(n*0.85)])
            test_frames.append(run_df.iloc[int(n*0.85):])
            
    for i in val_runs:
        run_df = df[df["run_id"] == i]
        n = len(run_df)
        val_frames.append(run_df.iloc[:int(n*0.5)])
        test_frames.append(run_df.iloc[int(n*0.5):])
        
    train_df = pd.concat(train_frames)
    val_df = pd.concat(val_frames)
    test_df = pd.concat(test_frames)
    
    return {
        "X_train": train_df[feature_names].values,
        "X_val": val_df[feature_names].values,
        "X_test": test_df[feature_names].values,
        "y_train_anomaly": train_df["label_anomaly"].values,
        "y_val_anomaly": val_df["label_anomaly"].values,
        "y_test_anomaly": test_df["label_anomaly"].values,
        "y_train_fault": train_df["label_fault_int"].values,
        "y_val_fault": val_df["label_fault_int"].values,
        "y_test_fault": test_df["label_fault_int"].values,
        "feature_names": feature_names
    }

def fit_and_save_scaler(X_train, feature_names):
    scaler = StandardScaler()
    scaler.fit(X_train)
    joblib.dump(scaler, SCALER_PATH)
    return scaler

def save_processed_splits(splits_dict):
    for split in ["train", "val", "test"]:
        X = splits_dict[f"X_{split}"]
        df = pd.DataFrame(X, columns=splits_dict["feature_names"])
        df["label_anomaly"] = splits_dict[f"y_{split}_anomaly"]
        df["label_fault_int"] = splits_dict[f"y_{split}_fault"]
        df.to_csv(DATA_PROC_DIR / f"features_{split}.csv", index=False)

if __name__ == "__main__":
    all_csvs = [f for f in sorted(DATA_RAW_DIR.glob("*.csv")) if not f.name.startswith("my_custom_test")]
    healthy_csvs = [f for f in all_csvs if "healthy" in f.name]
    fault_csvs   = [f for f in all_csvs if "healthy" not in f.name]
    
    data_dict = build_feature_matrix(all_csvs)
    splits    = split_by_run(data_dict, healthy_csvs, fault_csvs, all_csvs)
    scaler    = fit_and_save_scaler(splits["X_train"], data_dict["feature_names"])
    save_processed_splits(splits)
    
    print(f"Feature engineering complete. Feature count: {len(data_dict['feature_names'])}")
    print(f"Train: {splits['X_train'].shape}, Val: {splits['X_val'].shape}, Test: {splits['X_test'].shape}")
