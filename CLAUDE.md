# 🧠 Project: High-Frequency Quant Backtester

## Architecture
- Java: execution engine (tick streaming, portfolio, costs, bid/ask realism)
- Python: strategy logic + optimizer

Execution engine is assumed correct and cost-accurate unless proven otherwise

## Strategy Modules
- Gatekeeper: blocks trades if expected edge < costs
- Z-Score Arb: mean reversion (paired assets)
- Momentum: breakout/trend-following
- OBI Flow: order book imbalance filter

## Constraints
- Always account for spread, slippage, commission
- Avoid overfitting
- Prefer statistically robust logic over curve-fitting

## Rules
- Only suggest code if ≥95% confident
- Ask clarifying questions if unsure
- Use diffs, not full rewrites