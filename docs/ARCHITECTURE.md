# Architecture

A single Python process that wakes at every completed 5-minute bar, rebuilds a feature frame with no
look-ahead, asks a strategy engine for signals, and (optionally) routes them to a broker executor with
hard safety rails. The same engine and executor code run in backtests and paper replays, so what you
see offline is what runs live.

```
Groww API ──► data/groww.py ──► bars (5m, 1d, VIX)     option chain snapshots
                                       │                       │
                     data/feed.py (normalise, resample, cache in parquet)
                                       │
                     engine/features.py  ─ 5m indicators (numba), 15m structure, prev-day levels,
                                           VIX, days-to-expiry (engine/calendar.py)
                                       │
                  engine/signals.py make_engine(cfg) ──► one of
                      engine/premium.py   PremiumEngine   iron fly seller      (default)
                      engine/signals.py   SignalEngine    option buyer, driven by
                            engine/pa_scorer.py  price-action setups  (strategy = "pa_short")
                            engine/scorer.py     confluence scorer    (strategy = "confluence")
                                       │  Signal objects: SELL/BUY/EXIT with legs, levels, reason
                     alerts/sink.py (console, JSONL, webhook, Telegram)
                     execution/broker.py Executor (paper | live) with rails
                                       │
                     live.py scheduler  |  backtest/runner.py replay  |  run.py CLI
```

## Modules

| Module | Responsibility |
|---|---|
| `config.py` | typed defaults for every tunable; `Config.load()` overlays `config.toml` |
| `data/feed.py` | bar frame conventions (IST index, OHLCV), `CSVSource` for CSV/parquet replay, session-anchored resampling |
| `data/groww.py` | Groww auth (token, key+secret, TOTP), chunked candle history with parquet cache, option-chain parsing with a session-start OI baseline |
| `data/chain.py` | `ChainSnapshot` analytics: PCR, IV, max pain, OI walls, near-ATM flow; `ChainHistory` for trends |
| `indicators/core.py` | numba-compiled EMA, ATR, RSI, ADX, Supertrend, MACD, Bollinger, efficiency ratio, Donchian, session VWAP, opening range, swing pivots, percentile ranks |
| `engine/calendar.py` | weekly expiry rules (Thursday to Sep-2025, Tuesday after), holiday roll, fractional days to expiry |
| `engine/features.py` | the feature frame; 15m columns come from the last **completed** 15m bar, daily columns from the previous day |
| `engine/options.py` | Black-Scholes price and greeks, IV solver, strike selection |
| `engine/premium.py` | iron-fly engine: entry filters, structure pricing, TP/SL/time exits, re-entry |
| `engine/signals.py` | `Signal` dataclass, `BarEngine` base, the directional `SignalEngine` state machine, `make_engine` factory |
| `engine/pa_scorer.py`, `engine/scorer.py` | setup detection for the buyers |
| `backtest/runner.py` | replay loop, slippage, metrics (points, rupees, drawdown, by year, return on margin) |
| `execution/broker.py` | order placement and verification, position persistence, rails, kill switch, multi-leg handling |
| `alerts/sink.py` | alert dispatch |
| `live.py` | `DataHub` (sources + feature build) and the bar-close scheduler |
| `run.py` | `live`, `scan`, `backtest`, `paper-replay`, `status`, `groww-check` |

## The bar cycle (`live.py`)

1. Sleep until the next 5-minute boundary plus a few seconds.
2. Poll the feed until the just-closed bar is present (gives up before the next bar; late bars are
   caught up on the next cycle since every unseen bar index is processed).
3. Fetch one option-chain snapshot (throttled) if enabled.
4. For every unseen bar: `engine.on_bar(feats, i, chain, chist, expiry)` returns zero or more
   signals; each goes to the alert sinks and, if `[exec] enabled`, to the executor.
5. Print one heartbeat line (`engine.status`) so a watcher can see why there is or is not a trade.
6. After square-off, or if the kill file exists, the executor flattens whatever is open.

## No look-ahead rules

- A 5m bar is processed only after it has closed; the engine refuses to process an index twice.
- 15m features are aligned by **bar end time** with `merge_asof(direction="backward")`.
- Daily and VIX features are looked up on the previous calendar day key, never the same day.
- Days to expiry is computed from the bar's own timestamp.
- Backtests apply the same code with the same restrictions; the only difference is that premiums are
  synthesised instead of read from the chain.

## Execution safety (`execution/broker.py`)

- `paper` mode writes every order exactly as it would be sent and sends nothing.
- `live` mode places MIS market orders, polls the order status to a terminal state, and uses the
  broker's average fill price. A rejected or cancelled entry leaves no position, so the engine's later
  EXIT is ignored instead of selling something you do not hold.
- Rails: one position or structure at a time, lot cap, daily trade cap, daily realised-loss halt, no
  entries after `entry_end`, flatten at `square_off`, kill file.
- Multi-leg: long wings first, then the shorts; on exit the shorts first, then the wings; if a leg fails
  mid-way the filled legs are unwound and no position is recorded.
- State (`cache/executor_state.json`) survives a restart within the same day; a stale position from
  another day is reported and must be closed by hand.

## Performance

Indicators are numba JIT functions on float64 arrays (cached compile). A 9-year, 176k-bar feature
build plus iron-fly replay takes about 10 s; the directional engine about 40 s. The live cycle does a
tail fetch and a full recompute each bar, well under a second.

## Tests

`tests/` (38, pytest): indicators against pandas references, calendar and DTE, option maths and IV
round-trip, chain parsing, no-look-ahead checks, engine state machines for both strategies, the
executor in paper and fake-live modes including rejected legs and the kill switch.
