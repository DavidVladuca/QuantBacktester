import numpy as np
from collections import deque

class MomentumEngineStrategy:
    def __init__(self, target_symbol, window_ms=300000, vol_z_threshold=1.8, volume_mult=1.0):
        self.target_symbol = target_symbol
        self.window_ms = window_ms
        self.vol_z_threshold = vol_z_threshold
        self.volume_mult = volume_mult

        self.price_history = deque()  # (timestamp, price) tuples
        self.vol_history = deque()    # (timestamp, volume) tuples, always co-pruned

    def process_event(self, event):
        if event.get("type") != "MARKET_DATA" or event.get("symbol") != self.target_symbol:
            return None

        price = event.get("price", event.get("bid_price", 0))
        volume = event.get("volume", event.get("bid_size", 0) + event.get("ask_size", 0))
        timestamp = event["timestamp"]

        if price <= 0:
            return self._empty_signal(timestamp, price)

        self.price_history.append((timestamp, price))
        self.vol_history.append((timestamp, volume))

        cutoff = timestamp - self.window_ms
        while self.price_history and self.price_history[0][0] < cutoff:
            self.price_history.popleft()
            self.vol_history.popleft()

        if len(self.price_history) < 2:
            return self._empty_signal(timestamp, price)

        # Total log return from the oldest surviving price to now
        oldest_price = self.price_history[0][1]
        total_return = np.log(price / oldest_price)

        # Per-step volatility across the window — normalises total_return into
        # standard deviations of expected random-walk drift over n steps
        prices = np.fromiter((p for _, p in self.price_history), dtype=np.float64,
                             count=len(self.price_history))
        step_returns = np.diff(np.log(prices))
        step_std = np.std(step_returns) if len(step_returns) > 1 else 1e-9

        n_steps = len(step_returns)
        z_score_ret = total_return / max(step_std * np.sqrt(n_steps), 1e-9)

        # Volume modifier: penalises below-average volume, caps at 1.0
        vols = np.fromiter((v for _, v in self.vol_history), dtype=np.float64,
                           count=len(self.vol_history))
        avg_vol = np.mean(vols)
        vol_modifier = min(1.0, volume / (avg_vol * self.volume_mult)) if avg_vol > 0 else 0.0

        base_confidence = z_score_ret / (self.vol_z_threshold * 2.0)
        confidence = float(np.clip(base_confidence * vol_modifier, -1.0, 1.0))

        return {
            "type": "ORDER_SIGNAL",
            "symbol": self.target_symbol,
            "timestamp": timestamp,
            "signal": "TRADE",
            "confidence": confidence,
            "price": price,
            "metadata": {
                "momentum_z_score": round(z_score_ret, 4),
                "expert_name": "MOMENTUM_ENGINE"
            }
        }

    def _empty_signal(self, timestamp, price):
        return {
            "type": "ORDER_SIGNAL",
            "symbol": self.target_symbol,
            "timestamp": timestamp,
            "signal": "HOLD",
            "confidence": 0.0,
            "price": price,
            "metadata": {"momentum_z_score": 0.0}
        }
