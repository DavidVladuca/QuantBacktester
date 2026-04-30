import numpy as np
from collections import deque

class BreakoutStrategy:
    def __init__(self, lookback_period=15):
        self.lookback_period = lookback_period
        # We store 15 periods for the box, PLUS 2 periods for the confirmation hold
        self.prices = deque(maxlen=self.lookback_period + 2)

    def process_event(self, event):
        if event.get("type") != "MARKET_DATA":
            return None

        symbol = event["symbol"]
        timestamp = event["timestamp"]
        price = event["price"]

        self.prices.append(price)

        signal = "HOLD"
        allocation = 0.0
        bull_trap_level = 0.0

        if len(self.prices) == self.lookback_period + 2:
            
            # --- 1. DEFINE THE CONSOLIDATION BOX ---
            # Slice the first 15 periods to define our local ceiling and floor
            box_history = list(self.prices)[:self.lookback_period]
            local_high = max(box_history)
            local_low = min(box_history)
            channel_range = local_high - local_low
            
            # Structural Abort: Mid-point of the old box
            bull_trap_level = local_high - (channel_range * 0.5)
            
            # Condition A: Volatility Contraction
            is_coiled = channel_range > 0 and channel_range < (price * 0.005)
            
            # --- 2. UPGRADED BREAKOUT MATH ---
            
            # Dynamic Threshold: Must clear by 20% of the box height, OR 5 basis points (whichever is larger)
            # This protects against micro-spread noise in ultra-tight ranges.
            min_break = max(channel_range * 0.20, price * 0.0005)
            
            # Condition B: Two-Tick Confirmation (Anti-Wick)
            # We look at the 2 most recent prices. BOTH must be firmly above the dynamic threshold.
            recent_prices = list(self.prices)[-2:]
            is_breaking_out = all(p > (local_high + min_break) for p in recent_prices)

            # --- 3. SIGNAL GENERATION ---
            if is_coiled and is_breaking_out:
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
                "abort_level": bull_trap_level
            }
        }