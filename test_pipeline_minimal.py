from run_e2e_pipeline import run_e2e_pipeline
import pandas as pd
from pathlib import Path

def test_minimal():
    print("\n>>> STARTING MINIMAL PIPELINE TEST <<<")
    
    # Run pipeline for only 1 session, year 2024 (stable data)
    # This will test Crawl -> Consolidate -> Clean -> Build
    run_e2e_pipeline(year=2024, limit=1)
    
    # Check if final dataset exists
    output_path = Path("data/processed/driver_session_base.csv")
    if output_path.exists():
        print(f"\n[SUCCESS] Final dataset created at: {output_path}")
        df = pd.read_csv(output_path)
        print(f"[INFO] Dataset shape: {df.shape}")
        print("\n--- Sample Data (First 5 rows) ---")
        print(df.head())
    else:
        print("\n[FAILED] Final dataset was not created. Check logs above.")

if __name__ == "__main__":
    test_minimal()
