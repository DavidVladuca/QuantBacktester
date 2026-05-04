import logging
import json
import os
import numpy as np
from collections import deque
from dataclasses import dataclass
from Try3.council_zscore_arb import ZScoreArbStrategy
from Try3.council_momentum import MomentumEngineStrategy
from Try3.council_obi_flow import OBIFlowStrategy
from Try3.council_gatekeeper import Gatekeeper

@dataclass 
class PositionState:
    is_active: bool = False
    side: str = None      
    entry_price: float = 0.0
    bars_held: int = 0
    sponsor: str = None   
    dynamic_sl_pct: float = 0.0  
    dynamic_tp_pct: float = 0.0 
    shares: int = 0

    best_price: float = 0.0
    reversal_count: int = 0

    # NEW: once a trade has moved enough in our favor,
    # we no longer allow it to become a full loser.
    breakeven_armed: bool = False

class MasterEnsemble:
    def __init__(self, target_symbol="NVDA", hedge_symbol="SMH"):
        # setup logging
        self.logger = logging.getLogger("CouncilLogger")
        self.logger.setLevel(logging.INFO)
        fh = logging.FileHandler('strategy_log.txt', mode='w', encoding='utf-8')
        formatter = logging.Formatter('%(message)s') 
        fh.setFormatter(formatter)
        
        if not self.logger.handlers:
            self.logger.addHandler(fh)
            
        self.logger.info(">>> Council Brain Initialized. Awaiting Events...")

        # configuration
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        config_path = os.path.join(project_root, "config.json")

        try:
            with open(config_path, "r") as f:
                config = json.load(f)
        except FileNotFoundError:
            config = {
                "z_score_threshold": 2.0,
                "momentum_threshold": 3.0,
                "obi_threshold": 0.4,
                "regime_threshold": 0.5
            }

        z_thresh = config.get("z_score_threshold", 2.0)
        mom_thresh = config.get("momentum_threshold", 3.0)
        obi_thresh = config.get("obi_threshold", 0.4)
        commission = config.get("commission_rate", 0.0001)
        slippage = config.get("slippage_rate", 0.0005)
        self.regime_vol_threshold = config.get("regime_threshold", 0.5)

        self.logger.info(f"-> LOADED PARAMS: Z={z_thresh} | Mom={mom_thresh} | OBI={obi_thresh} | Regime Vol={self.regime_vol_threshold} | Commission={commission} | Slippage={slippage}")

        self.target_symbol = target_symbol
        self.hedge_symbol = hedge_symbol

        self.gatekeeper = Gatekeeper(target_symbol, max_spread_bps=15.0, commission_rate=commission, slippage_rate=slippage)
        self.z_score_arb = ZScoreArbStrategy(target_symbol, hedge_symbol, entry_threshold=z_thresh)
        self.momentum = MomentumEngineStrategy(target_symbol, vol_z_threshold=mom_thresh, volume_mult=1.0)
        self.obi_flow = None
        
        self.position = PositionState()
        self.eventCount = 0  

        self.score_history = deque(maxlen=3)

        # extra filters to avoid chasing exhausted moves
        self.price_history = deque(maxlen=30)
        self.hedge_price_history = deque(maxlen=30)
        self.momentum_history = deque(maxlen=3)
        
        self.sl_vol_multiplier = 3.0

        # TP is not the main exit (winners should run)
        self.tp_vol_multiplier = 8.0

        self.min_risk_pct = 0.0075
        self.max_hold_bars = 78
        self.min_hold_bars = 4  

        self.trailing_vol_multiplier = 2.5
        self.min_trail_pct = 0.0060
                
        self.exit_decay_threshold = config.get("exit_decay_threshold", 0.12)
        self.entry_threshold = config.get("entry_threshold", 0.40)

        self.last_exit_time = 0
        self.cooldown_ms = config.get("cooldown_ms", 900000)

        self.round_trip_cost_pct = 2.0 * (commission + slippage)

        self.total_capital = config.get("total_capital", 10000.0)
        self.max_risk_per_trade_pct = config.get("max_risk_per_trade_pct", 0.01)
        
        # macro regime tracking
        self.last_sample_time = 0
        self.last_sampled_price = None 
        self.rolling_returns = deque(maxlen=60) 
        self.current_regime = "WARMUP"
        
    def log(self, msg):
        self.logger.info(msg)

    def calculate_shares(self, entry_price, stop_loss_pct, confidence_score):
        # prevent divide-by-zero errors
        if entry_price <= 0 or stop_loss_pct <= 0: 
            return 0
        
        # risks
        dollar_risk = self.total_capital * self.max_risk_per_trade_pct
        risk_per_share = entry_price * stop_loss_pct
        
        # shares based on risk + confidence
        base_shares = dollar_risk / risk_per_share
        adjusted_shares = base_shares * abs(confidence_score)
        
        max_shares_allowed = self.total_capital / entry_price
        
        return int(min(adjusted_shares, max_shares_allowed))

    def process_event(self, event):
        gk_vote = self.gatekeeper.process_event(event)
        zs_vote = self.z_score_arb.process_event(event)
        mo_vote = self.momentum.process_event(event)
        obi_vote = {"confidence": 0.0}

        symbol = event.get("symbol")
        raw_price = event.get("price", 0)

        if symbol == self.hedge_symbol and raw_price > 0:
            self.hedge_price_history.append(raw_price)

        if symbol != self.target_symbol:
            return None

        if not all([gk_vote, zs_vote, mo_vote, obi_vote]):
            return None

        bid_price = event.get("bid_price", 0)
        ask_price = event.get("ask_price", 0)
        price = event.get("price", 0)
        
        if bid_price == 0: bid_price = price
        if ask_price == 0: ask_price = price
        current_price = (bid_price + ask_price) / 2.0 
        timestamp = event["timestamp"]
        self.price_history.append(current_price)

        # regime sampling
        if timestamp - self.last_sample_time >= 300000:
            if self.last_sampled_price is not None:
                pct_return = (current_price - self.last_sampled_price) / self.last_sampled_price
                self.rolling_returns.append(pct_return)
            
            self.last_sampled_price = current_price
            self.last_sample_time = timestamp
            
            if len(self.rolling_returns) >= 10:
                current_vol_pct = np.std(self.rolling_returns) * 100 
                
                if current_vol_pct >= self.regime_vol_threshold:
                    self.current_regime = "TREND"
                else:
                    self.current_regime = "CHOP"


        # input clamping + master score calculation
        z_val = float(np.clip(zs_vote.get("confidence", 0.0), -1.0, 1.0))
        m_val = float(np.clip(mo_vote.get("confidence", 0.0), -1.0, 1.0))
        self.momentum_history.append(m_val)
        self.log(f"[DEBUG] momentum={m_val:.3f}")
        obi_val = float(np.clip(obi_vote.get("confidence", 0.0), -1.0, 1.0))

        # veto logic
        if self.current_regime == "TREND" and len(self.rolling_returns) > 1:
            trend_direction = np.mean(self.rolling_returns)
            if trend_direction > 0 and z_val < 0:   # uptrend -> block Z-score shorts
                z_val = 0.0
            elif trend_direction < 0 and z_val > 0:  # downtrend -> block Z-score longs
                z_val = 0.0

        if self.current_regime == "TREND":
            z_weight, m_weight = 0.35, 0.65
        else:
            z_weight, m_weight = 0.65, 0.35

        raw_master_score = (z_val * z_weight) + (m_val * m_weight)
        master_score = float(np.clip(raw_master_score, -1.0, 1.0))
        self.log(
            f"[PIPE] ts={timestamp} | regime={self.current_regime} | "
            f"z={z_val:.2f} m={m_val:.2f} score={master_score:.2f} | "
            f"entry_th={self.entry_threshold}"
        )

        self.score_history.append(master_score)
        
        ensemble_signal = "HOLD"
        
        # POSITION MANAGEMENT!!!
        if self.position.is_active:
            self.position.bars_held += 1

            current_vol_decimal = np.std(self.rolling_returns) if len(self.rolling_returns) > 1 else 0.001
            trailing_stop_pct = max(current_vol_decimal * self.trailing_vol_multiplier, self.min_trail_pct)

            if self.position.side == "LONG":
                if self.position.best_price <= 0:
                    self.position.best_price = self.position.entry_price

                self.position.best_price = max(self.position.best_price, bid_price)

                pnl_pct = (bid_price - self.position.entry_price) / self.position.entry_price
                favorable_move = (self.position.best_price - self.position.entry_price) / self.position.entry_price
                giveback = (self.position.best_price - bid_price) / self.position.entry_price

            elif self.position.side == "SHORT":
                if self.position.best_price <= 0:
                    self.position.best_price = self.position.entry_price

                self.position.best_price = min(self.position.best_price, ask_price)

                pnl_pct = (self.position.entry_price - ask_price) / self.position.entry_price
                favorable_move = (self.position.entry_price - self.position.best_price) / self.position.entry_price
                giveback = (ask_price - self.position.best_price) / self.position.entry_price

            else:
                return None

            ensemble_signal = "HOLD"
            exit_reason = "UNKNOWN"

            if pnl_pct <= -self.position.dynamic_sl_pct:
                ensemble_signal = "EXIT"
                exit_reason = "STOP_LOSS"

            if favorable_move >= self.position.dynamic_sl_pct:
                self.position.breakeven_armed = True

            if (
                ensemble_signal != "EXIT" and
                self.position.breakeven_armed and
                self.position.bars_held >= self.min_hold_bars and
                pnl_pct <= self.round_trip_cost_pct
            ):
                ensemble_signal = "EXIT"
                exit_reason = f"BREAKEVEN_PROTECT pnl={pnl_pct*100:.2f}%"

            # trailing stop
            if (
                ensemble_signal != "EXIT" and
                self.position.bars_held >= self.min_hold_bars and
                favorable_move >= self.position.dynamic_sl_pct and
                giveback >= trailing_stop_pct
            ):
                ensemble_signal = "EXIT"
                exit_reason = f"TRAILING_STOP giveback={giveback*100:.2f}%"

            # time exit
            elif self.position.bars_held >= self.max_hold_bars:
                ensemble_signal = "EXIT"
                exit_reason = "TIME_LIMIT"

            # strong reversal exit
            if ensemble_signal != "EXIT" and self.position.bars_held >= self.min_hold_bars:
                exit_threshold = 0.20

                opposite_reversal = False
                if self.position.side == "LONG" and master_score < -exit_threshold:
                    opposite_reversal = True
                elif self.position.side == "SHORT" and master_score > exit_threshold:
                    opposite_reversal = True

                if opposite_reversal:
                    self.position.reversal_count += 1
                else:
                    self.position.reversal_count = 0

                if self.position.reversal_count >= 2:
                    ensemble_signal = "EXIT"
                    exit_reason = f"CONFIRMED_REVERSAL ({master_score:.2f})"

            if ensemble_signal == "EXIT":
                self.log(
                    f"[EXIT] {self.position.side} | pnl={pnl_pct*100:.2f}% | "
                    f"reason={exit_reason} | held={self.position.bars_held} | "
                    f"best={self.position.best_price:.2f}"
                )

                self.last_exit_time = timestamp 

                exit_signal = "SELL_TO_CLOSE" if self.position.side == "LONG" else "BUY_TO_COVER"
                exit_price = bid_price if self.position.side == "LONG" else ask_price
                exit_quantity = self.position.shares 

                self.position = PositionState()
                self.score_history.clear()

                return {
                    "type": "ORDER_SIGNAL", 
                    "symbol": self.target_symbol, 
                    "timestamp": timestamp, 
                    "signal": exit_signal, 
                    "price": exit_price,
                    "quantity": exit_quantity
                }
                
        
        # ENTRY LOGIC (long + short) !!!
        elif not self.position.is_active:
            
            if timestamp - self.last_exit_time < self.cooldown_ms:
                self.log("[SKIP] COOLDOWN active")
                return None 

            if gk_vote["signal"] == "VETO":
                self.log(f"[SKIP] GATEKEEPER veto | reason={gk_vote['metadata'].get('reason')}")
                return None 

            if self.current_regime == "WARMUP":
                self.log(f"[SKIP] WARMUP | returns={len(self.rolling_returns)}")
                return None

            if len(self.price_history) < 20 or len(self.hedge_price_history) < 20 or len(self.rolling_returns) < 20:
                self.log(
                    f"[SKIP] not enough filter history | "
                    f"prices={len(self.price_history)} hedge={len(self.hedge_price_history)} returns={len(self.rolling_returns)}"
                )
                return None

            prices = list(self.price_history)
            hedge_prices = list(self.hedge_price_history)

            fast_sma = float(np.mean(prices[-5:]))
            slow_sma = float(np.mean(prices[-20:]))

            hedge_fast_sma = float(np.mean(hedge_prices[-5:]))
            hedge_slow_sma = float(np.mean(hedge_prices[-20:]))

            trend_direction = float(np.mean(self.rolling_returns))

            recent_3bar_return = (prices[-1] - prices[-4]) / prices[-4]
            current_vol_decimal = float(np.std(self.rolling_returns)) if len(self.rolling_returns) > 1 else 0.001
            max_chase_pct = max(current_vol_decimal * 2.0, 0.004)

            momentum_threshold = 0.60

            thesis_direction = None
            sponsor = None

            long_confirmed = (
                trend_direction > 0 and
                fast_sma > slow_sma and
                hedge_fast_sma > hedge_slow_sma and
                m_val >= momentum_threshold and
                master_score >= self.entry_threshold and
                len(self.score_history) == 3 and
                all(s >= self.entry_threshold for s in self.score_history) and
                recent_3bar_return <= max_chase_pct
            )

            self.log(
                f"[ENTRY CHECK] score={master_score:.2f} | m={m_val:.2f} | z={z_val:.2f} | "
                f"trend_dir={trend_direction:.5f} | "
                f"nvda_fast={fast_sma:.2f} nvda_slow={slow_sma:.2f} | "
                f"smh_fast={hedge_fast_sma:.2f} smh_slow={hedge_slow_sma:.2f} | "
                f"3bar_ret={recent_3bar_return*100:.2f}% max_chase={max_chase_pct*100:.2f}% | "
                f"long={long_confirmed}"
            )

            if long_confirmed:
                thesis_direction = "LONG"
                sponsor = "MOMENTUM_ENGINE"
            else:
                return None

            current_vol_decimal = np.std(self.rolling_returns) if len(self.rolling_returns) > 1 else 0.001
            trade_sl = max(current_vol_decimal * self.sl_vol_multiplier, self.min_risk_pct)
            trade_tp = max(current_vol_decimal * self.tp_vol_multiplier, self.min_risk_pct * 2)

            entry_p = ask_price
            shares_to_trade = self.calculate_shares(entry_p, trade_sl, master_score)

            self.log(
                f"[SIZE] entry={entry_p:.2f} | sl={trade_sl:.4f} | "
                f"score={master_score:.2f} | shares={shares_to_trade}"
            )

            if shares_to_trade <= 0:
                self.log("[SKIP] shares=0 → trade blocked")
                return None

            self.position.is_active = True
            self.position.side = "LONG"
            self.position.entry_price = ask_price
            self.position.best_price = ask_price
            self.position.sponsor = sponsor
            self.position.dynamic_sl_pct = trade_sl
            self.position.dynamic_tp_pct = trade_tp
            self.position.shares = shares_to_trade

            self.log(
                f"[EXECUTE] LONG | price={ask_price:.2f} | "
                f"shares={shares_to_trade} | score={master_score:.2f}"
            )

            return {
                "type": "ORDER_SIGNAL",
                "symbol": self.target_symbol,
                "timestamp": timestamp,
                "signal": "BUY",
                "price": ask_price,
                "quantity": shares_to_trade
            }