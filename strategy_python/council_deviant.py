import numpy as np
from collections import deque

class DeviantStrategy:
    def __init__(self, vwap_period=60, entry_z_score=-2.5, abort_z_score=-3.5):
        self.vwap_period = vwap_period
        self.entry_z_score = entry_z_score  
        self.abort_z_score = abort_z_score  
        
        self.prices = deque(maxlen=self.vwap_period)
        self.volumes = deque(maxlen=self.vwap_period)
        
        # O(1) State Tracking
        self.sum_pv = 0.0  # Sum of (Price * Volume)
        self.sum_vol = 0.0 # Sum of Volume
        self.sum_price = 0.0
        self.sum_sq_price = 0.0

    def process_event(self, event):
        if event.get("type") != "MARKET_DATA": return None

        symbol, timestamp, price = event["symbol"], event["timestamp"], event["price"]
        volume = event.get("volume", 0)

        # --- 1. O(1) MATH UPDATES ---
        if len(self.prices) == self.vwap_period:
            oldest_price = self.prices[0]
            oldest_vol = self.volumes[0]
            
            self.sum_pv -= (oldest_price * oldest_vol)
            self.sum_vol -= oldest_vol
            self.sum_price -= oldest_price
            self.sum_sq_price -= (oldest_price ** 2)

        self.prices.append(price)
        self.volumes.append(volume)
        
        self.sum_pv += (price * volume)
        self.sum_vol += volume
        self.sum_price += price
        self.sum_sq_price += (price ** 2)

        # --- 2. SIGNAL GENERATION ---
        signal = "HOLD"
        allocation = 0.0
        vwap = price
        current_z_score = 0.0

        if len(self.prices) == self.vwap_period:
            
            # O(1) Rolling VWAP
            if self.sum_vol > 0:
                vwap = self.sum_pv / self.sum_vol
            else:
                vwap = self.sum_price / self.vwap_period
                
            # O(1) Rolling Z-Score
            n = self.vwap_period
            variance = (self.sum_sq_price - ((self.sum_price ** 2) / n)) / n
            price_std = np.sqrt(max(0, variance))
            
            if price_std > 1e-8:
                current_z_score = (price - vwap) / price_std

            prices_list = list(self.prices)
            is_curling_up = prices_list[-1] > prices_list[-2]

            if current_z_score <= self.entry_z_score and is_curling_up:
                signal = "BUY"
                allocation = 1.0

        return {
            "type": "ORDER_SIGNAL",
            "symbol": symbol,
            "timestamp": timestamp,
            "signal": signal,
            "price": price,
            "allocation": allocation,
            "metadata": {
                "fair_value": vwap,
                "abort_z_score": self.abort_z_score,
                "current_z_score": current_z_score
            }
        }