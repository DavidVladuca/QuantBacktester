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

class MasterEnsemble:
    def __init__(self, target_symbol="NVDA", hedge_symbol="SMH"):
        # --- SETUP LOGGING ---
        self.logger = logging.getLogger("CouncilLogger")
        self.logger.setLevel(logging.INFO)
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

        z_thresh = config.get("z_score_threshold", 2.0)
        mom_thresh = config.get("momentum_threshold", 3.0)
        obi_thresh = config.get("obi_threshold", 0.4)
        
        # 🚨 NEW: Volatility Threshold (Standard Deviation in dollars)
        self.regime_vol_threshold = config.get("regime_threshold", 0.5) 

        self.logger.info(f"⚙️ LOADED PARAMS: Z={z_thresh} | Mom={mom_thresh} | OBI={obi_thresh} | Regime Vol={self.regime_vol_threshold}")

        self.target_symbol = target_symbol
        self.hedge_symbol = hedge_symbol
        
        self.gatekeeper = Gatekeeper(target_symbol, max_spread_bps=5.0)
        self.z_score_arb = ZScoreArbStrategy(target_symbol, hedge_symbol, entry_threshold=z_thresh)
        self.momentum = MomentumEngineStrategy(target_symbol, vol_z_threshold=mom_thresh, volume_mult=2.0)
        self.obi_flow = OBIFlowStrategy(target_symbol, trigger_threshold=obi_thresh)
        
        self.position = PositionState()
        self.eventCount = 0  
        
        self.stop_loss_pct = 0.01   
        self.take_profit_pct = 0.02 
        self.max_hold_ticks = 15000 
        
        self.last_exit_time = 0
        self.cooldown_ms = 300000 
        
        # 🚨 NEW: MACRO REGIME TRACKER
        self.last_sample_time = 0
        self.rolling_prices = deque(maxlen=60) # Holds the last 60 minutes
        self.current_regime = "WARMUP"

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

        # 🚨 NEW: REGIME SAMPLING LOGIC
        # Sample the price every 60,000 milliseconds (1 minute)
        if timestamp - self.last_sample_time >= 60000:
            self.rolling_prices.append(current_price)
            self.last_sample_time = timestamp
            
            # Calculate Regime if we have enough data (at least 30 mins to start guessing)
            if len(self.rolling_prices) >= 30:
                current_vol = np.std(self.rolling_prices)
                if current_vol >= self.regime_vol_threshold:
                    self.current_regime = "TREND"
                else:
                    self.current_regime = "CHOP"

        # --- DIAGNOSTIC LOGGING ---
        self.eventCount += 1
        if self.eventCount % 50000 == 0: 
            self.logger.info(f"--- COUNCIL STATUS [{timestamp}] ---")
            self.logger.info(f"MACRO REGIME: {self.current_regime} (Vol: {np.std(self.rolling_prices) if len(self.rolling_prices) > 1 else 0:.3f})")
            self.logger.info(f"Gatekeeper: {gk_vote['signal']}")
            self.logger.info(f"Z-Score: {zs_vote['metadata']['z_score']}")
            self.logger.info(f"Momentum: {mo_vote['metadata']['momentum_z_score']}") 
            self.logger.info(f"--------------------------------------")
        
        ensemble_signal = "HOLD"
        
        # --- 2. POSITION MANAGEMENT ---
        if self.position.is_active:
            self.position.bars_held += 1
            
            if self.position.side == "LONG":
                pnl_pct = (bid_price - self.position.entry_price) / self.position.entry_price
            elif self.position.side == "SHORT":
                pnl_pct = (self.position.entry_price - ask_price) / self.position.entry_price

            # EXIT LOGIC A: Hard Risk Stops
            if pnl_pct <= -self.stop_loss_pct or pnl_pct >= self.take_profit_pct or self.position.bars_held > self.max_hold_ticks:
                ensemble_signal = "EXIT"
                
            # EXIT LOGIC B: Thesis Invalidated 
            # Note: We ONLY listen to the sponsor that got us into the trade
            elif (self.position.sponsor == "Z_SCORE_ARB" and zs_vote["signal"] == "EXIT") or \
                 (self.position.sponsor == "MOMENTUM_ENGINE" and mo_vote["signal"] == "EXIT"):
                
                spread_cost_pct = (ask_price - bid_price) / current_price
                if pnl_pct > 0 or pnl_pct < -(spread_cost_pct * 1.5):
                    ensemble_signal = "EXIT"

            if ensemble_signal == "EXIT":
                self.logger.info(f"[{timestamp}] 🚪 EXITING {self.position.side} | Actual PnL: {pnl_pct*100:.3f}% | Reason: {self.position.sponsor} or Risk")
                self.last_exit_time = timestamp 
                
                exit_signal = "SELL_TO_CLOSE" if self.position.side == "LONG" else "BUY_TO_COVER"
                exit_price = bid_price if self.position.side == "LONG" else ask_price
                
                self.position = PositionState()
                return {"type": "ORDER_SIGNAL", "symbol": self.target_symbol, "timestamp": timestamp, "signal": exit_signal, "price": exit_price}
            
        # --- 3. ENTRY TOURNAMENT (LONG & SHORT) ---
        elif not self.position.is_active:
            
            if timestamp - self.last_exit_time < self.cooldown_ms:
                return None 
            if gk_vote["signal"] == "VETO": return None 
            if self.current_regime == "WARMUP": return None # Don't trade until we know the weather

            thesis_direction = None
            sponsor = None

            # 🚨 NEW: TRAFFIC LIGHT ROUTING
            if self.current_regime == "CHOP":
                # Only listen to Mean Reversion
                if zs_vote["signal"] == "BUY":
                    thesis_direction = "LONG"
                    sponsor = "Z_SCORE_ARB"
                elif zs_vote["signal"] == "SELL":
                    thesis_direction = "SHORT"
                    sponsor = "Z_SCORE_ARB"
                    
            elif self.current_regime == "TREND":
                # Only listen to Momentum Breakouts
                if mo_vote["signal"] == "BUY":
                    thesis_direction = "LONG"
                    sponsor = "MOMENTUM_ENGINE"
                elif mo_vote["signal"] == "SELL":
                    thesis_direction = "SHORT"
                    sponsor = "MOMENTUM_ENGINE"
            
            # HIERARCHY LEVEL 2: Execution Fuel (OBI must confirm the final push)
            if thesis_direction == "LONG":
                if obi_vote["signal"] == "BUY":
                    self.position.is_active = True
                    self.position.side = "LONG"
                    self.position.entry_price = ask_price 
                    self.position.sponsor = sponsor
                    return {"type": "ORDER_SIGNAL", "symbol": self.target_symbol, "timestamp": timestamp, "signal": "BUY", "price": ask_price}
            
            elif thesis_direction == "SHORT":
                if obi_vote["signal"] == "SELL":
                    self.position.is_active = True
                    self.position.side = "SHORT"
                    self.position.entry_price = bid_price 
                    self.position.sponsor = sponsor
                    return {"type": "ORDER_SIGNAL", "symbol": self.target_symbol, "timestamp": timestamp, "signal": "SELL", "price": bid_price}

        return None