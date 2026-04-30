class Gatekeeper:
    def __init__(self, target_symbol, max_spread_bps=10.0):
        self.target_symbol = target_symbol
        # BPS (Basis Points). 1 bps = 0.01%. 
        # 5 bps on a $100 stock is a $0.05 spread.
        self.max_spread_pct = max_spread_bps / 10000.0

    def process_event(self, event):
        if event.get("type") != "MARKET_DATA" or event.get("symbol") != self.target_symbol:
            return None

        bid_price = event.get("bid_price", 0.0)
        ask_price = event.get("ask_price", 0.0)
        bid_size = event.get("bid_size", 0.0)
        ask_size = event.get("ask_size", 0.0)
        timestamp = event["timestamp"]

        # 1. DATA INTEGRITY CHECK (The "Crossed Book" Defense)
        # If the book is empty, or the bid is higher than the ask (bad data tick), VETO.
        if bid_size == 0 or ask_size == 0 or bid_price >= ask_price or bid_price == 0:
            return self._veto_signal(timestamp, "INVALID_BOOK")

        # 2. SPREAD TOXICITY CHECK
        # Calculate spread as a percentage of the asset's price 
        spread = ask_price - bid_price
        mid_price = (bid_price + ask_price) / 2.0
        spread_pct = spread / mid_price

        # 3. SIGNAL LOGIC
        signal = "SAFE"
        reason = "NORMAL"

        if spread_pct > self.max_spread_pct:
            signal = "VETO"
            reason = "SPREAD_TOO_WIDE"

        return {
            "type": "RISK_SIGNAL",
            "symbol": self.target_symbol,
            "timestamp": timestamp,
            "signal": signal,
            "price": mid_price,
            "metadata": {
                "spread_bps": round(spread_pct * 10000, 2),
                "reason": reason,
                "expert_name": "GATEKEEPER"
            }
        }

    def _veto_signal(self, timestamp, reason):
        return {
            "type": "RISK_SIGNAL",
            "symbol": self.target_symbol,
            "timestamp": timestamp,
            "signal": "VETO",
            "price": 0.0,
            "metadata": {"spread_bps": 9999, "reason": reason, "expert_name": "GATEKEEPER"}
        }