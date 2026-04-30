import json
from collections import deque
import statistics

class SMAStrategy:
    def __init__(self, fast_window=3, slow_window=25, target_vol=0.02): # removed trailing_stop_pct # new
        # rolling window setup 
        self.SLOW_WINDOW = slow_window
        self.FAST_WINDOW = fast_window
        self.price_history = deque(maxlen=self.SLOW_WINDOW) 

        # risk management parameters
        self.TARGET_VOL = target_vol # target volatility (2% daily)
        
        # strategy states
        self.prev_fast_sma = None
        self.prev_slow_sma = None
        
        # removed internal position/risk states # new

    def process_event(self, event):
        # extract the important fields
        if event.get("type") != "MARKET_DATA":
            return None

        timestamp = event.get("timestamp")
        price = event.get("price")
        symbol = event.get("symbol")

        # adding element to the rolling window
        self.price_history.append(price)

        signal = "HOLD" # default signal
        allocation = 0.0 # default allocation 
        
        if len(self.price_history) == self.SLOW_WINDOW:
            # converted to list so that we can slice it
            history_list = list(self.price_history)
            
            # calculate the simple moving average
            # slow_sma -> all 20 last prices
            slow_sma = sum(history_list) / self.SLOW_WINDOW
            # fast_sma -> only the last 5 prices
            fast_sma = sum(history_list[-self.FAST_WINDOW:]) / self.FAST_WINDOW

            # calculate volatility with standard deviation of the price history
            stdev = statistics.stdev(history_list)
            if price > 0:
                volatility_pct = stdev / price
            else:
                volatility_pct = 0.01 # in case of wrong reads, we avoid division by zero
            
            # high volatility -> smaller allocation, low volatility -> bigger allocation
            if volatility_pct > 0:
                dynamic_alloc = self.TARGET_VOL / volatility_pct
            else:
                dynamic_alloc = 1.0

            # clamp the allocation [10%, 100%]
            buy_allocation = max(0.1, min(1.0, dynamic_alloc))

            # continuous stance evaluation (replaced discrete crossover) # new
            if fast_sma > slow_sma: # new
                signal = "BUY" # new
                allocation = buy_allocation # new
            elif fast_sma < slow_sma: # new
                signal = "SELL" # new
                allocation = 1.0 # new

            # remember yesterday values (kept for continuity, though no longer used for crosses)
            self.prev_fast_sma = fast_sma
            self.prev_slow_sma = slow_sma

        response = {
            "type": "ORDER_SIGNAL",
            "symbol": symbol,
            "timestamp": timestamp,
            "signal": signal,
            "price": price,
            "allocation": allocation
        }

        return response