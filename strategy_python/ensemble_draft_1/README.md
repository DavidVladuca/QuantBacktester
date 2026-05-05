# Ensemble Draft 1

## Concept

The first idea was to build a “council” of well-known technical indicators. Each indicator would evaluate the same market event and produce a directional opinion. If enough members agreed, the ensemble would execute the consensus action.

The original assumption was that combining several popular indicators would make the signal more reliable. In practice, this was too naive: indicators are often correlated, noisy, and regime-dependent. A majority vote does not automatically create edge.

## Council Members

### SMA Strategy
Trend-following strategy based on fast and slow simple moving averages. It buys when the fast average is above the slow average and sells when the fast average drops below it.

### MACD Strategy
Momentum strategy using exponential moving averages. It buys when the MACD line is above the signal line and sells when momentum turns bearish.

### RSI Strategy
Mean-reversion strategy based on oversold/overbought conditions. It buys when RSI shows oversold behavior, optionally requiring the broader trend to still be positive.

### Bollinger Strategy
Mean-reversion strategy using Bollinger Bands. It buys when price falls below the lower band and sells when price rises above the upper band.

### Pullback Strategy
Trend-continuation strategy. It looks for a bullish trend where price temporarily pulls back near the slow moving average before continuing upward.

### VWAP Strategy
Intraday trend/pullback strategy. It compares price to session VWAP and buys when price remains above VWAP in an upward trend, while selling on VWAP breakdowns.

### ADX Filter
Regime filter used to estimate trend strength. It was introduced because not every strategy should have equal voting power in every market condition.

## Regime Logic

The ADX filter was used to split the market into rough regimes:

- **Low-trend / choppy market:** Bollinger and RSI were more relevant because they are mean-reversion strategies.
- **Moderate-trend market:** Pullback and VWAP were more relevant because they try to enter continuation setups after temporary weakness.
- **Strong-trend market:** SMA and MACD were more relevant because they are trend/momentum-following strategies.

The key lesson was that the ensemble should not treat every indicator equally. A strategy that works in a trending market can perform badly in a sideways market, and the reverse is also true.

## Features Implemented

- Multiple independent strategy classes.
- Shared `process_event()` interface returning order signals.
- Volatility-adjusted position sizing.
- Minimum/maximum allocation clamps.
- Rolling windows using `deque`.
- Trend and mean-reversion strategy variants.
- ADX-based market regime filtering.
- Grid-search optimizer for SMA parameters and trailing-stop experiments.

## Process

This draft started as a simple indicator-voting system: collect signals from common indicators and trade when enough of them agreed. That approach did not work well because agreement between indicators was not the same as real predictive strength.

The design then evolved into treating each indicator as its own standalone strategy. Instead of asking “do indicators agree?”, the system asked “which strategies currently want to buy or sell?”

The next improvement was regime awareness. Since different strategies work better in different market conditions, the ADX filter was added to classify the market and adjust which strategies should matter more.

This version was the most useful of the first draft because it exposed the real problem: most of these indicators were designed for slower daily-style trading. When the project moved toward 1-minute intraday data, the signals became too noisy and unstable. This draft was therefore stopped, and Draft 2 started with the goal of building a system better suited to lower-timeframe data and with better splitted council members.