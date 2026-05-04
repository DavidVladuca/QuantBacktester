import json
import numpy as np
from collections import deque
from datetime import datetime, timezone

class VWAPStrategy:
    def __init__(self, target_vol=0.02, vol_window=10, fast_period=20):
        self.target_vol = target_vol
        self.vol_window = vol_window
        self.fast_period = fast_period 
        
        # setup windows
        self.max_window = max(self.vol_window, self.fast_period)
        self.prices = deque(maxlen=self.max_window)
        self.volumes = deque(maxlen=10) 
        
        # state variables
        self.previous_price = None
        self.current_day = None
        self.cum_vol = 0.0
        self.cum_pv = 0.0

    def calculate_vol_allocation(self):
        if len(self.prices) < self.vol_window:
            return 0.0, 0.0 
            
        prices_window = list(self.prices)[-self.vol_window:]
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
        high = event.get("high", price) 
        low = event.get("low", price) 
        volume = event.get("volume")

        if volume is None:
            return {"type": "ORDER_SIGNAL", "symbol": symbol, "timestamp": timestamp, "signal": "HOLD", "price": price, "allocation": 0.0}

        self.prices.append(price)
        self.volumes.append(volume) 

        signal = "HOLD"
        allocation = 0.0

        event_date = datetime.fromtimestamp(timestamp / 1000.0, tz=timezone.utc).date()

        if self.current_day != event_date:
            self.current_day = event_date
            self.cum_vol = 0.0
            self.cum_pv = 0.0

        typical_price = (high + low + price) / 3.0
        self.cum_pv += (typical_price * volume)
        self.cum_vol += volume

        vwap = self.cum_pv / self.cum_vol if self.cum_vol > 0 else price
        
        dynamic_alloc, daily_vol = self.calculate_vol_allocation() 

        if len(self.prices) >= self.fast_period: 
            prices_array = np.array(self.prices) 
            fast_sma = np.mean(prices_array[-self.fast_period:]) 
            
            # VWAP Breakdown 
            if price < vwap * (1.0 - daily_vol): 
                signal = "SELL" 
                allocation = 1.0 
                
            # VWAP Pullback 
            else: 
                trend_strength = (fast_sma - vwap) / vwap if vwap > 0 else 0 
                trend_up = trend_strength >= 0.0015 and price >= vwap 
                
                if trend_up: 
                    signal = "BUY" 
                    allocation = dynamic_alloc 

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