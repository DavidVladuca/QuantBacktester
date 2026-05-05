# Ensemble Active

## Concept

The final ensemble moved away from indicator voting and toward a smaller set of less-correlated experts. Instead of having many strategies look at the same price chart, each expert was meant to measure a different market dimension: relative value, momentum, liquidity, and microstructure flow.

The final version became a conservative NVDA-focused bot using SMH as a hedge/reference asset. The goal was to trade only when several independent conditions aligned, rather than forcing frequent trades.

## Active Council Members

### Gatekeeper

Risk and liquidity filter. It checks whether the bid/ask book is valid, whether there is liquidity on both sides, and whether spread plus estimated round-trip trading cost is acceptable. If friction is too high, it vetoes the trade.

### Z-Score Arbitrage

Relative-value expert using NVDA versus SMH. It tracks the rolling log-spread:

```text
spread = log(NVDA price) - log(SMH price)
```

Then it converts that spread into a z-score. The idea is to detect when NVDA is statistically stretched relative to SMH.

### Momentum Engine

Directional momentum expert. It looks at recent log returns inside a rolling time window, normalizes the move by realized volatility, adjusts confidence using volume, and smooths the final confidence with an EMA.

### OBI Flow

Order-book imbalance expert based on bid size versus ask size:

```text
OBI = (bid_size - ask_size) / (bid_size + ask_size)
```

This was implemented as a microstructure signal, but in the final ensemble it is effectively disabled. The master ensemble sets OBI confidence to `0.0`, so it no longer affects decisions.

## Final Decision Logic

The final ensemble combines mainly:

```text
Z-Score Arbitrage + Momentum Engine + Gatekeeper
```

The bot first updates both NVDA and SMH prices. It only considers trades on the target symbol, NVDA.

Before entry, it requires:

- Gatekeeper must not veto.
- Market regime must be out of warmup.
- Enough target, hedge, and volatility history must exist.
- Momentum must be strong enough.
- NVDA short-term trend must agree with NVDA longer-term trend.
- SMH short-term trend must agree with SMH longer-term trend.
- Master score must stay above the entry threshold for multiple events.
- Recent price movement must not be too extended, to avoid chasing.

The final implementation is long-only (but it supported short before). Although some expert scores can be negative, the active entry logic only opens long NVDA trades.

## Risk Management

The active ensemble includes more serious position management than the earlier drafts:

- Risk-based position sizing.
- Dynamic stop-loss based on recent volatility.
- Minimum risk floor.
- Maximum holding time.
- Cooldown after exits.
- Breakeven protection after a favorable move.
- Trailing stop based on giveback from best price.
- Confirmed reversal exit after repeated opposite master-score signals.

This made the system more realistic than the earlier indicator-council versions, even though it also made it much harder for trades to pass all filters.

## Process

After Draft 2, the main problem was still correlation. Even though the strategies had different names and roles, many of them were still reacting to the same short-term price behavior. The final draft tried to fix this by separating the experts by market dimension.

The new design used:

- **Relative value:** NVDA versus SMH spread.
- **Momentum:** directional return strength and volume.
- **Liquidity:** spread, fees, slippage, and book validity.
- **Microstructure:** bid/ask size imbalance, later disabled.

The move from a multi-stock portfolio idea to an NVDA/SMH pair made the design cleaner. Instead of trying to trade many unrelated assets, the system focused on one target asset and one related reference asset.

This version performed better structurally because it was designed for noisy intraday data rather than daily indicators. However, the practical results were still weak. The NVDA/SMH relationship was not strong enough to create reliable entries, the OBI signal did not add useful confirmation, and the remaining filters made the bot extremely conservative.

OBI likely failed because top-of-book size is noisy, easy to spoof, and incomplete compared with deeper order-book data. It also becomes useless when running on macro bar data without real bid/ask sizes. For that reason, the final master ensemble leaves OBI disabled.

Testing on 5-minute data reduced some noise, but grid search mostly improved results by reducing trades rather than finding a robust edge. After several tuning attempts, this draft was left as the active/default strategy mainly to validate the Java backtester, execution gateway, portfolio accounting, logging, and full event-driven pipeline.

## Accuracy Notes

- OBI is implemented but not active in `MasterEnsemble`.
- The final bot is long-only in the shown code.
- The active decision uses Z-score + momentum + gatekeeper, not a full four-member council.
- The regime logic is volatility-based `TREND` / `CHOP`, not ADX-based.
- The active timeframe logic is not pure tick-HFT; it processes events and uses rolling windows/buckets.

## Final Hyperparameters

While this was not necessarily the true optimal configuration, these were the best working values found after repeated tuning.

### `config.json`

```json
{
  "target_symbol": "NVDA",
  "hedge_symbol": "SMH",

  "z_score_threshold": 1.8,
  "momentum_threshold": 2.5,
  "obi_threshold": 0.25,
  "regime_threshold": 0.12,

  "entry_threshold": 0.45,
  "exit_decay_threshold": 0.12,
  "cooldown_ms": 900000,

  "commission_rate": 0.0001,
  "slippage_rate": 0.0005,

  "total_capital": 10000.0,
  "max_risk_per_trade_pct": 0.01
}
```

### Strategy-Level Parameters Used in the Final Code

#### Trading Pair

| Parameter | Value | Meaning |
|---|---:|---|
| `target_symbol` | `NVDA` | Main asset traded by the strategy. |
| `hedge_symbol` | `SMH` | Reference asset used by the Z-score arbitrage module. |

> Note: in the shown `MasterEnsemble` code, `target_symbol` and `hedge_symbol` are constructor arguments with defaults of `NVDA` and `SMH`. The config file contains the same values, but the shown constructor does not directly read these two fields from `config.json`.

#### Z-Score Arbitrage

| Parameter | Value | Meaning |
|---|---:|---|
| `entry_threshold` | `1.8` | Z-score threshold passed from `z_score_threshold`. |
| `exit_threshold` | `0.2` | Spread considered mean-reverted when absolute z-score falls near this level. |
| `window_ms` | `14,400,000` | Rolling spread history window, equal to 4 hours. |
| `bucket_interval_ms` | `300,000` | Spread sampling interval, equal to 5 minutes. |

#### Momentum Engine

| Parameter | Value | Meaning |
|---|---:|---|
| `vol_z_threshold` | `2.5` | Momentum normalization threshold passed from `momentum_threshold`. |
| `window_ms` | `1,800,000` | Rolling momentum window, equal to 30 minutes. |
| `volume_mult` | `1.0` | Volume multiplier used when scaling momentum confidence. |
| `ema_alpha` | `0.35` | Smoothing factor for the momentum confidence EMA. |
| `lookback_steps` | `10` | Maximum number of recent steps used for short-term momentum return calculation. |

#### OBI Flow

| Parameter | Value | Meaning |
|---|---:|---|
| `obi_threshold` | `0.25` | Intended OBI trigger threshold from config. |
| `tau_ms` | `300,000` | Default time constant for OBI EMA smoothing. |

> Note: OBI is implemented in `council_obi_flow.py`, but it is disabled in the shown final `MasterEnsemble`. The code sets `obi_vote = {"confidence": 0.0}` and `self.obi_flow = None`, so OBI does not affect final decisions.

#### Gatekeeper / Execution Friction

| Parameter | Value | Meaning |
|---|---:|---|
| `max_spread_bps` | `15.0` | Maximum allowed spread in basis points, passed when creating the `Gatekeeper`. |
| `commission_rate` | `0.0001` | Commission assumption used for trading-cost estimation. |
| `slippage_rate` | `0.0005` | Slippage assumption used for trading-cost estimation. |
| `round_trip_cost_pct` | `0.0012` | Estimated entry + exit cost: `2 * (commission + slippage)`. |
| `max_friction_pct` | `0.0020` | Hard cap for total allowed trading friction, equal to 0.20%. |


