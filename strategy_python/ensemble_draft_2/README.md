# Ensemble Draft 2

## Concept

Draft 2 moved away from a generic indicator-voting council and tried to create specialized council members with clearer roles. Instead of using several similar indicators that all reacted to the same price movement, each member was designed to detect a specific market behavior: trend direction, breakout, pullback continuation, exhaustion bounce, VWAP deviation, or volume confirmation.

The goal was to reduce duplicated signals and make the ensemble more regime-aware.

## Council Members

### Anchor
Macro-direction filter based on a 200-period SMA. It tracks whether price is meaningfully above or below the long moving average, using volatility-adjusted bands to avoid flipping direction on small noise.

### Breakout
Compression breakout strategy. It builds a short-term price box, checks whether the range is tight, and buys only if the latest two prices break above the local high by enough to clear noise.

### Detective
Confirmation and veto module. It measures recent price movement, relative volume, and candle position to decide whether a move has real conviction or should be treated as weak/fake.

### Deviant
VWAP mean-reversion strategy. It calculates rolling VWAP as a fair-value estimate and buys when price is deeply below VWAP using a rolling z-score, but only if price starts curling upward.

### Exhaustion Fade
Short-term oversold bounce strategy. It uses a fast RSI-style exhaustion signal, then requires price curl and a strong close near the top of the candle before buying.

### Sprinter
Pullback-continuation strategy. It tracks a 20-period EMA, waits for price to pull back near the EMA zone, and buys only when price curls upward with a volume spike.

## Intended Roles

- **Anchor:** broad trend direction / macro bias.
- **Detective:** confirmation or veto based on volume and candle strength.
- **Breakout:** momentum continuation after compression.
- **Sprinter:** trend pullback continuation.
- **Deviant:** VWAP-based mean reversion.
- **Exhaustion Fade:** oversold bounce / short-term exhaustion reversal.

## Features Implemented

- More specialized strategy roles than Draft 1.
- Rolling-window state with `deque`.
- O(1) running calculations for SMA, volume, VWAP, variance, and RSI-like components.
- Volatility-adjusted thresholds.
- Breakout confirmation using multiple closes.
- Volume confirmation through relative volume and z-scores.
- Metadata fields for council-level decision making, such as confidence, abort levels, fair value, z-score, structure low, and loss-of-structure level.

## Process

After Draft 1, it became clear that simply combining common indicators was not enough. Many indicators were too correlated and often voted for the same reason, so the ensemble did not actually gain much independent confirmation.

Draft 2 tried to fix this by giving each council member a more specific job. The system was redesigned around roles: one member for macro bias, one for volume validation, some for trend continuation, and others for mean reversion or exhaustion.

This version was more structured than Draft 1 and better aligned with 1-minute intraday data, but the strategies still struggled with noise. Several members were still indirectly reacting to the same short-term price behavior, so their signals remained more correlated than expected. After trying to tune the system and make each regime contain useful independent members, this draft was ended and replaced by a final draft focused on fully uncorrelated elements.