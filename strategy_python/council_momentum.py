import numpy as np
from collections import deque

class MomentumEngineStrategy:
    def __init__(self, target_symbol, lookback=60, vol_z_threshold=1.8, volume_mult=1.2):
        self.target_symbol = target_symbol
        self.lookback = lookback
        self.vol_z_threshold = vol_z_threshold
        self.volume_mult = volume_mult
        
        # State tracking
        self.prev_price = None
        self.returns = deque(maxlen=self.lookback)
        self.volumes = deque(maxlen=self.lookback)
        
        # O(1) Math State
        self.sum_returns = 0.0
        self.sum_sq_returns = 0.0
        self.sum_volume = 0.0 

    def process_event(self, event):
        if event.get("type") != "MARKET_DATA" or event.get("symbol") != self.target_symbol:
            return None

        price = event.get("price", event.get("bid_price", 0)) # Safe fallback
        volume = event.get("volume", event.get("bid_size", 0) + event.get("ask_size", 0))
        timestamp = event["timestamp"]

        # If first tick, just store and return
        if self.prev_price is None:
            self.prev_price = price
            return self._empty_signal(timestamp, price)

        # 1. CALCULATE CURRENT RETURN
        # Log return is standard for financial time series
        current_return = np.log(price) - np.log(self.prev_price)
        self.prev_price = price

        # 2. O(1) ROLLING UPDATES
        if len(self.returns) == self.lookback:
            old_ret = self.returns[0]
            old_vol = self.volumes[0]
            
            self.sum_returns -= old_ret
            self.sum_sq_returns -= (old_ret ** 2)
            self.sum_volume -= old_vol

        self.returns.append(current_return)
        self.volumes.append(volume)
        
        self.sum_returns += current_return
        self.sum_sq_returns += (current_return ** 2)
        self.sum_volume += volume

        # 3. STATISTICAL BREAKOUT LOGIC
        signal = "HOLD"
        z_score_ret = 0.0
        
        if len(self.returns) >= self.lookback:
            # Calculate Realized Volatility (Standard Deviation of returns)
            mean_ret = self.sum_returns / self.lookback
            variance = (self.sum_sq_returns - (self.sum_returns ** 2) / self.lookback) / self.lookback
            std_dev = np.sqrt(max(1e-9, variance))
            
            # How extreme is this current move?
            z_score_ret = (current_return - mean_ret) / std_dev
            
            # Average Volume
            avg_vol = self.sum_volume / self.lookback
            
            # 🚨 THE TRIGGER: 3-Sigma move + Volume Anomaly
            if z_score_ret >= self.vol_z_threshold and volume >= (avg_vol * self.volume_mult):
                signal = "BUY"
            elif z_score_ret <= -self.vol_z_threshold and volume >= (avg_vol * self.volume_mult):
                signal = "SELL"

        return {
            "type": "ORDER_SIGNAL",
            "symbol": self.target_symbol,
            "timestamp": timestamp,
            "signal": signal,
            "price": price,
            "metadata": {
                "momentum_z_score": round(z_score_ret, 4),
                "expert_name": "MOMENTUM_ENGINE"
            }
        }

    def _empty_signal(self, timestamp, price):
        return {"type": "ORDER_SIGNAL", "symbol": self.target_symbol, "timestamp": timestamp, "signal": "HOLD", "price": price, "metadata": {"momentum_z_score": 0.0}}