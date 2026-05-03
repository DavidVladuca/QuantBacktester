import logging
import json
import os
import numpy as np
from collections import deque
from dataclasses import dataclass
from council_zscore_arb import ZScoreArbStrategy
from council_momentum import MomentumEngineStrategy
from council_obi_flow import OBIFlowStrategy
from council_gatekeeper import Gatekeeper

@dataclass 
class PositionState:
    is_active: bool = False
    side: str = None      
    entry_price: float = 0.0
    bars_held: int = 0
    sponsor: str = None   
    dynamic_sl_pct: float = 0.0  
    dynamic_tp_pct: float = 0.0 
    # 🚨 NEW: Memory for position sizing (Critique #4)
    shares: int = 0

class MasterEnsemble:
    def __init__(self, target_symbol="NVDA", hedge_symbol="SMH"):
        # --- SETUP LOGGING ---
        self.logger = logging.getLogger("CouncilLogger")
        # self.logger.setLevel(logging.INFO)
        self.logger.setLevel(logging.CRITICAL)
        fh = logging.FileHandler('strategy_log.txt', mode='w', encoding='utf-8')
        formatter = logging.Formatter('%(message)s') 
        fh.setFormatter(formatter)
        
        if not self.logger.handlers:
            self.logger.addHandler(fh)
            
        self.logger.info(">>> Council Brain Initialized. Awaiting Events...")

        # --- LOAD CONFIGURATION ---
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(script_dir, "config.json")
        
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
        except FileNotFoundError:
            config = {"z_score_threshold": 2.0, "momentum_threshold": 3.0, "obi_threshold": 0.4, "regime_threshold": 0.5}

        z_thresh    = config.get("z_score_threshold", 2.0)
        mom_thresh  = config.get("momentum_threshold", 3.0)
        obi_thresh  = config.get("obi_threshold", 0.4)
        commission  = config.get("commission_rate", 0.0001)
        slippage    = config.get("slippage_rate", 0.0005)
        self.regime_vol_threshold = config.get("regime_threshold", 0.5)

        self.logger.info(f"⚙️ LOADED PARAMS: Z={z_thresh} | Mom={mom_thresh} | OBI={obi_thresh} | Regime Vol={self.regime_vol_threshold} | Commission={commission} | Slippage={slippage}")

        self.target_symbol = target_symbol
        self.hedge_symbol = hedge_symbol

        self.gatekeeper = Gatekeeper(target_symbol, max_spread_bps=15.0, commission_rate=commission, slippage_rate=slippage)
        self.z_score_arb = ZScoreArbStrategy(target_symbol, hedge_symbol, entry_threshold=z_thresh)
        self.momentum = MomentumEngineStrategy(target_symbol, vol_z_threshold=mom_thresh, volume_mult=1.0)
        self.obi_flow = OBIFlowStrategy(target_symbol, trigger_threshold=obi_thresh)
        
        self.position = PositionState()
        self.eventCount = 0  
        
        # 🚨 UPDATED: VOLATILITY SCALED RISK PARAMETERS
        self.sl_vol_multiplier = 2.0  
        self.tp_vol_multiplier = 4.0  
        self.min_risk_pct = 0.0025    
        self.max_hold_ticks = 15000
        
        self.exit_decay_threshold = 0.20
        self.entry_threshold = config.get("entry_threshold", 0.40)

        self.last_exit_time = 0
        self.cooldown_ms = 300000

        self.total_capital = config.get("total_capital", 100000.0)
        self.max_risk_per_trade_pct = config.get("max_risk_per_trade_pct", 0.01)
        
        # 🚨 UPDATED: MACRO REGIME TRACKER (Returns-Based)
        self.last_sample_time = 0
        self.last_sampled_price = None 
        self.rolling_returns = deque(maxlen=60) # Holds the last 60 minutes of % returns
        self.current_regime = "WARMUP"
        
        # Note: Because we are now measuring % returns, the threshold needs to be much smaller.
        # A typical 1-minute return standard deviation for a stock like NVDA is around 0.05% to 0.15%.
        # So your regime_vol_threshold in config should now be a percentage, like 0.10.

    def calculate_shares(self, entry_price, stop_loss_pct, confidence_score):
        # Prevent divide-by-zero errors
        if entry_price <= 0 or stop_loss_pct <= 0: 
            return 0
        
        # 1. Dollar Risk & Risk per Share
        dollar_risk = self.total_capital * self.max_risk_per_trade_pct
        risk_per_share = entry_price * stop_loss_pct
        
        # 2. Base Shares & Conviction Scaling
        base_shares = dollar_risk / risk_per_share
        adjusted_shares = base_shares * abs(confidence_score)
        
        # 🚨 UPDATED: Buying Power Constraint (Critique #2)
        # Assuming 1:1 margin requirement for short selling. 
        # If your broker requires 150% margin for shorts, this formula must be updated to (self.total_capital / 1.5) / entry_price
        max_shares_allowed = self.total_capital / entry_price
        
        return int(min(adjusted_shares, max_shares_allowed))

    def process_event(self, event):
        gk_vote = self.gatekeeper.process_event(event)
        zs_vote = self.z_score_arb.process_event(event)
        mo_vote = self.momentum.process_event(event)
        obi_vote = self.obi_flow.process_event(event)

        if event.get("symbol") != self.target_symbol: return None
        if not all([gk_vote, zs_vote, mo_vote, obi_vote]): return None

        bid_price = event.get("bid_price", 0)
        ask_price = event.get("ask_price", 0)
        price = event.get("price", 0)
        
        if bid_price == 0: bid_price = price
        if ask_price == 0: ask_price = price
        current_price = (bid_price + ask_price) / 2.0 
        timestamp = event["timestamp"]

        # 🚨 UPDATED: REGIME SAMPLING LOGIC (Returns-Based)
        # Sample the price every 60,000 milliseconds (1 minute)
        if timestamp - self.last_sample_time >= 60000:
            if self.last_sampled_price is not None:
                # Calculate the exact percentage return over the last minute
                pct_return = (current_price - self.last_sampled_price) / self.last_sampled_price
                self.rolling_returns.append(pct_return)
            
            self.last_sampled_price = current_price
            self.last_sample_time = timestamp
            
            # Calculate Regime if we have enough data (at least 30 mins to start guessing)
            if len(self.rolling_returns) >= 30:
                # Calculate Standard Deviation of the returns, multiply by 100 to make it a percentage
                current_vol_pct = np.std(self.rolling_returns) * 100 
                
                if current_vol_pct >= self.regime_vol_threshold:
                    self.current_regime = "TREND"
                else:
                    self.current_regime = "CHOP"


        # 🚨 UPDATED: INPUT CLAMPING & MASTER EQUATION (Critique #1)
        # We must clip the inputs at the source before they hit the Master Equation
        z_val = float(np.clip(zs_vote.get("confidence", 0.0), -1.0, 1.0))
        m_val = float(np.clip(mo_vote.get("confidence", 0.0), -1.0, 1.0))
        obi_val = float(np.clip(obi_vote.get("confidence", 0.0), -1.0, 1.0))

        # Veto Z-score signals that trade against the macro trend direction.
        # z_val < 0 = Z-score wants SHORT (spread above mean); z_val > 0 = wants LONG.
        # Only applied in TREND regime — in CHOP, mean reversion fires freely.
        if self.current_regime == "TREND" and len(self.rolling_returns) > 1:
            trend_direction = np.mean(self.rolling_returns)
            if trend_direction > 0 and z_val < 0:   # uptrend: block Z-score shorts
                z_val = 0.0
            elif trend_direction < 0 and z_val > 0:  # downtrend: block Z-score longs
                z_val = 0.0

        if self.current_regime == "TREND":
            z_weight, m_weight = 0.35, 0.65
        else:
            z_weight, m_weight = 0.65, 0.35

        raw_master_score = (z_val * z_weight) + (m_val * m_weight) + (obi_val * 0.2)
        master_score = float(np.clip(raw_master_score, -1.0, 1.0))
        
        ensemble_signal = "HOLD"
        
        # --- 2. POSITION MANAGEMENT ---
        if self.position.is_active:
            self.position.bars_held += 1
            
            if self.position.side == "LONG":
                pnl_pct = (bid_price - self.position.entry_price) / self.position.entry_price
            elif self.position.side == "SHORT":
                pnl_pct = (self.position.entry_price - ask_price) / self.position.entry_price

            exit_reason = "UNKNOWN"

            # 🚨 UPDATED: EXIT LOGIC A (Dynamic Risk Stops)
            if pnl_pct <= -self.position.dynamic_sl_pct:
                ensemble_signal = "EXIT"
                exit_reason = "STOP_LOSS"
            elif pnl_pct >= self.position.dynamic_tp_pct:
                ensemble_signal = "EXIT"
                exit_reason = "TAKE_PROFIT"
            elif self.position.bars_held > self.max_hold_ticks:
                ensemble_signal = "EXIT"
                exit_reason = "TIME_LIMIT"
                
            # 🚨 NEW: EXIT LOGIC B (Confidence-Based Decay)
            # If the overarching thesis dies, don't hold the bag. Get out.
            if ensemble_signal != "EXIT":
                thesis_decayed = False
                if self.position.side == "LONG" and master_score < self.exit_decay_threshold:
                    thesis_decayed = True
                elif self.position.side == "SHORT" and master_score > -self.exit_decay_threshold:
                    thesis_decayed = True

                if thesis_decayed:
                    # Prevent exiting into a toxic spread for a tiny decay loss
                    spread_cost_pct = (ask_price - bid_price) / current_price
                    if pnl_pct > 0 or pnl_pct < -(spread_cost_pct * 1.5):
                        ensemble_signal = "EXIT"
                        exit_reason = f"THESIS_DECAY ({master_score:.2f})"

            if ensemble_signal == "EXIT":
              #  self.logger.info(f"[{timestamp}] 🚪 EXITING {self.position.side} | Shares: {self.position.shares} | Actual PnL: {pnl_pct*100:.3f}% | Reason: {exit_reason}")
                self.last_exit_time = timestamp 
                
                exit_signal = "SELL_TO_CLOSE" if self.position.side == "LONG" else "BUY_TO_COVER"
                exit_price = bid_price if self.position.side == "LONG" else ask_price
                
                # 🚨 NEW: Capture the shares BEFORE wiping the position state
                exit_quantity = self.position.shares 
                
                # Reset state
                self.position = PositionState()
                
                return {
                    "type": "ORDER_SIGNAL", 
                    "symbol": self.target_symbol, 
                    "timestamp": timestamp, 
                    "signal": exit_signal, 
                    "price": exit_price,
                    "quantity": exit_quantity # 🚨 NEW: Send quantity to downstream executor
                }
            
        # --- 3. ENTRY TOURNAMENT (LONG & SHORT) ---
        elif not self.position.is_active:
            
            if timestamp - self.last_exit_time < self.cooldown_ms:
                return None 
            if gk_vote["signal"] == "VETO": return None 
            if self.current_regime == "WARMUP": return None # Don't trade until we know the weather

            thesis_direction = None
            sponsor = None

            if master_score >= self.entry_threshold:
                thesis_direction = "LONG"
                sponsor = "Z_SCORE_ARB" if (z_val * z_weight) >= (m_val * m_weight) else "MOMENTUM_ENGINE"
            elif master_score <= -self.entry_threshold:
                thesis_direction = "SHORT"
                sponsor = "Z_SCORE_ARB" if (z_val * z_weight) <= (m_val * m_weight) else "MOMENTUM_ENGINE"
            
            if not thesis_direction:
                return None
            
            # 🚨 NEW: Calculate Dynamic Risk for this specific entry
            current_vol_decimal = np.std(self.rolling_returns) if len(self.rolling_returns) > 1 else 0.001
            trade_sl = max(current_vol_decimal * self.sl_vol_multiplier, self.min_risk_pct)
            trade_tp = max(current_vol_decimal * self.tp_vol_multiplier, self.min_risk_pct * 2)

            # 🚨 NEW: Calculate position size based on risk and conviction
            entry_p = ask_price if thesis_direction == "LONG" else bid_price
            shares_to_trade = self.calculate_shares(entry_p, trade_sl, master_score)
            
            # If the math dictates 0 shares (or we don't have enough capital), abort the trade.
            if shares_to_trade <= 0:
                return None 

            # Execute immediately with dynamically calculated share quantity
            if thesis_direction == "LONG":
                self.position.is_active = True
                self.position.side = "LONG"
                self.position.entry_price = ask_price 
                self.position.sponsor = sponsor
                self.position.dynamic_sl_pct = trade_sl
                self.position.dynamic_tp_pct = trade_tp
                self.position.shares = shares_to_trade # 🚨 NEW: Track the size!
                
               # self.logger.info(f"🟢 LONG ENTRY | Score: {master_score:.3f} | Shares: {shares_to_trade} | Risk: -{trade_sl*100:.2f}% | Target: +{trade_tp*100:.2f}%")
                return {"type": "ORDER_SIGNAL", "symbol": self.target_symbol, "timestamp": timestamp, "signal": "BUY", "price": ask_price, "quantity": shares_to_trade} 
            
            elif thesis_direction == "SHORT":
                self.position.is_active = True
                self.position.side = "SHORT"
                self.position.entry_price = bid_price 
                self.position.sponsor = sponsor
                self.position.dynamic_sl_pct = trade_sl
                self.position.dynamic_tp_pct = trade_tp
                self.position.shares = shares_to_trade # 🚨 NEW: Track the size!
                
                # self.logger.info(f"🔴 SHORT ENTRY | Score: {master_score:.3f} | Shares: {shares_to_trade} | Risk: -{trade_sl*100:.2f}% | Target: +{trade_tp*100:.2f}%")
                return {"type": "ORDER_SIGNAL", "symbol": self.target_symbol, "timestamp": timestamp, "signal": "SELL", "price": bid_price, "quantity": shares_to_trade}
       
        return None