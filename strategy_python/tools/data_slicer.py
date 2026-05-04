import pandas as pd
from pathlib import Path

def slice_stress_test_data(input_file, output_file, target_dates_str):
    print(f"Slicing {input_file}...")
    
    # convert string dates to datetime objects
    target_dates = [pd.to_datetime(d).date() for d in target_dates_str]
    
    chunksize = 1000000
    selected_chunks = []

    try:
        for chunk in pd.read_csv(input_file, chunksize=chunksize):
            chunk['temp_ts'] = pd.to_datetime(chunk['timestamp'])
            mask = chunk['temp_ts'].dt.date.isin(target_dates)
            interesting_data = chunk[mask].copy()
            
            if not interesting_data.empty:
                interesting_data = interesting_data.drop(columns=['temp_ts'])
                selected_chunks.append(interesting_data)

        if selected_chunks:
            final_df = pd.concat(selected_chunks)
            # sort chronologically just to be safe
            final_df = final_df.sort_values(by='timestamp')
            final_df.to_csv(output_file, index=False)
            print(f"  (GOOD) Saved {len(final_df)} rows to {Path(output_file).name}")
        else:
            print(f"  (ERROR) No data found for those dates in {input_file}.")
    except Exception as e:
        print(f"  (ERROR) Failed processing {input_file}: {e}")

if __name__ == "__main__":
    # !!! PASTE THE 3 MAGIC DATES FROM THE DATA PROFILER HERE !!!
    target_dates = ["2026-04-16", "2026-04-17", "2026-04-20"]

    TOOLS_DIR = Path(__file__).resolve().parent
    STRATEGY_DIR = TOOLS_DIR.parent
    ROOT_DIR = STRATEGY_DIR.parent
    data_dir = ROOT_DIR / "backend_java" / "backtester" / "data"

    # define the files to slice (input, output)
    files_to_slice = [
        ("NVDA_macro_5min.csv", "NVDA_macro_stress.csv"),
        ("SMH_macro_5min.csv", "SMH_macro_stress.csv")
    ]

    print(f" Starting Master Slicer for dates: {target_dates}\n")
    for input_name, output_name in files_to_slice:
        in_path = data_dir / input_name
        out_path = data_dir / output_name
        slice_stress_test_data(in_path, out_path, target_dates)
        
    print("\n => Stress test files generated successfully!")