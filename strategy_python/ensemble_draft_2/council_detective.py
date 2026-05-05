import numpy as np
from collections import deque

# DETECTIVE = confirmation/veto strategy that:
# - measures recent price move strength
# - compares current volume against average volume
# - checks candle control inside the high-low range
# - confirms or vetoes directional moves based on conviction
class DetectiveStrategy:
    def __init__(self, vol_window=20, conviction_threshold=1.8):
        self.vol_window = vol_window
        self.conviction_threshold = conviction_threshold
        
        self.prices = deque(maxlen=self.vol_window)
        self.volumes = deque(maxlen=self.vol_window)
        
        # O(1) volume state
        self.sum_vol = 0.0

        # O(1) volatility state
        self.prev_price = None
        self.returns = deque(maxlen=self.vol_window - 1)
        self.sum_returns = 0.0
        self.sum_sq_returns = 0.0

    def process_event(self, event):
        if event.get("type") != "MARKET_DATA": return None

        symbol, timestamp, price = event["symbol"], event["timestamp"], event["price"]
        high, low = event.get("high", price), event.get("low", price)
        volume = event.get("volume", 0)

        # update volume in O(1)
        if len(self.volumes) == self.vol_window:
            self.sum_vol -= self.volumes[0]
        self.volumes.append(volume)
        self.sum_vol += volume

        # compute returns and volatility in O(1)
        if self.prev_price is not None:
            current_return = (price - self.prev_price) / self.prev_price
            if len(self.returns) == self.vol_window - 1:
                oldest_return = self.returns[0]
                self.sum_returns -= oldest_return
                self.sum_sq_returns -= (oldest_return ** 2)
            
            self.returns.append(current_return)
            self.sum_returns += current_return
            self.sum_sq_returns += (current_return ** 2)
            
        self.prev_price = price
        self.prices.append(price)

        signal, allocation = "NEUTRAL", 0.0
        conviction_score, rvol, vol_threshold = 0.0, 1.0, 0.001
        direction = "NONE"

        if len(self.prices) >= 10 and len(self.volumes) == self.vol_window:
            avg_vol = self.sum_vol / self.vol_window
            
            # volatility threshold
            n_returns = len(self.returns)
            variance = (self.sum_sq_returns - ((self.sum_returns ** 2) / n_returns)) / n_returns
            vol_threshold = max(np.sqrt(max(0, variance)) * 2, 0.001)
            effective_vol = max(vol_threshold, 0.0005)

            # recent directional move
            price_3_bars_ago = self.prices[-3] if len(self.prices) >= 3 else self.prices[0]
            price_change_pct = (price - price_3_bars_ago) / price_3_bars_ago
            
            # candle control inside the bar
            candle_range = high - low
            candle_position = (price - low) / candle_range if candle_range > 0 else 0.5
            candle_control = 2 * abs(candle_position - 0.5) 
            
            # relative volume
            rvol = volume / avg_vol if avg_vol > 0 else 1.0

            # conviction score combines volume, move size, and candle control
            conviction_score = min(1.0, (rvol / 2.0) * (abs(price_change_pct) / effective_vol) * candle_control)

            if price_change_pct > vol_threshold: direction = "BUY"
            elif price_change_pct < -vol_threshold: direction = "SELL"

            # signal generation
            if abs(price_change_pct) > vol_threshold and rvol < 0.7:
                signal = "VETO"
            elif direction != "NONE" and rvol >= self.conviction_threshold:
                if direction == "BUY" and candle_position >= 0.75: signal = "CONFIRM_BUY"
                elif direction == "SELL" and candle_position <= 0.25: signal = "CONFIRM_SELL"
            elif abs(price_change_pct) > (vol_threshold * 0.5) and rvol >= 1.2:
                if direction == "BUY" and candle_position >= 0.7: signal = "WEAK_CONFIRM_BUY"
                elif direction == "SELL" and candle_position <= 0.3: signal = "WEAK_CONFIRM_SELL"

        return {
            "type": "ORDER_SIGNAL",
            "symbol": symbol, "timestamp": timestamp, "signal": signal, "price": price, "allocation": allocation,
            "metadata": {"direction": direction, "conviction": round(conviction_score, 4), "rvol": round(rvol, 2), "vol_threshold": round(vol_threshold, 6)}
        }