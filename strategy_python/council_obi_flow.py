import math
import numpy as np

class OBIFlowStrategy:
    def __init__(self, target_symbol, tau_ms=2000, trigger_threshold=0.4):
        self.target_symbol = target_symbol
        self.tau_ms = tau_ms
        self.trigger_threshold = trigger_threshold
        
        self.obi_ema = None
        self.last_timestamp = None

    def process_event(self, event):
        if event.get("type") != "MARKET_DATA" or event.get("symbol") != self.target_symbol: 
            return None

        bid_size = event.get("bid_size", 0)
        ask_size = event.get("ask_size", 0)
        price = event.get("price", event.get("bid_price", 0))
        timestamp = event["timestamp"]

        # 1. CALCULATE RAW OBI
        total_size = bid_size + ask_size
        raw_obi = 0.0 
        if total_size > 0:
            raw_obi = (bid_size - ask_size) / total_size

        # 2. TIME-WEIGHTED EXPONENTIAL SMOOTHING
        if self.obi_ema is None or self.last_timestamp is None:
            self.obi_ema = raw_obi
            self.last_timestamp = timestamp
        else:
            dt = max(0, timestamp - self.last_timestamp)
            alpha = 1.0 - math.exp(-dt / self.tau_ms)
            self.obi_ema = raw_obi * alpha + self.obi_ema * (1.0 - alpha)
            self.last_timestamp = timestamp

        # 🚨 NEW: CONTINUOUS CONFIDENCE SCALING (-1.0 to 1.0)
        # We divide the current EMA by the trigger threshold.
        raw_confidence = self.obi_ema / self.trigger_threshold
        confidence = float(np.clip(raw_confidence, -1.0, 1.0))

        # We keep the text signal for logging, but the math engine will ignore it.
        signal = "HOLD"
        if confidence >= 0.8: signal = "BUY"
        elif confidence <= -0.8: signal = "SELL"

        return {
            "type": "ORDER_SIGNAL",
            "symbol": self.target_symbol,
            "timestamp": timestamp,
            "signal": signal,
            "confidence": confidence, # 🚨 THE NEW BRAIN
            "price": price,
            "metadata": {
                "raw_obi": round(raw_obi, 4),
                "ema_obi": round(self.obi_ema, 4),
                "expert_name": "OBI_FLOW"
            }
        }