import pandas as pd
import numpy as np

def profile_market_regimes(input_file):
    print(f"Interrogating {input_file}... (Parsing Date Strings)")
    
    chunksize = 1000000
    daily_stats = {}

    for chunk in pd.read_csv(input_file, chunksize=chunksize):
        # 🚨 THE FIX: Convert string timestamps to actual datetime objects
        chunk['timestamp'] = pd.to_datetime(chunk['timestamp'])
        
        # Calculate Mid-Price
        chunk['mid'] = (chunk['bid_price'] + chunk['ask_price']) / 2.0
        
        # Extract just the Date (e.g., '2026-04-14')
        chunk['date_key'] = chunk['timestamp'].dt.date
        
        for date, group in chunk.groupby('date_key'):
            if date not in daily_stats:
                daily_stats[date] = []
            daily_stats[date].extend(group['mid'].tolist())

    print("\n--- MARKET REGIME REPORT ---")
    print(f"{'Date':<15} | {'Volatility (StdDev)':<20} | {'Price Range %':<15}")
    print("-" * 55)

    regimes = []
    for date, prices_list in daily_stats.items():
        prices = np.array(prices_list)
        if len(prices) < 5000: continue # Skip weekends or half-days
        
        vol = np.std(prices)
        price_range = (np.max(prices) - np.min(prices)) / np.min(prices) * 100
        regimes.append({'date': date, 'vol': vol, 'range': price_range})
        print(f"{str(date):<15} | {vol:<20.4f} | {price_range:<15.2f}%")

    # Find the extremes
    meat_grinder = max(regimes, key=lambda x: x['vol'])
    desert = min(regimes, key=lambda x: x['vol'])

    print(f"\n🔥 RECOMMENDATION:")
    print(f"Volatile 'Meat Grinder' Day: {meat_grinder['date']} ({meat_grinder['range']:.2f}% swing)")
    print(f"Quiet 'Desert' Day: {desert['date']} ({desert['range']:.2f}% swing)")
    
    return meat_grinder['date'], desert['date']

# RUN PROFILER
nvda_path = r"C:\Users\PC\Desktop\QuantBacktester\backend_java\backtester\data\NVDA_micro_quotes.csv"
smh_path = r"C:\Users\PC\Desktop\QuantBacktester\backend_java\backtester\data\SMH_micro_quotes.csv"
volatile_date, quiet_date = profile_market_regimes(nvda_path)
volatile_date_smh, quiet_date_smh = profile_market_regimes(smh_path)