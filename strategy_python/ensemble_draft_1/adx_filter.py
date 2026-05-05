import numpy as np
from collections import deque

# Average Directional Index (ADX) filter for trend strength
class ADXFilter:
    def __init__(self, period=14):
        self.period = period
        # extra window size to stablize the ADX
        self.window = period * 3 
        self.highs = deque(maxlen=self.window)
        self.lows = deque(maxlen=self.window)
        self.closes = deque(maxlen=self.window)

    def update(self, high, low, close):
        self.highs.append(high)
        self.lows.append(low)
        self.closes.append(close)

    def calculate_adx(self):
        # we first fill the window
        if len(self.closes) < self.window:
            return None

        trs = [] # True Ranges (TR)
        pos_dms = [] # Positive Directional Movements (+DM)
        neg_dms = [] # Negative Directional Movements (-DM)

        # TR, +DM, -DM for the whole window
        for i in range(1, len(self.closes)):
            h = self.highs[i]
            l = self.lows[i]
            prev_c = self.closes[i-1]
            prev_h = self.highs[i-1]
            prev_l = self.lows[i-1]

            # TR -> volatility measurement
            tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
            trs.append(tr)

            # DM
            up_move = h - prev_h
            down_move = prev_l - l

            # only take in account dominant direction
            if up_move > down_move and up_move > 0:
                pos_dms.append(up_move)
            else:
                pos_dms.append(0)

            if down_move > up_move and down_move > 0:
                neg_dms.append(down_move)
            else:
                neg_dms.append(0)

        # Wilder smoothing for TR, +DM, -DM
        def wilders_smoothing(data, period):
            smoothed = [sum(data[:period])]
            for val in data[period:]:
                smoothed.append(smoothed[-1] - (smoothed[-1] / period) + val)
            return smoothed

        smoothed_tr = wilders_smoothing(trs, self.period)
        smoothed_pos_dm = wilders_smoothing(pos_dms, self.period)
        smoothed_neg_dm = wilders_smoothing(neg_dms, self.period)

        # Directional Indices (+DI and -DI)
        dxs = []
        for i in range(len(smoothed_tr)):
            if smoothed_tr[i] == 0:
                dxs.append(0)
                continue
            
            pos_di = 100 * (smoothed_pos_dm[i] / smoothed_tr[i])
            neg_di = 100 * (smoothed_neg_dm[i] / smoothed_tr[i])
            
            # Directional Index (DX)
            if (pos_di + neg_di) > 0:
                dx = 100 * abs(pos_di - neg_di) / (pos_di + neg_di)
            else:
                dx = 0
            dxs.append(dx)

        # ADX = Wilder smoothed average of DX
        first_adx = np.mean(dxs[:self.period])
        adx_vals = [first_adx]
        
        for dx in dxs[self.period:]:
            adx_vals.append((adx_vals[-1] * (self.period - 1) + dx) / self.period)
            
        return adx_vals[-1]