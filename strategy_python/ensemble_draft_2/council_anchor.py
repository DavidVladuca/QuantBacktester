import numpy as np
from collections import deque

class AnchorStrategy:
    def __init__(self, macro_period=200):
        self.macro_period = macro_period
        self.prices = deque(maxlen=self.macro_period)
        self.current_regime = "HOLD" 
        
        # O(1) SMA State
        self.running_sum = 0.0
        
        # O(1) Volatility State
        self.prev_price = None
        self.returns = deque(maxlen=self.macro_period - 1)
        self.sum_returns = 0.0
        self.sum_sq_returns = 0.0

        # 🚨 NEW: SLOPE TRACKER
        # We store the last 10 minutes of SMA values to calculate the trend angle
        self.sma_history = deque(maxlen=10)

    def process_event(self, event):
        if event.get("type") != "MARKET_DATA": return None

        symbol, timestamp, price = event["symbol"], event["timestamp"], event["price"]

        # --- 1. O(1) MATH UPDATES ---
        if len(self.prices) == self.macro_period:
            oldest_price = self.prices[0]
            self.running_sum -= oldest_price
            
        self.prices.append(price)
        self.running_sum += price

        # Calculate Returns Volatility in O(1)
        if self.prev_price is not None:
            current_return = (price - self.prev_price) / self.prev_price
            if len(self.returns) == self.macro_period - 1:
                oldest_return = self.returns[0]
                self.sum_returns -= oldest_return
                self.sum_sq_returns -= (oldest_return ** 2)
                
            self.returns.append(current_return)
            self.sum_returns += current_return
            self.sum_sq_returns += (current_return ** 2)
            
        self.prev_price = price

        # --- 2. SIGNAL & SLOPE GENERATION ---
        signal = self.current_regime
        sma_200 = 0.0
        slope = 0.0
        confidence = 0.0
        noise_threshold = 0.001 

        if len(self.prices) == self.macro_period:
            sma_200 = self.running_sum / self.macro_period
            
            # 🚨 NEW: SLOPE CALCULATION
            # Comparison: current SMA vs SMA from 10 minutes ago
            if len(self.sma_history) == 10:
                oldest_sma = self.sma_history[0]
                # Slope formula: $Slope = \frac{SMA_{current} - SMA_{old}}{SMA_{old}}$
                slope = (sma_200 - oldest_sma) / oldest_sma
            
            self.sma_history.append(sma_200)

            # Volatility Math
            n_returns = len(self.returns)
            variance = (self.sum_sq_returns - ((self.sum_returns ** 2) / n_returns)) / n_returns
            vol_multiplier = np.sqrt(max(0, variance))
            noise_threshold = max(vol_multiplier * 2, 0.001)
            
            # Regime Logic
            upper_band = sma_200 * (1 + noise_threshold)
            lower_band = sma_200 * (1 - noise_threshold)
            
            if self.current_regime == "HOLD":
                self.current_regime = "BUY" if price > sma_200 else "SELL"
            elif price > upper_band:
                self.current_regime = "BUY"
            elif price < lower_band:
                self.current_regime = "SELL"
            
            signal = self.current_regime
            distance_from_sma = abs(price - sma_200) / sma_200
            confidence = min(1.0, distance_from_sma / (noise_threshold * 3))

        return {
            "type": "ORDER_SIGNAL",
            "symbol": symbol,
            "timestamp": timestamp,
            "signal": signal,
            "price": price,
            "allocation": 0.0,
            "metadata": {
                "intraday_bias": signal,
                "confidence": round(confidence, 4),
                "macro_sma": sma_200,
                "slope": slope, # 🚨 ENSEMBLE NOW SEES THIS
                "vol_adaptive_noise": round(noise_threshold, 6)
            }
        }