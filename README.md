# Quant Backtester & Strategy Ensemble

## Short Description

This project is an event-driven Java + Python trading/backtesting system.

The Java side is responsible for market-data ingestion, event ordering, order creation, execution simulation, portfolio accounting, live Alpaca integration, and final performance reporting. The Python side is responsible for strategy logic. Java sends every `MarketEvent` to Python through ZeroMQ, Python returns an order signal, and Java decides whether that signal becomes an executable order.

This is not real HFT. It is an HFT-inspired / intraday event-driven architecture using 5-minute or lower-timeframe market data.

## Architecture

```text
CSV / Alpaca REST / Alpaca WebSocket
        |
        v
Java MarketEvent pipeline
        |
        v
BlockingQueue<MarketEvent>
        |
        v
Java Main Engine
        |
        v
ZeroMQ REQ/REP bridge
        |
        v
Python Strategy Ensemble
        |
        v
OrderSignal response
        |
        v
Portfolio -> ExecutionGateway -> Portfolio accounting
```

## Main Components

### Java Backtester

Location:

```text
backend_java/backtester/src/main/java/com/quant
```

Important files:

| File | Purpose |
|---|---|
| `Main.java` | Main engine loop. Reads market events, sends them to Python, receives strategy signals, creates orders, executes them, and prints the final report. |
| `CSVStreamer.java` | Loads historical CSV data, converts rows into `MarketEvent` objects, sorts all events chronologically, and sends them into the event queue. |
| `LiveMarketStreamer.java` | Connects to Alpaca WebSocket, authenticates, subscribes to live bars, aggregates bars, and sends completed events to the engine. |
| `AlpacaRESTFetcher.java` | Fetches recent Alpaca historical bars before live trading starts, so the strategy has warmup data. |
| `BarAggregator.java` | Converts lower-timeframe events into fixed-size OHLCV bars. |
| `Portfolio.java` | Tracks cash, positions, fills, fees, deployed capital, and final performance versus buy-and-hold. |
| `Order.java` | Represents an order and its execution state. |
| `ExecutionGateway.java` | Interface for execution backends. |
| `SimulatedGateway.java` | Backtest execution simulator with slippage and commission. |
| `AlpacaGateway.java` | Sends paper/live orders to Alpaca. |

### Python Strategy Side

Location:

```text
strategy_python/
```

Important folders:

| Folder | Purpose |
|---|---|
| `ensemble_draft_1/` | First draft: indicator council using classic technical indicators. |
| `ensemble_draft_2/` | Second draft: more specialized council members for trend, breakout, pullback, exhaustion, and VWAP deviation. |
| `ensemble_active/` | Final/default strategy ensemble used for testing the backtester. |
| `tools/` | Data download, profiling, slicing, file cutting, and grid-search utilities. |

The final active strategy is in:

```text
strategy_python/ensemble_active/strategy_ensemble.py
```

## Final Strategy Concept

The final strategy moved away from simple indicator voting and toward a smaller set of less-correlated experts.

The active ensemble mainly combines:

```text
Gatekeeper + Z-Score Arbitrage + Momentum Engine
```

OBI Flow exists in the codebase, but in the shown final `MasterEnsemble` it is disabled by setting:

```python
obi_vote = {"confidence": 0.0}
```

### Active Experts

| Expert | Role |
|---|---|
| `Gatekeeper` | Liquidity and friction filter. Blocks trades if spread, book quality, or trading costs are unacceptable. |
| `ZScoreArbStrategy` | Relative-value module using the log-spread between NVDA and SMH. |
| `MomentumEngineStrategy` | Directional momentum module using rolling log returns, volatility normalization, volume adjustment, and EMA-smoothed confidence. |
| `OBIFlowStrategy` | Order-book imbalance module. Implemented, but disabled in the final master strategy. |

The final strategy is conservative and long-only in the shown code. It has logic for managing short positions, but the active entry logic only opens long NVDA trades.

## How To Run

### 1. Requirements

Java side:

```text
Java 17+
Maven
```

Python side:

```text
Python 3.10+
pandas
numpy
alpaca-py
pyzmq
```

Install Python dependencies manually or through your environment manager.

Example:

```bash
pip install pandas numpy alpaca-py pyzmq
```

### 2. Configure Alpaca Credentials

Create this file:

```text
backend_java/backtester/config.properties
```

Expected format:

```properties
alpaca.key=YOUR_ALPACA_KEY
alpaca.secret=YOUR_ALPACA_SECRET
alpaca.url=https://paper-api.alpaca.markets/v2
```

For backtesting with local CSV files, Alpaca credentials are only needed if you want to download data or use live/paper mode.

### 3. Configure Strategy Parameters

Main config file:

```text
strategy_python/config.json
```

Example final configuration:

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

Important: some values are loaded but not fully used in the final active code. For example, `obi_threshold` is loaded, but OBI is disabled in `MasterEnsemble`. `exit_decay_threshold` is loaded, but it is not actively used in the shown exit logic.

### 4. Download Data

From the project root or from the `strategy_python/tools` workflow, run:

```bash
python strategy_python/tools/alpaca_downloader.py
```

This downloads macro bar data into:

```text
backend_java/backtester/data/
```

Default symbols:

```text
NVDA
SMH
```

Default timeframe in the shown downloader:

```text
5-minute bars
```

Output examples:

```text
NVDA_macro_5min.csv
SMH_macro_5min.csv
```

Micro quote downloading exists but is commented out because it can create very large files and slow down testing heavily.

### 5. Start the Python Strategy Bridge

Open a terminal in:

```text
strategy_python/
```

Run:

```bash
python bridge.py
```

The bridge must listen on:

```text
tcp://localhost:5555
```

The Java engine uses a ZeroMQ `REQ` socket and expects a response for every event. If the bridge is not running, the Java engine will repeatedly timeout and rebuild the socket.

### 6. Run the Java Engine

Open another terminal in:

```text
backend_java/backtester/
```

Run:

```bash
mvn exec:java "-Dexec.mainClass=com.quant.Main"
```

The engine writes output to:

```text
backend_java/backtester/engine_log.txt
```

## Backtest Mode vs Live Mode

In `Main.java`:

```java
boolean IS_BACKTEST_MODE = true;
```

Use:

```java
true
```

for CSV backtesting.

Use:

```java
false
```

for Alpaca paper/live mode.

In backtest mode, the engine reads files from:

```java
String[] csvFiles = {
    "data/NVDA_macro_5min.csv",
    "data/SMH_macro_5min.csv"
};
```

In live mode, the engine first uses `AlpacaRESTFetcher` for warmup, then starts `LiveMarketStreamer`.

## How To Tune

### Manual Tuning

Edit:

```text
strategy_python/config.json
```

Most important values:

| Parameter | Meaning |
|---|---|
| `z_score_threshold` | Controls how extreme the NVDA/SMH spread must be before the relative-value module becomes meaningful. |
| `momentum_threshold` | Controls how strong normalized momentum must be. |
| `regime_threshold` | Controls whether the market is treated as `TREND` or `CHOP`. |
| `entry_threshold` | Minimum final master score needed for entry. |
| `cooldown_ms` | Time after an exit before another trade can be opened. |
| `commission_rate` | Commission assumption used in both backtest and friction calculations. |
| `slippage_rate` | Slippage assumption used in both backtest and friction calculations. |
| `max_risk_per_trade_pct` | Risk budget used for position sizing. |

Hardcoded parameters also exist inside `strategy_ensemble.py`, including:

| Parameter | Current Value | Meaning |
|---|---:|---|
| `sl_vol_multiplier` | `3.0` | Stop-loss distance based on recent volatility. |
| `tp_vol_multiplier` | `8.0` | Take-profit reference distance. |
| `min_risk_pct` | `0.0075` | Minimum stop-loss distance. |
| `max_hold_bars` | `78` | Maximum holding period. |
| `min_hold_bars` | `4` | Minimum holding period before some exits activate. |
| `trailing_vol_multiplier` | `2.5` | Trailing stop volatility multiplier. |
| `min_trail_pct` | `0.0060` | Minimum trailing stop distance. |
| `score_history` | `3` | Requires repeated score confirmation before entry. |

### Grid Search

The tuning script is:

```text
strategy_python/tools/grid_search.py
```

Run:

```bash
python strategy_python/tools/grid_search.py
```

What it does:

1. Writes parameter combinations into `strategy_python/config.json`.
2. Starts `bridge.py`.
3. Runs the Java engine.
4. Reads `engine_log.txt`.
5. Extracts PnL and return.
6. Writes results to:

```text
strategy_python/tools/grid_search_results.csv
```

Important: grid search can be slow. Micro quote files were especially slow and could make one run take a very long time. The final workflow uses macro 5-minute files to keep iteration practical.

## Data Tools

### `alpaca_downloader.py`

Downloads historical Alpaca data.

Main outputs:

```text
NVDA_macro_5min.csv
SMH_macro_5min.csv
```

Optional micro quote download exists but is intentionally disabled by default.

### `data_profiler.py`

Profiles daily market regimes from a CSV file.

It reports:

- daily volatility
- daily range
- directional move

Then it selects representative days:

- highest chop
- quietest day
- cleanest directional move

### `data_slicer.py`

Cuts selected dates into smaller stress-test CSV files.

Example outputs:

```text
NVDA_macro_stress.csv
SMH_macro_stress.csv
```

### `file_cutter.py`

Cuts the first `100000` rows of large micro quote files to create smaller lab files.

Example outputs:

```text
NVDA_micro_lab.csv
SMH_micro_lab.csv
```

### `grid_search.py`

Runs repeated backtests across parameter combinations and saves the results.

## Important Checks Before Running

### 1. The Python bridge must be running

Java sends every event to:

```text
tcp://localhost:5555
```

If `bridge.py` is not running, Java will timeout.

### 2. Run commands from the correct directories

Several paths are relative.

Important examples:

```java
../../strategy_python/config.json
```

from Java, and:

```python
backend_java/backtester/config.properties
```

from Python tools.

Running scripts from the wrong working directory can break path resolution.

### 3. Check the strategy response format

`Main.java` expects the Python response to contain:

```json
{
  "signal": "BUY",
  "symbol": "NVDA",
  "price": 123.45,
  "quantity": 10
}
```

The active strategy returns `quantity`. Older draft strategies often return `allocation`, not `quantity`, so they are not directly compatible with the final Java engine unless the bridge converts allocation into quantity.

### 4. Check `IS_BACKTEST_MODE`

In `Main.java`:

```java
boolean IS_BACKTEST_MODE = true;
```

If this is accidentally set to `false`, the engine will try to use Alpaca live/paper components.

### 5. Check the CSV filenames

`CSVStreamer` extracts the symbol from the filename:

```text
NVDA_macro_5min.csv -> NVDA
SMH_macro_5min.csv  -> SMH
```

Do not rename files randomly unless you also update the parsing assumptions.

### 6. Check CSV schema

Macro files are expected to contain at least:

```text
timestamp,open,high,low,close,volume
```

Micro quote files are expected to contain:

```text
timestamp,bid_price,bid_size,ask_price,ask_size
```

### 7. Check the final report

After the run, inspect:

```text
backend_java/backtester/engine_log.txt
```

Look for:

```text
FINAL PERFORMANCE REPORT
Bot Total Return
Buy & Hold Return
Strategy Alpha
Total Fees Paid
```

### 8. Do not trust zero-trade optimization

A grid-search result with better performance because the bot barely trades is not a real strategy improvement. It usually means the filters became too restrictive.

## Known Limitations

- The active strategy is very conservative and may produce few or zero trades.
- OBI is implemented but disabled in the final master strategy.
- The system is synchronous: Java sends one event to Python and waits for one response before continuing.
- The CSV streamer loads all events into memory before sorting and replaying them.
- The live WebSocket streamer has no robust reconnect logic.
- `BarAggregator` does not flush the final unfinished bar at end-of-stream.
- Several paths are hardcoded or relative.
- This is a research/backtesting project, not a production trading system.

## Development Process Summary

### Draft 1: Indicator Council

The first idea was to combine common technical indicators into a council. Strategies included SMA, MACD, RSI, Bollinger Bands, Pullback, VWAP, and an ADX filter. The assumption was that if several well-known indicators agreed, the signal would be stronger.

That assumption was weak. Many indicators were correlated because they all looked at the same price history. Agreement between indicators did not mean independent confirmation.

### Draft 2: Specialized Council Members

The second version tried to give each council member a clearer role. Instead of generic indicators, the system used members like Anchor, Breakout, Detective, Deviant, Exhaustion Fade, and Sprinter.

This was more structured. Some members were designed for trend continuation, others for mean reversion, and others for confirmation or veto. However, on noisy 1-minute data, the signals were still unstable and many members were still indirectly reacting to the same short-term price movement.

### Final Version: Less-Correlated Experts

The final version moved toward orthogonal market dimensions:

- relative value: NVDA versus SMH spread
- momentum: normalized directional return strength
- liquidity/friction: spread, book validity, commission, and slippage
- microstructure: bid/ask imbalance, later disabled

The project also moved away from a broad multi-stock portfolio idea and focused on an NVDA/SMH pair. This made the system cleaner and easier to reason about.

The final bot was better suited to intraday noise than the earlier drafts, but it still did not find a robust trading edge. The NVDA/SMH dependency was not strong enough, OBI did not provide useful confirmation, and grid search mostly improved results by reducing trade frequency. The final active strategy remains useful as a default bot for validating the Java backtester, execution simulator, portfolio accounting, logging, and the full Java-Python event pipeline.
