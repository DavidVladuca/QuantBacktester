import numpy as np
from collections import deque

class ExhaustionStrategy:
    def __init__(self, rsi_period=7, entry_threshold=20, exit_threshold=65):
        self.rsi_period = rsi_period
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold
        
        self.prices = deque(maxlen=20)
        self.rsis = deque(maxlen=5) 
        
        # O(1) RSI State Tracking
        self.gains = deque(maxlen=self.rsi_period)
        self.losses = deque(maxlen=self.rsi_period)
        self.sum_gains = 0.0
        self.sum_losses = 0.0

    def process_event(self, event):
        if event.get("type") != "MARKET_DATA": return None
        symbol, timestamp, price = event["symbol"], event["timestamp"], event["price"]
        high, low = event.get("high", price), event.get("low", price)

        # --- 1. O(1) GAIN/LOSS UPDATES ---
        if len(self.prices) > 0:
            change = price - self.prices[-1]
            gain = max(0, change)
            loss = max(0, -change)
            
            if len(self.gains) == self.rsi_period:
                self.sum_gains -= self.gains[0]
                self.sum_losses -= self.losses[0]
                
            self.gains.append(gain)
            self.losses.append(loss)
            self.sum_gains += gain
            self.sum_losses += loss

        self.prices.append(price)

        # --- 2. O(1) RSI CALCULATION ---
        current_rsi = 50.0
        if len(self.gains) == self.rsi_period:
            avg_gain = self.sum_gains / self.rsi_period
            avg_loss = self.sum_losses / self.rsi_period
            
            if avg_loss == 0:
                current_rsi = 100.0 if avg_gain > 0 else 50.0
            else:
                rs = avg_gain / avg_loss
                current_rsi = 100.0 - (100.0 / (1.0 + rs))
                
        self.rsis.append(current_rsi)

        signal, allocation, structure_low = "HOLD", 0.0, 0.0

        # --- 3. ALPHA FILTERS ---
        if len(self.prices) >= 10 and len(self.rsis) >= 2:
            # A. Strong Close Check: Close must be in the top 30% of the minute's range
            candle_range = high - low
            relative_close = (price - low) / candle_range if candle_range > 0 else 0.5
            is_strong_bounce = relative_close > 0.70
            
            # B. Curling and Hooking
            is_curling_up = (self.prices[-1] > self.prices[-2] + (price * 0.0001))
            is_rsi_hooking = (self.rsis[-2] <= self.entry_threshold) and (current_rsi > self.rsis[-2])
            
            prices_list = list(self.prices)
            structure_low = min(prices_list[-3:]) 

            # 🚨 TRIGGER: All three conditions must be met
            if is_rsi_hooking and is_curling_up and is_strong_bounce:
                signal, allocation = "BUY", 1.0

        # Renamed key to current_rsi
        return {
            "type": "ORDER_SIGNAL", 
            "symbol": symbol, 
            "timestamp": timestamp, 
            "signal": signal, 
            "price": price, 
            "allocation": allocation, 
            "metadata": {
                "current_rsi": current_rsi, 
                "exit_threshold": self.exit_threshold, 
                "structure_low": structure_low
            }
        }