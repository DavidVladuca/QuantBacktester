import csv
import itertools
import statistics

# grid search parameter ranges
FAST_MA_RANGE = range(3, 11)         
SLOW_MA_RANGE = range(15, 31, 5)      
TRAILING_STOP_RANGE = [0.05, 0.10, 0.15, 0.20, 0.25] 

def load_data(filepath):
    data = []
    with open(filepath, 'r') as file:
        reader = csv.reader(file)
        next(reader) # skip header
        next(reader) # skip sub-header
        for row in reader:
            data.append({"date": row[0], "price": float(row[1])})
    return data

def simulate(data, fast_window, slow_window, trailing_stop_pct):
    cash = 10000.0
    shares = 0
    in_position = False
    entry_price = 0.0
    high_water_mark = 0.0
    
    price_history = []
    prev_fast_sma = None
    prev_slow_sma = None

    for event in data:
        price = event["price"]
        price_history.append(price)

        if len(price_history) >= slow_window:
            # the current window of prices
            window_data = price_history[-slow_window:]
            
            slow_sma = sum(window_data) / slow_window
            fast_sma = sum(window_data[-fast_window:]) / fast_window

            # dynamic sizing math
            if len(window_data) > 1:
                stdev = statistics.stdev(window_data)
            else:
                stdev = 0
            
            if price > 0:
                volatility_pct = stdev / price
            else:
                volatility_pct = 0.01 # avoid division by zero

            if volatility_pct > 0:
                dynamic_alloc = 0.02 / volatility_pct
            else:
                dynamic_alloc = 1.0
    
            buy_allocation = max(0.1, min(1.0, dynamic_alloc))

            # if we have shares
            if in_position:
                if price > high_water_mark:
                    high_water_mark = price
                
                trailing_stop_price = high_water_mark * (1.0 - trailing_stop_pct)
                
                # exit 
                if price <= trailing_stop_price or (prev_fast_sma is not None and fast_sma < slow_sma and prev_fast_sma >= prev_slow_sma):
                    # SELL
                    revenue = shares * price
                    cash += revenue
                    shares = 0
                    in_position = False
                    high_water_mark = 0.0
            else:
                # entry 
                if prev_fast_sma is not None and prev_slow_sma is not None:
                    if fast_sma > slow_sma and prev_fast_sma <= prev_slow_sma:
                        # BUY
                        capital_to_deploy = cash * buy_allocation
                        shares_to_buy = int(capital_to_deploy / price)
                        if shares_to_buy > 0:
                            cost = shares_to_buy * price
                            cash -= cost
                            shares += shares_to_buy
                            in_position = True
                            entry_price = price
                            high_water_mark = price

            prev_fast_sma = fast_sma
            prev_slow_sma = slow_sma

    # final portfolio value
    final_price = data[len(data) - 1]["price"]
    final_value = cash + (shares * final_price)
    return_pct = ((final_value - 10000.0) / 10000.0) * 100
    return return_pct

def main():
    filepath = "../backend_java/backtester/data/AAPL_Daily_5years.csv"
    
    print("Loading data into memory...")
    try:
        data = load_data(filepath)
    except FileNotFoundError:
        print(f"Error: Could not find {filepath}.")
        return

    print("Data loaded. Starting Grid Search...")
    
    # generate all possible combinations of parameters
    combinations = list(itertools.product(FAST_MA_RANGE, SLOW_MA_RANGE, TRAILING_STOP_RANGE))
    total_runs = len(combinations)
    
    results = []
    
    for i, (fast, slow, ts) in enumerate(combinations):
        if fast >= slow:
            continue # skip invalid combinations 
            
        ret = simulate(data, fast, slow, ts)
        results.append({
            "fast": fast,
            "slow": slow,
            "ts": ts,
            "return": ret
        })
        
        # progress tracker
        if i % 20 == 0:
            print(f"Progress: {i}/{total_runs} simulations complete...")

    # sort results by return 
    results.sort(key=lambda x: x["return"], reverse=True)

    print("\n=== OPTIMIZATION COMPLETE ===")
    print("TOP 3 CONFIGURATIONS FOR AAPL:")
    for i in range(3):
        res = results[i]
        print(f"Rank {i+1}: FAST_WINDOW: {res['fast']} | SLOW_WINDOW: {res['slow']} | Trailing Stop: {res['ts']*100:.0f}% => Return: {res['return']:.2f}%")

if __name__ == "__main__":
    main()