# Roadmap

What would make this engine materially better, in the order that matters. Each item is an issue
candidate; pick one, say so in the issue, and open a PR with replay evidence (see `CONTRIBUTING.md`).

## 1. Replace simulated premiums with recorded ones (highest value)

Every backtest number here prices options with Black-Scholes at a constant IV. The single most
useful contribution is a recorder that stores the Groww option chain (all strikes, bid, ask, LTP, IV,
OI) every 5 minutes to parquet, and a replay path that prices the structure from those recordings.
A month of recordings would let us say how far the model is from reality.

- `nifty_signals/data/chain.py` already parses snapshots; `live.py` fetches one per bar.
- Needs: a `ChainRecorder` sink, a `RecordedChainSource` for the backtester, and a comparison report.

## 2. Event calendar

`[sell] event_dates` is a hand-typed list. A source for RBI policy days, Union Budget, election
result days and index-heavyweight results would remove the main unmodelled tail.

## 3. Broker-reported margin

`margin_per_lot` is a constant. Read the actual margin from the broker before sizing, and refuse to
open a structure when free margin is below the structure's max loss.

## 4. Second broker adapter

The engine depends on two interfaces: `BarSource` (`data/feed.py`) and a chain class with
`expiries()`, `nearest_expiry()`, `snapshot()`. Zerodha Kite, Upstox, Dhan or Fyers adapters would
widen the audience and the data sources.

## 5. Intraday vega model in the backtester

Trend days raise implied vol; the model holds it constant, so real losses on those days are larger.
A simple regression of intraday IV change on the day's realised move, calibrated from recordings
(item 1), would make the stop statistics honest.

## 6. Walk-forward evaluation

Parameters were chosen on the full 2018-2026 sample. A rolling train/test harness
(`research/`) that re-selects parameters each year and reports only out-of-sample results would
show how much of the edge is real.

## 7. Bank Nifty and Sensex

Different lot sizes, expiry days and volatility. The calendar and strike step are already config.

## Non-goals

- Tick-level or sub-minute strategies: the API and the edge do not support them.
- Signal "accuracy" cosmetics without replay evidence.
- Anything that needs the user's credentials to leave their machine.
