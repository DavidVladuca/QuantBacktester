import numpy as np
from collections import deque

class MomentumEngineStrategy:
    def __init__(self, target_symbol, window_ms=1800000, vol_z_threshold=2.0, volume_mult=1.0):
        self.target_symbol = target_symbol
        self.window_ms = window_ms
        self.vol_z_threshold = vol_z_threshold
        self.volume_mult = volume_mult

        self.price_history = deque()
        self.vol_history = deque()

        self.confidence_ema = None
        self.ema_alpha = 0.35

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

        prices = np.fromiter(
            (p for _, p in self.price_history),
            dtype=np.float64,
            count=len(self.price_history)
        )

        lookback_steps = min(10, len(prices) - 1)
        recent_prices = prices[-(lookback_steps + 1):]
        recent_returns = np.diff(np.log(recent_prices))
        total_return = np.sum(recent_returns)

        step_returns = np.diff(np.log(prices))
        step_std = np.std(step_returns) if len(step_returns) > 1 else 1e-9

        z_score_ret = total_return / max(step_std, 1e-9)
        z_score_ret = np.clip(z_score_ret, -5.0, 5.0)

        vols = np.fromiter(
            (v for _, v in self.vol_history),
            dtype=np.float64,
            count=len(self.vol_history)
        )
        avg_vol = np.mean(vols)

        if avg_vol > 0:
            vol_modifier = min(1.0, np.sqrt(volume / (avg_vol * self.volume_mult)))
        else:
            vol_modifier = 0.0

        raw_confidence = float(np.clip(
            (z_score_ret / (self.vol_z_threshold * 2.0)) * vol_modifier,
            -1.0,
            1.0
        ))

        # NEW: EMA smoothing
        if self.confidence_ema is None:
            self.confidence_ema = raw_confidence
        else:
            self.confidence_ema = (
                self.ema_alpha * raw_confidence +
                (1.0 - self.ema_alpha) * self.confidence_ema
            )

        confidence = float(np.clip(self.confidence_ema, -1.0, 1.0))

        return {
            "type": "ORDER_SIGNAL",
            "symbol": self.target_symbol,
            "timestamp": timestamp,
            "signal": "TRADE",
            "confidence": confidence,
            "price": price,
            "metadata": {
                "momentum_z_score": round(z_score_ret, 4),
                "raw_confidence": round(raw_confidence, 4),
                "smoothed_confidence": round(confidence, 4),
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