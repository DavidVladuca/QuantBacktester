import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockQuotesRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.data.enums import DataFeed

# change these to adjust timeframe
BAR_TIMEFRAME_AMOUNT = 5
BAR_TIMEFRAME_UNIT = TimeFrameUnit.Minute
BAR_TIMEFRAME_LABEL = "5min"

def load_config(config_path):
    # parse config file in a dictionary
    config = {}
    if not config_path.exists():
        raise FileNotFoundError(f"(Error) Config file NOT found at: {config_path.absolute()}")
    
    with open(config_path, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                config[key.strip()] = value.strip()
    return config

# path setup
TOOLS_DIR = Path(__file__).resolve().parent
STRATEGY_DIR = TOOLS_DIR.parent
ROOT_DIR = STRATEGY_DIR.parent

CONFIG_PATH = ROOT_DIR / "backend_java" / "backtester" / "config.properties"
TARGET_FOLDER = ROOT_DIR / "backend_java" / "backtester" / "data"

# load config and initialize client
print(f"(Info) Looking for config at: {CONFIG_PATH}")
props = load_config(CONFIG_PATH)

API_KEY = props.get("alpaca.key")
SECRET_KEY = props.get("alpaca.secret")

if not API_KEY or not SECRET_KEY:
    raise ValueError("API Key or Secret missing from config.properties. Check your keys!")

client = StockHistoricalDataClient(API_KEY, SECRET_KEY)

def download_macro_bars(symbols, output_dir, days=90):
    # download macro bars
    print(f"(Downloading) Fetching MACRO BARS for {symbols}...")
    end_time = datetime.now()
    start_time = end_time - timedelta(days=days)
    
    request = StockBarsRequest(
        symbol_or_symbols=symbols,
        timeframe=TimeFrame(BAR_TIMEFRAME_AMOUNT, BAR_TIMEFRAME_UNIT),
        start=start_time,
        end=end_time,
        feed=DataFeed.IEX
    )
    
    bars_df = client.get_stock_bars(request).df
    
    for symbol in symbols:
        df = bars_df.xs(symbol)
        df.index = df.index.strftime('%Y-%m-%d %H:%M:%S')
        
        path = output_dir / f"{symbol}_macro_{BAR_TIMEFRAME_LABEL}.csv"
        df.to_csv(path)
        print(f"(Done) Saved {symbol} Macro Data ({len(df)} rows).")

def download_micro_quotes(symbols, output_dir, days=14):
    """Downloads raw Bid/Ask quotes in daily chunks to prevent MemoryError."""
    print(f"(Downloading) Fetching MICRO (Quotes) for {symbols} in CHUNKS...")
    
    end_all = datetime.now()
    start_all = end_all - timedelta(days=days)

    for symbol in symbols:
        path = os.path.join(output_dir, f"{symbol}_micro_quotes.csv")
        
        # remove old file if it exists to start fresh
        if path.exists():
            path.unlink()
            
        current_start = start_all
        
        # loop through each day individually (to not crash)
        while current_start < end_all:
            current_end = min(current_start + timedelta(days=1), end_all)
            print(f"   -> [{symbol}] Processing: {current_start.strftime('%Y-%m-%d')} to {current_end.strftime('%Y-%m-%d')}")

            try:
                request = StockQuotesRequest(
                    symbol_or_symbols=symbol,
                    start=current_start,
                    end=current_end,
                    feed=DataFeed.IEX
                )
                
                # fetch chunk
                raw_data = client.get_stock_quotes(request)
                if not raw_data.data:
                    current_start = current_end
                    continue

                df = raw_data.df.xs(symbol)
                df = df[['bid_price', 'bid_size', 'ask_price', 'ask_size']]
                df.index = df.index.strftime('%Y-%m-%d %H:%M:%S.%f')

                # append to CSV
                # header=True only if the file doesnt exist yet !!!!
                file_exists = path.is_file()
                df.to_csv(path, mode='a', header=not file_exists)
                
                # force clear memory references
                del df
                del raw_data

            except Exception as e:
                print(f"    Warning: Failed to fetch chunk for {symbol}: {e}")

            current_start = current_end

        print(f"(Done) Completed {symbol} Micro Quote Data.")

if __name__ == "__main__":
    # verify folder exists or create it
    if not TARGET_FOLDER.exists():
        TARGET_FOLDER.mkdir(parents=True)
        print(f"(Info) Created directory: {TARGET_FOLDER}")

    target_pair = ["NVDA", "SMH"]
    
    # get bars
    download_macro_bars(target_pair, TARGET_FOLDER, days=180)
    
    # get raw quotes
    # start with 1 day first to verify file size isn't overwhelming your disk!!!!
    # download_micro_quotes(target_pair, TARGET_FOLDER, days=2)