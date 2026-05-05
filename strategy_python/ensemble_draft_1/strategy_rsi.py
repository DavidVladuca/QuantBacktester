import json
import numpy as np
from collections import deque

# Relative Strength Index (RSI) strategy
class RSIStrategy:
    def __init__(self, rsi_period=14, oversold=40, vol_period=20, slow_period=50, target_vol=0.02, require_trend=True): 
        self.rsi_period = rsi_period 
        self.oversold = oversold 
        self.vol_period = vol_period 
        self.slow_period = slow_period 
        self.target_vol = target_vol 
        self.require_trend = require_trend # toggle for Chop vs Trend behavior
        
        # rolling window setup -> check window is large enough for the 50 SMA
        self.max_window = max(self.rsi_period + 1, self.vol_period + 1, self.slow_period)
        self.prices = deque(maxlen=self.max_window)

    def calculate_rsi(self):
        if len(self.prices) < self.rsi_period + 1:
            return None
            
        prices_window = list(self.prices)[-(self.rsi_period + 1):]
        changes = np.diff(prices_window) 
        
        gains = np.where(changes > 0, changes, 0)
        losses = np.where(changes < 0, -changes, 0)
        
        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)
        
        if avg_loss == 0:
            return 100.0
            
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def calculate_vol_allocation(self):
        if len(self.prices) < self.vol_period + 1:
            return 0.0, 0.0 
            
        prices_window = list(self.prices)[-(self.vol_period + 1):]
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

        self.prices.append(price)

        signal = "HOLD"
        allocation = 0.0

        if len(self.prices) >= self.max_window:
            rsi = self.calculate_rsi()
            dynamic_alloc, daily_vol = self.calculate_vol_allocation() 
            
            # trend strength based on slow SMA
            prices_array = np.array(self.prices)
            slow_sma = np.mean(prices_array[-self.slow_period:])
            
            trend_strength = (price - slow_sma) / slow_sma 
            
            if rsi is not None: 
                
                # continuous Oversold Condition 
                rsi_condition = rsi <= self.oversold 
                
                # trend condition based on input 
                trend_condition = (trend_strength >= 0.002) if self.require_trend else True
                
                if rsi_condition and trend_condition: 
                    signal = "BUY"
                    allocation = dynamic_alloc
                
                # overbought exit condition 
                elif rsi >= 70: 
                    signal = "SELL" 
                    allocation = 1.0 
        
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