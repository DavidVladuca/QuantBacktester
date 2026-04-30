import pandas as pd
import os

def slice_precise_days(input_file, output_file, date_a_str, date_b_str):
    print(f"Slicing {date_a_str} and {date_b_str} from {input_file}...")
    
    # Convert our target string dates into date objects for comparison
    date_a = pd.to_datetime(date_a_str).date()
    date_b = pd.to_datetime(date_b_str).date()
    
    chunksize = 1000000
    selected_chunks = []

    for chunk in pd.read_csv(input_file, chunksize=chunksize):
        chunk['temp_ts'] = pd.to_datetime(chunk['timestamp'])
        mask = chunk['temp_ts'].dt.date.isin([date_a, date_b])
        interesting_data = chunk[mask].copy()
        
        if not interesting_data.empty:
            interesting_data = interesting_data.drop(columns=['temp_ts'])
            selected_chunks.append(interesting_data)

    if selected_chunks:
        final_df = pd.concat(selected_chunks)
        final_df.to_csv(output_file, index=False)
        print(f"✅ Saved precisely sliced data to {output_file}")
    else:
        print("❌ Error: No data found for those dates.")

# File Paths
script_dir = os.path.dirname(os.path.abspath(__file__))
nvda_path = os.path.join(script_dir, "..", "backend_java", "backtester", "data", "NVDA_micro_quotes.csv")
smh_path = os.path.join(script_dir, "..", "backend_java", "backtester", "data", "SMH_micro_quotes.csv")

# We want the generated files to end up in the Java data folder
nvda_out = os.path.join(script_dir, "..", "backend_java", "backtester", "data", "NVDA_micro_2day.csv")
smh_out = os.path.join(script_dir, "..", "backend_java", "backtester", "data", "SMH_micro_2day.csv")

# Run the slicer!
slice_precise_days(nvda_path, nvda_out, "2026-04-14", "2026-04-24")
slice_precise_days(smh_path, smh_out, "2026-04-14", "2026-04-24")