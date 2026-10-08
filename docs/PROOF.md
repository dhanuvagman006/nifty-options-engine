# Proof: backtest evidence and how to reproduce it

Everything in this folder was produced by the code in this repository on the data in `data/`.
Nothing here is a live trading record. Premiums are simulated (see "What is modelled" below).

## Files in `docs/proof/`

| File | What it is |
|---|---|
| `iron_fly_backtest_2018_2026.txt` | console output of the 9-year replay of the default strategy |
| `iron_fly_trades_2018_2026.csv` | every structure: entry/exit time, ATM strike, credit, close-out value, points, reason, DTE, VIX |
| `iron_fly_monthly_2018_2026.csv` | structures, winners, net rupees per month and the 1-lot equity curve from Rs 1,00,000 |
| `iron_fly_backtest_2026_signals.txt` | the 2026 run with every SELL / EXIT line as the live console prints it |
| `paper_replay_2026.log` | 2026 fed through the engine **and** the paper executor (same code path as `live`) |
| `paper_replay_2026_orders.jsonl` | the leg-by-leg order log the executor wrote during that replay (402 orders) |
| `sweep_fly_sweep*.txt` | parameter and assumption sweeps for the seller (4 rounds) |
| `sweep_pa_sweep.txt`, `sweep_buy_sweep*.txt` | the same for the option-buying strategies |
| `pa_short_trades_2018_2026.csv` | trade list of the best buying configuration |

## Headline numbers (one lot of 75, model prices)

| Year | Structures | Win % | Net Rs | Worst structure Rs |
|---|---|---|---|---|
| 2018 (weekly expiry from Feb 2019, so few) | 23 | 87 | +32,150 | -3,313 |
| 2019 | 78 | 81 | +1,12,400 | -3,063 |
| 2020 | 58 | 91 | +1,30,341 | -3,522 |
| 2021 | 89 | 88 | +1,90,466 | -4,678 |
| 2022 | 84 | 85 | +1,66,152 | -5,977 |
| 2023 | 101 | 82 | +1,43,296 | -5,433 |
| 2024 | 81 | 78 | +1,50,045 | -4,886 |
| 2025 | 99 | 82 | +2,03,533 | -5,227 |
| 2026 (to 7 Oct) | 67 | 81 | +1,25,202 | -5,142 |
| **Total** | **680** | **83** | **+12,53,585** | max drawdown Rs 10,009 |

Rs 1,00,000 on 1 Jan 2025 at a fixed one lot: Rs 3,03,533 on 31 Dec 2025 (every month positive,
weakest October +3,363, equity never below Rs 94,574). Rs 1,00,000 on 1 Jan 2018 at one lot: about
Rs 13.5 lakh by October 2026 (`iron_fly_monthly_2018_2026.csv`, no compounding).

## Reproduce

```bash
pip install -r requirements.txt
```

```bash
python -m pytest -q tests
```

```bash
python run.py backtest --bars data/nifty_5m_2017_2026.parquet --vix cache/india_vix_1d.parquet --from 2018-01-01 --no-chain -q --csv trades.csv
```

```bash
python run.py backtest --bars data/nifty_5m_2017_2026.parquet --vix cache/india_vix_1d.parquet --from 2026-01-01 --no-chain -q
```

```bash
python run.py paper-replay --bars data/nifty_5m_2017_2026.parquet --vix cache/india_vix_1d.parquet --from 2026-01-01 --no-chain -q
```

The sweeps (`research/fly_sweep*.py`, `pa_sweep.py`, `buy_sweep*.py`) read `cache/hist_5m.parquet`
and `cache/india_vix_1d.parquet`; copy `data/nifty_5m_2017_2026.parquet` to `cache/hist_5m.parquet`
first. Each sweep takes 5-15 minutes.

Data: NIFTY 50 1-minute bars April 2017 to 7 Oct 2026 from the public dataset
`technovusin/nifty50-historical-data` (MIT), resampled to 5 minutes and parquet-packed, in `data/`.
Daily India VIX comes from Yahoo Finance (`^INDIAVIX`) and is **not** redistributed here; fetch it once:

```bash
pip install yfinance && python research/fetch_vix.py
```

That writes `cache/india_vix_1d.parquet`; pass it as `--vix cache/india_vix_1d.parquet`. Without a
VIX file the engine substitutes a realised-volatility proxy (20-day realised vol x 1.27, the median
India VIX premium 2018-2026); on that proxy the 2026 replay shows 51 structures and Rs 97,924 instead
of 67 and Rs 1,25,202, because the proxy lags real VIX and the filters block more days.

## What is modelled, and what is not

Modelled: real spot path at 5-minute resolution (entries and exits at bar closes, stops checked at
the bar's high and low), real previous-close India VIX, the true weekly expiry calendar with holiday
rolls, fractional time to expiry inside the session, Black-Scholes pricing of all four legs with IV =
VIX x 1.05 (wings +2 vol points for skew), 6 index points of round-trip cost per structure (spreads on
four legs plus brokerage), one position at a time, the same engine and the same executor code that
`live` runs.

Not modelled: intraday changes in implied volatility (IV rises on trend days, so real losses on those
days are larger than modelled), the term-structure premium of 0-1 DTE implied vol over VIX (real
credits are usually larger), the difference between mid and a market-order fill, exchange margin
changes, event days (budget, policy, results) unless listed in `event_dates`, and the broker being
down. The 2025 and 2026 years were part of the data used to choose the parameters, so they are not
out-of-sample. Treat every figure as an upper bound to be verified with a month of paper trading on
live chains.
