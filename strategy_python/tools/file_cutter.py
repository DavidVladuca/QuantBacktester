import pandas as pd
from pathlib import Path

# file cutter -> cut the first 100k rows of the micro files to speed up testing 
# (only if needed)


# set relative paths
TOOLS_DIR = Path(__file__).resolve().parent
STRATEGY_DIR = TOOLS_DIR.parent
ROOT_DIR = STRATEGY_DIR.parent
DATA_DIR = ROOT_DIR / "backend_java" / "backtester" / "data"
symbols = ["NVDA", "SMH"]
limit = 100000 # read the first 100k rows from each micro file

for symbol in symbols:
    input_path = DATA_DIR / f"{symbol}_micro_quotes.csv"
    output_path = DATA_DIR / f"{symbol}_micro_lab.csv"
    
    if input_path.exists():
        print(f"Cutting {symbol}...")
        df = pd.read_csv(input_path, nrows=limit)
        df.to_csv(output_path, index=False)
        print(f"  (GOOD) Saved {limit} rows to {output_path}")
    else:
        print(f"  (ERROR) Could not find {input_path}")