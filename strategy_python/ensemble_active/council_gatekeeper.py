class Gatekeeper:
    def __init__(self, target_symbol, max_spread_bps=10.0, commission_rate=0.0001, slippage_rate=0.0005):
        self.target_symbol = target_symbol
        self.max_spread_pct = max_spread_bps / 10000.0

        # round-trip cost = entry + exit
        self.round_trip_fee_pct = 2.0 * (slippage_rate + commission_rate)

        # friction cap (max allowed friction to trade)
        self.max_friction_pct = 0.0020  # 0.20%

    def process_event(self, event):
        if event.get("type") != "MARKET_DATA" or event.get("symbol") != self.target_symbol:
            return None

        timestamp = event["timestamp"]

        bid_price = event.get("bid_price", 0.0)
        ask_price = event.get("ask_price", 0.0)
        bid_size  = event.get("bid_size", 0.0)
        ask_size  = event.get("ask_size", 0.0)
        price     = event.get("price", 0.0)

        # macro data (missing book) checks
        if bid_price == 0.0 and ask_price == 0.0:
            return {
                "type": "RISK_SIGNAL",
                "symbol": self.target_symbol,
                "timestamp": timestamp,
                "signal": "SAFE",
                "price": price,
                "metadata": {
                    "mode": "MACRO",
                    "reason": "NO_MICROSTRUCTURE"
                }
            }

        # micro data (with book) checks
        if bid_price <= 0 or ask_price <= 0 or bid_price >= ask_price:
            return self._veto_signal(timestamp, "INVALID_BOOK")

        if bid_size == 0 or ask_size == 0:
            return self._veto_signal(timestamp, "ZERO_LIQUIDITY")

        # spread
        spread = ask_price - bid_price
        mid_price = (bid_price + ask_price) / 2.0
        spread_pct = spread / mid_price

        # total friction
        breakeven_pct = spread_pct + self.round_trip_fee_pct

        # gatekeeper logic
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
                "mode": "MICRO",
                "spread_bps": round(spread_pct * 10000, 2),
                "breakeven_pct": round(breakeven_pct * 100, 4),
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
            "metadata": {
                "mode": "MICRO",
                "reason": reason,
                "spread_bps": 9999,
                "breakeven_pct": 9999,
                "expert_name": "GATEKEEPER"
            }
        }