import pandas as pd
import numpy as np
import os

def profile_market_regimes(input_file):
    print(f"Interrogating {input_file} for Best Days...")
    
    chunksize = 1000000
    daily_stats = {}

    for chunk in pd.read_csv(input_file, chunksize=chunksize):
        chunk['timestamp'] = pd.to_datetime(chunk['timestamp'])
        
        # find if macro or micro (look at book columns)
        if 'bid_price' in chunk.columns:
            chunk['mid'] = (chunk['bid_price'] + chunk['ask_price']) / 2.0
        else:
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
        if len(prices) < 3000: continue # skip weekends/short days
        
        returns = np.diff(np.log(prices))
        vol = np.std(returns) * 100  # convert to percentage
        
        price_range = (np.max(prices) - np.min(prices)) / np.min(prices) * 100
        
        # trend (close vs open)
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

    # find 3 representative days
    big_chop = max(regimes, key=lambda x: x['vol']) # Highest Chop
    chill_day = min(regimes, key=lambda x: x['vol']) # Quietest Day
    trend_day = max(regimes, key=lambda x: x['trend']) # Cleanest Directional Move

    print(f"\n THE 3 REPRESENTATIVE DAYS:")
    print(f"1. Highest Chop: {big_chop['date']} (Vol: {big_chop['vol']:.4f}%)")
    print(f"2. Quietest Day:      {chill_day['date']} (Vol: {chill_day['vol']:.4f}%)")
    print(f"3. Cleanest Directional Move:     {trend_day['date']} (Move: {trend_day['trend']:.2f}%)")
    
    return [str(big_chop['date']), str(chill_day['date']), str(trend_day['date'])]

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))

    nvda_path = os.path.join(script_dir, "..", "backend_java", "backtester", "data", "NVDA_micro_quotes.csv")
    
    magic_dates = profile_market_regimes(nvda_path)
    print(f"\n => COPY THESE DATES INTO YOUR SLICER: {magic_dates}")