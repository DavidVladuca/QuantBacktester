import numpy as np
from collections import deque

# BREAKOUT = compression breakout strategy that:
# - builds a short-term consolidation box from recent prices
# - checks that volatility/range has contracted
# - requires two confirmed closes above the breakout threshold
# - outputs BUY only when the breakout clears noise
class BreakoutStrategy:
    def __init__(self, lookback_period=15):
        self.lookback_period = lookback_period

        # store box window + 2 confirmation prices
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
            
            # define consolidation box
            box_history = list(self.prices)[:self.lookback_period]
            local_high = max(box_history)
            local_low = min(box_history)
            channel_range = local_high - local_low
            
            # midpoint used as possible failed-breakout abort level
            bull_trap_level = local_high - (channel_range * 0.5)
            
            # require tight range before accepting breakout
            is_coiled = channel_range > 0 and channel_range < (price * 0.005)
            
            # require breakout to clear box noise
            min_break = max(channel_range * 0.20, price * 0.0005)
            
            # require both latest prices above breakout level
            recent_prices = list(self.prices)[-2:]
            is_breaking_out = all(p > (local_high + min_break) for p in recent_prices)

            # signal generation
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