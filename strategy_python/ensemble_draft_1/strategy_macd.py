import json
import numpy as np
from collections import deque

# Moving Average Convergence Divergence (MACD) strategy
class MACDStrategy:
    def __init__(self, fast_period=12, slow_period=26, signal_period=9, vol_period=20, target_vol=0.02):  
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
        
        self.vol_period = vol_period
        self.target_vol = target_vol
        
        # rolling window setup (100 is enough to give time for EMAs to stabilize)
        # EMA = Exponential Moving Average
        self.max_window = max(100, self.vol_period + 1)
        self.prices = deque(maxlen=self.max_window)

    def calculate_ema_array(self, data, window):
        alpha = 2 / (window + 1)
        ema = [data[0]]
        for price in data[1:]:
            ema.append((price - ema[-1]) * alpha + ema[-1])
        return np.array(ema)

    def calculate_macd(self):
        if len(self.prices) < self.slow_period + self.signal_period:
            return None, None, None, None
            
        prices_list = list(self.prices)
        
        # compute EMAs
        fast_ema = self.calculate_ema_array(prices_list, self.fast_period)
        slow_ema = self.calculate_ema_array(prices_list, self.slow_period)
        
        # MACD line
        macd_line = fast_ema - slow_ema
        
        # signal line (EMA of the MACD line)
        signal_line = self.calculate_ema_array(macd_line, self.signal_period)
        
        # current and previous values for crossover detection
        current_macd = macd_line[-1]
        current_signal = signal_line[-1]
        prev_macd = macd_line[-2]
        prev_signal = signal_line[-2]
        
        return current_macd, current_signal, prev_macd, prev_signal

    def calculate_vol_allocation(self):
        if len(self.prices) < self.vol_period + 1:
            return 0.0
            
        # current window of prices
        prices_window = list(self.prices)[-(self.vol_period + 1):]
        returns = np.diff(prices_window) / prices_window[:-1] # changes / price(i-1) => daily returns   
        
        daily_vol = np.std(returns)
        
        if daily_vol == 0:
            return 1.0 # if no volatility, we allocate all
            
        dynamic_alloc = self.target_vol / daily_vol # high volatility => smaller allocation, low volatility => bigger allocation
        return min(1.0, dynamic_alloc) # clamp allocation to 100%

    def process_event(self, event):
        
        if event.get("type") != "MARKET_DATA":
            return None

        symbol = event["symbol"]
        timestamp = event["timestamp"]
        price = event["price"]

        self.prices.append(price)

        signal = "HOLD"
        allocation = 0.0

        # wait until the window is full
        if len(self.prices) >= self.max_window:
            current_macd, current_signal, prev_macd, prev_signal = self.calculate_macd()
            dynamic_alloc = self.calculate_vol_allocation()

            if current_macd is not None: 
                # continuous Bullish Momentum Stance 
                if current_macd > current_signal: 
                    signal = "BUY" 
                    allocation = dynamic_alloc 
                
                # continuous Bearish Momentum Stance 
                elif current_macd < current_signal: 
                    signal = "SELL" 
                    allocation = 1.0 

        # final allocation
        if signal == "BUY":
            final_allocation = round(max(0.1, allocation), 4) # clamped min 10%
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