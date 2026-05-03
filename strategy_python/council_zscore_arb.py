import numpy as np
from collections import deque

class ZScoreArbStrategy:
    def __init__(self, target_symbol, hedge_symbol, window_ms=3600000,
                 bucket_interval_ms=60000, entry_threshold=2.0, exit_threshold=0.2):
        self.target_symbol = target_symbol
        self.hedge_symbol = hedge_symbol
        self.window_ms = window_ms
        self.bucket_interval_ms = bucket_interval_ms
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold

        self.last_prices = {self.target_symbol: None, self.hedge_symbol: None}

        self.spread_history = deque()  # (timestamp, spread) tuples
        self.last_bucket_time = 0

        # Running sums allow O(1) mean and variance on every tick
        self.sum_spread = 0.0
        self.sum_sq_spread = 0.0

    def process_event(self, event):
        if event.get("type") != "MARKET_DATA":
            return None

        symbol = event["symbol"]
        price = event["price"]
        timestamp = event["timestamp"]

        if symbol not in self.last_prices:
            return None

        self.last_prices[symbol] = price

        if self.last_prices[self.target_symbol] is None or self.last_prices[self.hedge_symbol] is None:
            return self._empty_signal(symbol, timestamp, price)

        target_price = self.last_prices[self.target_symbol]
        hedge_price = self.last_prices[self.hedge_symbol]
        current_spread = np.log(target_price) - np.log(hedge_price)

        # Prune entries that have aged out of the window, keeping running sums exact
        cutoff = timestamp - self.window_ms
        while self.spread_history and self.spread_history[0][0] < cutoff:
            _, old_spread = self.spread_history.popleft()
            self.sum_spread -= old_spread
            self.sum_sq_spread -= old_spread ** 2

        # Append one bucket sample per bucket_interval_ms — keeps points statistically
        # independent and limits the deque to ~60 entries over a 60-minute window
        if timestamp - self.last_bucket_time >= self.bucket_interval_ms:
            self.spread_history.append((timestamp, current_spread))
            self.sum_spread += current_spread
            self.sum_sq_spread += current_spread ** 2
            self.last_bucket_time = timestamp

        z_score = 0.0
        n = len(self.spread_history)
        if n >= 2:
            mean = self.sum_spread / n
            # Computational form of variance: E[X²] − (E[X])²
            variance = (self.sum_sq_spread / n) - (mean ** 2)
            std = np.sqrt(max(1e-9, variance))
            z_score = (current_spread - mean) / std

        raw_confidence = -z_score / (self.entry_threshold * 2.0)
        confidence = float(np.clip(raw_confidence, -1.0, 1.0))
        signal = "TRADE"

        if abs(z_score) <= self.exit_threshold:
            confidence = 0.0
            signal = "EXIT"

        return {
            "type": "ORDER_SIGNAL",
            "symbol": symbol,
            "timestamp": timestamp,
            "signal": signal,
            "confidence": confidence,
            "price": price,
            "metadata": {
                "z_score": round(z_score, 4),
                "spread": round(current_spread, 6),
                "expert_name": "Z_SCORE_ARB"
            }
        }

    def _empty_signal(self, symbol, timestamp, price):
        return {
            "type": "ORDER_SIGNAL",
            "symbol": symbol,
            "timestamp": timestamp,
            "signal": "HOLD",
            "confidence": 0.0,
            "price": price,
            "metadata": {"z_score": 0.0, "spread": 0.0}
        }
