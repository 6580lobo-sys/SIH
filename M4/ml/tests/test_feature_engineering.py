import os
from pathlib import Path
from src.config import DATA_RAW_DIR, DATA_PROC_DIR

def test_raw_data_exists():
    assert DATA_RAW_DIR.exists(), "Raw data directory should exist"
    csv_files = list(DATA_RAW_DIR.glob("*.csv"))
    assert len(csv_files) > 0, "Raw CSV files should be generated and present"

def test_processed_features_exist():
    assert DATA_PROC_DIR.exists(), "Processed data directory should exist"
    train_file = DATA_PROC_DIR / "features_train.csv"
    val_file = DATA_PROC_DIR / "features_val.csv"
    test_file = DATA_PROC_DIR / "features_test.csv"
    
    assert train_file.exists(), f"{train_file} should exist"
    assert val_file.exists(), f"{val_file} should exist"
    assert test_file.exists(), f"{test_file} should exist"
