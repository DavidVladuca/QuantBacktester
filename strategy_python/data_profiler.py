import pandas as pd
import numpy as np
import os

def profile_market_regimes(input_file):
    print(f"Interrogating {input_file} for Goldilocks Days...")
    
    chunksize = 1000000
    daily_stats = {}

    for chunk in pd.read_csv(input_file, chunksize=chunksize):
        chunk['timestamp'] = pd.to_datetime(chunk['timestamp'])
        
        # Determine if Macro or Micro file based on columns
        if 'bid_price' in chunk.columns:
            chunk['mid'] = (chunk['bid_price'] + chunk['ask_price']) / 2.0
        else:
            chunk['mid'] = chunk['close'] # Fallback for macro
            
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
        if len(prices) < 3000: continue # Skip weekends/short days
        
        # 🚨 THE FINAL FIX: Log Returns Volatility
        # This perfectly aligns the profiler with the trading bot's math.
        returns = np.diff(np.log(prices))
        vol = np.std(returns) * 100  # Converted to % to match your config thresholds
        
        price_range = (np.max(prices) - np.min(prices)) / np.min(prices) * 100
        
        # Directional trend (Close vs Open)
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

    # Find the 3 Archetypes
    meat_grinder = max(regimes, key=lambda x: x['vol'])    # Highest Chop
    desert = min(regimes, key=lambda x: x['vol'])          # Quietest Day
    trend_day = max(regimes, key=lambda x: x['trend'])     # Cleanest Directional Move

    print(f"\n🔥 THE 3 REPRESENTATIVE DAYS:")
    print(f"1. Meat Grinder (Chop): {meat_grinder['date']} (Vol: {meat_grinder['vol']:.4f}%)")
    print(f"2. Desert (Quiet):      {desert['date']} (Vol: {desert['vol']:.4f}%)")
    print(f"3. Trend Day (Run):     {trend_day['date']} (Move: {trend_day['trend']:.2f}%)")
    
    return [str(meat_grinder['date']), str(desert['date']), str(trend_day['date'])]

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Profile NVDA to set the baseline dates for everything
    nvda_path = os.path.join(script_dir, "..", "backend_java", "backtester", "data", "NVDA_micro_quotes.csv")
    
    magic_dates = profile_market_regimes(nvda_path)
    print(f"\n👉 COPY THESE DATES INTO YOUR SLICER: {magic_dates}")