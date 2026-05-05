import json
import numpy as np
from collections import deque

class PullbackStrategy:
    def __init__(self, fast_period=20, slow_period=60, target_vol=0.02): 
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.target_vol = target_vol
        
        # setup windows
        self.prices = deque(maxlen=self.slow_period)
        self.volumes = deque(maxlen=10)

        # tracking variables for curl confirmation
        self.previous_price = None

    def calculate_vol_allocation(self):
        if len(self.prices) < self.fast_period:
            return 0.0, 0.0
            
        prices_window = list(self.prices)[-self.fast_period:]
        returns = np.diff(prices_window) / prices_window[:-1]   
        
        daily_vol = np.std(returns)
        
        if daily_vol == 0:
            return 1.0, 0.01 
            
        dynamic_alloc = self.target_vol / daily_vol 
        return min(1.0, dynamic_alloc), daily_vol

    def process_event(self, event):
        
        if event.get("type") != "MARKET_DATA":
            return None

        symbol = event["symbol"]
        timestamp = event["timestamp"]
        price = event["price"]
        volume = event.get("volume", 0) 

        self.volumes.append(volume)
        self.prices.append(price)

        signal = "HOLD"
        allocation = 0.0

        if len(self.prices) == self.slow_period:
            prices_array = np.array(self.prices)
            fast_sma = np.mean(prices_array[-self.fast_period:])
            slow_sma = np.mean(prices_array)

            fast_sma_prev = np.mean(prices_array[-(self.fast_period + 1):-1]) 
            fast_sma_slope_positive = (fast_sma >= fast_sma_prev) 

            trend_strength = (fast_sma - slow_sma) / slow_sma # 

            dynamic_alloc, daily_vol = self.calculate_vol_allocation()

            # continuous Trend Evaluation 
            proximity_threshold = min(max(daily_vol, 0.001), 0.005) 
            is_near_slow_sma = abs(price - slow_sma) / slow_sma <= proximity_threshold 
            min_trend = max(0.002, daily_vol * 0.5)

            # check for Pullback setup
            is_pullback_zone = fast_sma > slow_sma and slow_sma < price < fast_sma 
            
            if is_pullback_zone and is_near_slow_sma and trend_strength >= min_trend and fast_sma_slope_positive: 
                signal = "BUY" 
                allocation = dynamic_alloc 
            
            # trend breakdown exit 
            elif price < slow_sma * (1.0 - daily_vol): 
                signal = "SELL" 
                allocation = 1.0 

        self.previous_price = price

        if signal == "BUY":
            final_allocation = round(max(0.1, allocation), 4)
        elif signal == "SELL": 
            final_allocation = allocation 
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