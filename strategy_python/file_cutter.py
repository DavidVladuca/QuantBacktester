import pandas as pd
import os

# Set the relative path to your data folder
DATA_DIR = os.path.join("..", "backend_java", "backtester", "data")
symbols = ["NVDA", "SMH"]
limit = 100000

for symbol in symbols:
    input_path = os.path.join(DATA_DIR, f"{symbol}_micro_quotes.csv")
    output_path = os.path.join(DATA_DIR, f"{symbol}_micro_lab.csv")
    
    if os.path.exists(input_path):
        print(f"✂️ Truncating {symbol}...")
        # Read the first 100k rows
        df = pd.read_csv(input_path, nrows=limit)
        df.to_csv(output_path, index=False)
        print(f"✅ Saved {limit} rows to {output_path}")
    else:
        print(f"❌ Error: Could not find {input_path}")