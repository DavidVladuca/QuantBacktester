import numpy as np
from collections import deque

class ZScoreArbStrategy:
    def __init__(self, target_symbol, hedge_symbol, window_size=60, entry_threshold=2.0, exit_threshold=0.2):
        self.target_symbol = target_symbol
        self.hedge_symbol = hedge_symbol
        self.window_size = window_size
        
        # Widened the entry, tightened the exit to ensure we capture meatier moves
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold
        
        self.last_prices = {self.target_symbol: None, self.hedge_symbol: None}
        
        # 🚨 NEW: Time-Bucketing State
        self.spread_history = deque(maxlen=window_size)
        self.last_bucket_time = 0
        self.bucket_interval_ms = 60000  # 60,000 ms = 1 Minute
        
        self.sum_spread = 0.0
        self.sum_sq_spread = 0.0

    def process_event(self, event):
        if event.get("type") != "MARKET_DATA": return None

        symbol = event["symbol"]
        price = event["price"]
        timestamp = event["timestamp"] 

        if symbol not in self.last_prices:
            return None

        self.last_prices[symbol] = price

        if self.last_prices[self.target_symbol] is None or self.last_prices[self.hedge_symbol] is None:
            return self._empty_signal(symbol, timestamp, price)

        # Current Live Spread
        target_price = self.last_prices[self.target_symbol]
        hedge_price = self.last_prices[self.hedge_symbol]
        current_spread = np.log(target_price) - np.log(hedge_price)

        # 🚨 THE FIX: Only update the historical baseline once per minute
        if timestamp - self.last_bucket_time >= self.bucket_interval_ms:
            if len(self.spread_history) == self.window_size:
                old_spread = self.spread_history[0]
                self.sum_spread -= old_spread
                self.sum_sq_spread -= (old_spread ** 2)

            self.spread_history.append(current_spread)
            self.sum_spread += current_spread
            self.sum_sq_spread += (current_spread ** 2)
            
            self.last_bucket_time = timestamp

        # Calculate Z-Score against the STABLE baseline
        z_score = 0.0
        if len(self.spread_history) >= self.window_size:
            mean = self.sum_spread / self.window_size
            variance = (self.sum_sq_spread - (self.sum_spread ** 2) / self.window_size) / self.window_size
            std = np.sqrt(max(1e-9, variance))
            z_score = (current_spread - mean) / std

        signal = "HOLD"
        
        if symbol == self.target_symbol:
            if z_score <= -self.entry_threshold:
                signal = "BUY"
            elif z_score >= self.entry_threshold:
                signal = "SELL"
            elif abs(z_score) <= self.exit_threshold:
                signal = "EXIT"

        return {
            "type": "ORDER_SIGNAL",
            "symbol": symbol,
            "timestamp": timestamp,
            "signal": signal,
            "price": price,
            "metadata": {
                "z_score": round(z_score, 4),
                "spread": round(current_spread, 6),
                "expert_name": "Z_SCORE_ARB"
            }
        }

    def _empty_signal(self, symbol, timestamp, price):
        return {"type": "ORDER_SIGNAL", "symbol": symbol, "timestamp": timestamp, "signal": "HOLD", "price": price, "metadata": {"z_score": 0.0, "spread": 0.0}}