import json
import numpy as np
from collections import deque

class BollingerStrategy:
    def __init__(self, period=20, std_dev_multiplier=2.0, target_vol=0.02): # removed stop_loss_pct # new
        self.period = period
        self.std_dev_multiplier = std_dev_multiplier
        self.target_vol = target_vol
        
        self.prices = deque(maxlen=self.period)
        
        # removed internal position/risk states # new

    def calculate_vol_allocation(self):
        if len(self.prices) < self.period:
            return 0.0
            
        prices_window = list(self.prices)
        returns = np.diff(prices_window) / prices_window[:-1]   
        
        daily_vol = np.std(returns)
        
        if daily_vol == 0:
            return 1.0 
            
        dynamic_alloc = self.target_vol / daily_vol 
        return min(1.0, dynamic_alloc) 

    def process_event(self, event):
        
        if event.get("type") != "MARKET_DATA":
            return None

        symbol = event["symbol"]
        timestamp = event["timestamp"]
        price = event["price"]

        self.prices.append(price)

        signal = "HOLD"
        allocation = 0.0

        if len(self.prices) == self.period:
            prices_array = np.array(self.prices)
            sma = np.mean(prices_array)
            std_dev = np.std(prices_array)
            
            upper_band = sma + (std_dev * self.std_dev_multiplier)
            lower_band = sma - (std_dev * self.std_dev_multiplier)

            dynamic_alloc = self.calculate_vol_allocation()

            # Continuous Bollinger Band Stances # new
            # price is unusually low -> expect it to bounce back
            if price < lower_band: # new
                signal = "BUY"
                allocation = dynamic_alloc

            # price is unusually high -> expect it to fall back
            elif price > upper_band: # new
                signal = "SELL"
                allocation = 1.0 # new

        if signal == "BUY":
            final_allocation = round(max(0.1, allocation), 4)
        elif signal == "SELL": # new
            final_allocation = allocation # new
        else:
            final_allocation = 0.0

        response = {
            "type": "ORDER_SIGNAL",
            "symbol": symbol,
            "timestamp": timestamp,
            "signal": signal,
            "price": price,
            "allocation": final_allocation
        }
        
        return response