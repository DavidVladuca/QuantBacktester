class Gatekeeper:
    def __init__(self, target_symbol, max_spread_bps=10.0, commission_rate=0.0001, slippage_rate=0.0005):
        self.target_symbol = target_symbol
        self.max_spread_pct = max_spread_bps / 10000.0

        # Round-trip fee burden from the actual Portfolio fill model: 2 × (slippage + commission)
        self.round_trip_fee_pct = 2.0 * (slippage_rate + commission_rate)

        # Veto if total round-trip cost (spread + fees) exceeds 0.20%
        self.max_friction_pct = 0.0020

    def process_event(self, event):
        if event.get("type") != "MARKET_DATA" or event.get("symbol") != self.target_symbol:
            return None

        bid_price = event.get("bid_price", 0.0) 
        ask_price = event.get("ask_price", 0.0)
        bid_size = event.get("bid_size", 0.0)
        ask_size = event.get("ask_size", 0.0)
        timestamp = event["timestamp"]

        # 1. DATA INTEGRITY CHECK (The "Crossed Book" Defense)
        if bid_size == 0 or ask_size == 0 or bid_price >= ask_price or bid_price == 0:
            return self._veto_signal(timestamp, "INVALID_BOOK")

        # 2. SPREAD TOXICITY CHECK
        spread = ask_price - bid_price
        mid_price = (bid_price + ask_price) / 2.0
        spread_pct = spread / mid_price

        # 3. EXPECTED VALUE (EV) FRICTION GATE
        # Total round-trip cost as a fraction of mid: spread + Portfolio's actual fee model
        breakeven_pct = spread_pct + self.round_trip_fee_pct

        # 4. SIGNAL LOGIC
        signal = "SAFE"
        reason = "NORMAL"

        if spread_pct > self.max_spread_pct:
            signal = "VETO"
            reason = "SPREAD_TOO_WIDE"
        elif breakeven_pct > self.max_friction_pct:
            signal = "VETO"
            reason = f"FRICTION_TOO_HIGH_{breakeven_pct*100:.3f}%"

        return {
            "type": "RISK_SIGNAL",
            "symbol": self.target_symbol,
            "timestamp": timestamp,
            "signal": signal,
            "price": mid_price,
            "metadata": {
                "spread_bps": round(spread_pct * 10000, 2),
                "breakeven_pct": round(breakeven_pct * 100, 4), # Track this in logs!
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
            "metadata": {"spread_bps": 9999, "breakeven_pct": 9999, "reason": reason, "expert_name": "GATEKEEPER"}
        }