import numpy as np
from collections import deque

# SPRINTER = pullback-continuation strategy that:
# - tracks trend using a 20-period EMA
# - measures pullback distance from EMA
# - requires volume expansion on the rebound
# - outputs BUY when price curls up from the EMA zone
class SprinterStrategy:
    def __init__(self, ema_period=20, vol_window=20, z_score_threshold=1.8):
        self.ema_period = ema_period
        self.vol_window = vol_window
        self.z_score_threshold = z_score_threshold
        
        self.prices = deque(maxlen=30)
        
        # O(1) volume state
        self.volumes = deque(maxlen=self.vol_window)
        self.sum_vol = 0.0
        self.sum_sq_vol = 0.0
        
        # O(1) EMA-distance state
        self.ema_distances = deque(maxlen=60) 
        self.sum_dist = 0.0
        self.sum_sq_dist = 0.0
        
        self.ema20 = None
        self.bars_above_ema = 0 

    def _calc_ema(self, current_price, prev_ema, period):
        if prev_ema is None: return current_price
        multiplier = 2 / (period + 1)
        return (current_price - prev_ema) * multiplier + prev_ema

    def process_event(self, event):
        if event.get("type") != "MARKET_DATA": return None
        symbol, timestamp, price, volume = event["symbol"], event["timestamp"], event["price"], event.get("volume", 0)

        self.prices.append(price)
        self.ema20 = self._calc_ema(price, self.ema20, self.ema_period)

        # update volume in O(1)
        if len(self.volumes) == self.vol_window:
            old_vol = self.volumes[0]
            self.sum_vol -= old_vol
            self.sum_sq_vol -= (old_vol ** 2)
        self.volumes.append(volume)
        self.sum_vol += volume
        self.sum_sq_vol += (volume ** 2)

        # update EMA-distance state in O(1)
        distance = price - self.ema20
        if len(self.ema_distances) == 60:
            old_dist = self.ema_distances[0]
            self.sum_dist -= old_dist
            self.sum_sq_dist -= (old_dist ** 2)
        self.ema_distances.append(distance)
        self.sum_dist += distance
        self.sum_sq_dist += (distance ** 2)

        # signal generation
        signal, allocation, loss_of_structure_level = "HOLD", 0.0, 0.0

        if len(self.prices) >= 20 and len(self.volumes) == self.vol_window and len(self.ema_distances) >= 20:
            
            # volume z-score
            mean_vol = self.sum_vol / self.vol_window
            var_vol = (self.sum_sq_vol - ((self.sum_vol ** 2) / self.vol_window)) / self.vol_window
            std_vol = np.sqrt(max(0, var_vol))
            vol_z_score = (volume - mean_vol) / std_vol if std_vol > 1e-8 else 0

            # EMA-distance volatility
            n_dist = len(self.ema_distances)
            var_dist = (self.sum_sq_dist - ((self.sum_dist ** 2) / n_dist)) / n_dist
            zone_std = np.sqrt(max(0, var_dist))
            
            pullback_zone_size = min(max(zone_std, price * 0.001), price * 0.003) 
            
            if price > self.ema20: self.bars_above_ema += 1
            else: self.bars_above_ema = max(0, self.bars_above_ema - 1)

            # pullback and rebound checks
            in_pullback_zone = (distance <= pullback_zone_size * 0.2) and (distance >= -pullback_zone_size)
            is_curling_up = (self.prices[-1] > self.prices[-2] + (price * 0.0002)) and (self.prices[-2] <= self.prices[-3])
            has_volume_spike = (vol_z_score >= self.z_score_threshold) or (volume > mean_vol * 1.8)
            
            loss_of_structure_level = self.ema20 - pullback_zone_size

            if (self.bars_above_ema >= 3) and in_pullback_zone and is_curling_up and has_volume_spike:
                signal, allocation = "BUY", 1.0 

        return {"type": "ORDER_SIGNAL", "symbol": symbol, "timestamp": timestamp, "signal": signal, "price": price, "allocation": allocation, "metadata": {"loss_of_structure_level": loss_of_structure_level}}