import pandas as pd
import os

# file cutter -> cut the first 100k rows of the micro files to speed up testing 
# (only if needed)


# set relative paths
DATA_DIR = os.path.join("..", "backend_java", "backtester", "data")
symbols = ["NVDA", "SMH"]
limit = 100000 # read the first 100k rows from each micro file

for symbol in symbols:
    input_path = os.path.join(DATA_DIR, f"{symbol}_micro_quotes.csv")
    output_path = os.path.join(DATA_DIR, f"{symbol}_micro_lab.csv")
    
    if os.path.exists(input_path):
        print(f"Cutting {symbol}...")
        df = pd.read_csv(input_path, nrows=limit)
        df.to_csv(output_path, index=False)
        print(f"  (GOOD) Saved {limit} rows to {output_path}")
    else:
        print(f"  (ERROR) Could not find {input_path}")