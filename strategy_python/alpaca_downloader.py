import os
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockQuotesRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.data.enums import DataFeed

def load_config(config_path):
    """Parses Java-style .properties file into a dictionary."""
    config = {}
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"❌ Config file NOT found at: {os.path.abspath(config_path)}")
    
    with open(config_path, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                config[key.strip()] = value.strip()
    return config

# --- PATH LOGIC ---
# __file__ is strategy_python/alpaca_downloader.py
# .parent is strategy_python/
# .parent.parent is the root directory
ROOT_DIR = Path(__file__).parent.parent
CONFIG_PATH = ROOT_DIR / "backend_java" / "backtester" / "config.properties"
TARGET_FOLDER = ROOT_DIR / "backend_java" / "backtester" / "data"

# 1. LOAD CREDENTIALS
print(f"🔍 Looking for config at: {CONFIG_PATH}")
props = load_config(CONFIG_PATH)

API_KEY = props.get("alpaca.key")
SECRET_KEY = props.get("alpaca.secret")

if not API_KEY or not SECRET_KEY:
    raise ValueError("API Key or Secret missing from config.properties. Check your keys!")

client = StockHistoricalDataClient(API_KEY, SECRET_KEY)

def download_macro_bars(symbols, output_dir, days=90):
    """Downloads 1-minute bars for Z-Score and Momentum calculations."""
    print(f"📥 Fetching MACRO (1m Bars) for {symbols}...")
    end_time = datetime.now()
    start_time = end_time - timedelta(days=days)
    
    request = StockBarsRequest(
        symbol_or_symbols=symbols,
        timeframe=TimeFrame(1, TimeFrameUnit.Minute),
        start=start_time,
        end=end_time,
        feed=DataFeed.IEX
    )
    
    bars_df = client.get_stock_bars(request).df
    
    for symbol in symbols:
        df = bars_df.xs(symbol)
        df.index = df.index.strftime('%Y-%m-%d %H:%M:%S')
        
        path = os.path.join(output_dir, f"{symbol}_macro_1min.csv")
        df.to_csv(path)
        print(f"✅ Saved {symbol} Macro Data ({len(df)} rows).")

def download_micro_quotes(symbols, output_dir, days=14):
    """Downloads raw Bid/Ask quotes in daily chunks to prevent MemoryError."""
    print(f"📥 Fetching MICRO (Quotes) for {symbols} in CHUNKS...")
    
    end_all = datetime.now()
    start_all = end_all - timedelta(days=days)

    for symbol in symbols:
        path = os.path.join(output_dir, f"{symbol}_micro_quotes.csv")
        
        # Remove old file if it exists to start fresh
        if os.path.exists(path):
            os.remove(path)
            
        current_start = start_all
        
        # Loop through each day individually
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
                
                # Fetch chunk
                raw_data = client.get_stock_quotes(request)
                if not raw_data.data:
                    current_start = current_end
                    continue

                df = raw_data.df.xs(symbol)
                df = df[['bid_price', 'bid_size', 'ask_price', 'ask_size']]
                df.index = df.index.strftime('%Y-%m-%d %H:%M:%S.%f')

                # Append to CSV: 
                # header=True only if the file doesn't exist yet
                file_exists = os.path.isfile(path)
                df.to_csv(path, mode='a', header=not file_exists)
                
                # Force clear memory references
                del df
                del raw_data

            except Exception as e:
                print(f"   ⚠️ Warning: Failed to fetch chunk for {symbol}: {e}")

            current_start = current_end

        print(f"✅ Completed {symbol} Micro Quote Data.")

if __name__ == "__main__":
    # Ensure the data folder exists
    if not os.path.exists(TARGET_FOLDER):
        os.makedirs(TARGET_FOLDER)
        print(f"📁 Created directory: {TARGET_FOLDER}")

    target_pair = ["NVDA", "SMH"]
    
    # 1. Get the 'Map' (1-minute bars)
    download_macro_bars(target_pair, TARGET_FOLDER, days=90)
    
    # 2. Get the 'Trigger' (Raw quotes)
    # Start with 1 day first to verify file size isn't overwhelming your disk
    download_micro_quotes(target_pair, TARGET_FOLDER, days=14)