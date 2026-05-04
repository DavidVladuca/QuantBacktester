import pandas as pd
import numpy as np
from pathlib import Path

def profile_market_regimes(input_file):
    print(f"Interrogating {input_file} for Best Days...")
    
    chunksize = 1000000
    daily_stats = {}

    for chunk in pd.read_csv(input_file, chunksize=chunksize):
        chunk['timestamp'] = pd.to_datetime(chunk['timestamp'])
        
        # macro files use close as the main price
        chunk['mid'] = chunk['close']
            
        chunk['date_key'] = chunk['timestamp'].dt.date
        
        for date, group in chunk.groupby('date_key'):
            if date not in daily_stats:
                daily_stats[date] = []
            daily_stats[date].extend(group['mid'].tolist())

    print("\n--- MARKET REGIME REPORT ---")
    print(f"{'Date':<15} | {'Vol (Returns %)':<15} | {'Range %':<10} | {'Directional Move %':<15}")
    print("-" * 65)

    regimes = []

    for date, prices_list in daily_stats.items():
        prices = np.array(prices_list)

        # 5-minute regular trading day usually has around 78 bars
        if len(prices) < 50:
            continue
        
        returns = np.diff(np.log(prices))
        vol = np.std(returns) * 100
        
        price_range = (np.max(prices) - np.min(prices)) / np.min(prices) * 100
        
        open_price = prices[0]
        close_price = prices[-1]
        directional_move = abs(close_price - open_price) / open_price * 100
        
        regimes.append({
            'date': date, 
            'vol': vol, 
            'range': price_range,
            'trend': directional_move
        })

        print(f"{str(date):<15} | {vol:<15.4f} | {price_range:<10.2f}% | {directional_move:<15.2f}%")

    if not regimes:
        print("\n(ERROR) No valid full trading days found.")
        return []

    big_chop = max(regimes, key=lambda x: x['vol'])
    chill_day = min(regimes, key=lambda x: x['vol'])
    trend_day = max(regimes, key=lambda x: x['trend'])

    print(f"\n THE 3 REPRESENTATIVE DAYS:")
    print(f"1. Highest Chop: {big_chop['date']} (Vol: {big_chop['vol']:.4f}%)")
    print(f"2. Quietest Day: {chill_day['date']} (Vol: {chill_day['vol']:.4f}%)")
    print(f"3. Cleanest Directional Move: {trend_day['date']} (Move: {trend_day['trend']:.2f}%)")
    
    return [str(big_chop['date']), str(chill_day['date']), str(trend_day['date'])]

if __name__ == "__main__":
    TOOLS_DIR = Path(__file__).resolve().parent
    STRATEGY_DIR = TOOLS_DIR.parent
    ROOT_DIR = STRATEGY_DIR.parent
    DATA_DIR = ROOT_DIR / "backend_java" / "backtester" / "data"

    nvda_path = DATA_DIR / "NVDA_macro_5min.csv"

    magic_dates = profile_market_regimes(nvda_path)
    print(f"\n => COPY THESE DATES INTO YOUR SLICER: {magic_dates}")