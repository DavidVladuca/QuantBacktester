import math

class OBIFlowStrategy:
    def __init__(self, target_symbol, tau_ms=2000, trigger_threshold=0.4):
        self.target_symbol = target_symbol
        # tau_ms is the "half-life" of the memory in milliseconds. 
        # 2000ms (2 seconds) means order book walls must persist to move the needle.
        self.tau_ms = tau_ms
        self.trigger_threshold = trigger_threshold
        
        # State tracking
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

        # 2. TIME-WEIGHTED EXPONENTIAL SMOOTHING (The Anti-Spoofing Filter)
        if self.obi_ema is None or self.last_timestamp is None:
            self.obi_ema = raw_obi
            self.last_timestamp = timestamp
        else:
            # Calculate time elapsed in milliseconds since the last quote
            dt = max(0, timestamp - self.last_timestamp)
            
            # Time-decay alpha. 
            # If dt is tiny (e.g., 1ms flash spoof), alpha is near 0 -> EMA ignores it.
            # If dt is large (e.g., wall sat there for 1000ms), alpha grows -> EMA updates.
            alpha = 1.0 - math.exp(-dt / self.tau_ms)
            
            self.obi_ema = raw_obi * alpha + self.obi_ema * (1.0 - alpha)
            self.last_timestamp = timestamp

        # 3. SIGNAL LOGIC
        signal = "HOLD"
        
        # We only trigger if the SMOOTHED imbalance is dominant.
        if self.obi_ema >= self.trigger_threshold:
            signal = "BUY"
        elif self.obi_ema <= -self.trigger_threshold:
            signal = "SELL"

        return {
            "type": "ORDER_SIGNAL",
            "symbol": self.target_symbol,
            "timestamp": timestamp,
            "signal": signal,
            "price": price,
            "metadata": {
                "raw_obi": round(raw_obi, 4),
                "ema_obi": round(self.obi_ema, 4),
                "expert_name": "OBI_FLOW"
            }
        }