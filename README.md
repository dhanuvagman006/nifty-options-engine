# Nifty Options Engine

Open-source (MIT) intraday engine for NIFTY weekly options on the Groww API: a defined-risk
premium-selling strategy (weekly iron fly, sold only in the two sessions before expiry) that nine
years of 5-minute data support, two option-buying strategies kept for comparison, a no-look-ahead
feature pipeline, a backtester with simulated premiums, and a paper/live executor with hard safety
rails. Every number in the docs can be reproduced from the data in `data/`.

```
07-Oct 09:40  SELL IRON FLY NIFTY 22600  wings 22200/23000  credit 161.1  TP 81  SL 217  x1 lot  | spot 22613 | exp 13-Oct
           legs S22600CE@94.9 S22600PE@76.1 B23000CE@6.1 B22200PE@3.8
07-Oct 14:40  EXIT IRON FLY NIFTY 22600  @131.0  TIME  +15% of credit  | spot 22699
```

Status: backtested and paper-replayed, **not yet traded live**. The model's numbers are upper bounds
(`docs/PROOF.md`). Contributions that add live chain recordings are the most valuable thing you can do.

## Documentation

| | |
|---|---|
| [docs/STRATEGY.md](docs/STRATEGY.md) | what it trades, when, how it exits, capital, what to expect |
| [docs/PROOF.md](docs/PROOF.md) | backtest evidence, trade lists, sweeps, how to reproduce, what is and is not modelled |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | modules, data flow, bar cycle, no-look-ahead rules, execution safety |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | install, Groww setup, paper trading, going live, kill switch, VPS, daily checklist |
| [docs/RESEARCH.md](docs/RESEARCH.md) | the research that led here: what has an edge on NIFTY and what does not |
| [docs/ROADMAP.md](docs/ROADMAP.md) | what would make it materially better, in priority order; pick one |

## Install

```bash
pip install -r requirements.txt
```

Python 3.11+ (tested on 3.14). `numba` is optional but makes indicator computation ~100x faster.

## Configure Groww

Create API credentials at Groww > Trade API, then either paste them into `config.toml`:

```toml
[groww]
totp_token  = "..."     # no-expiry flow (recommended), needs pyotp
totp_secret = "..."
# or
api_key     = "..."     # key+secret flow (needs daily approval in the Groww app)
api_secret  = "..."
```

or export `GROWW_TOTP_TOKEN` / `GROWW_TOTP_SECRET` (or `GROWW_API_KEY` / `GROWW_API_SECRET`, or a
ready `GROWW_ACCESS_TOKEN`). Then verify the whole data path:

```bash
python run.py groww-check
```

Market data (candles and the option chain) needs Groww's data subscription; `groww-check` tells you
immediately if the account lacks it. Groww also requires the calling IP to be registered, so for
24/7 use deploy on a VPS with a static IP (see below).

## Run

```bash
python run.py live          # wakes at every 5-minute bar close during market hours, prints alerts
```

```bash
python run.py scan          # evaluate the most recent completed bar once
```

```bash
python run.py status        # diagnostic: current indicator state, chain stats, and why there is / is no signal
```

```bash
python run.py backtest --days 55 --csv trades.csv
```

```bash
python run.py backtest --bars cache/hist_5m.parquet --vix cache/india_vix_1d.parquet --from 2026-01-01 --no-chain -q
```

Flags: `-v` adds the score breakdown to each alert, `-q` suppresses log lines, `--no-chain` skips the
option chain (technical factors only), `--config path.toml` selects another config. For backtests,
`--bars` / `--vix` replay from local CSV or parquet files instead of Groww, `--from` / `--to` bound the
replay (earlier bars still warm the indicators) and `--strategy` overrides `[filt].strategy`.

While `live` runs it prints one status line per 5-minute bar so you can see what it is thinking:

```
09:45 INFO bar 09:40 close 22617 atr 24 rsi 51 adx 18 vix 13.9 dte 4.9 | pcr 0.91 iv 13.8/14.2 | FLY: filters pass
09:45 INFO 07-Oct 09:40  SELL IRON FLY NIFTY 22600  wings 22300/22900  credit 181.9  TP 91  SL 273  | spot 22617 | exp 13-Oct
                    legs S22600CE@204.1 S22600PE@158.2 B22900CE@104.2 B22300PE@76.2
10:05 INFO bar 10:00 close 22640 ... | OPEN FLY 22600 credit 182 value 178 (+2%) tp 91 sl 273 bars 4
14:45 INFO 07-Oct 14:40  EXIT IRON FLY NIFTY 22600  @160.4  TIME  +9% of credit  | spot 22620
```

`no [...]` lists the vetoes blocking an entry; with a position open the line shows the structure's
live close-out value against its take-profit and stop. The directional strategies print `CE:` / `PE:`
verdicts instead.

Alerts go to the console, `logs/signals.jsonl`, and optionally a webhook or Telegram bot
(`[alert]` section).

## Strategies

`[filt].strategy` selects one of three engines. The default is the one the research supports.

### iron_fly (default): defined-risk premium selling

Nine years of 5-minute data showed no usable intraday directional edge on NIFTY but a persistent
gap between implied and realised volatility ([docs/RESEARCH.md](docs/RESEARCH.md)). The engine
therefore sells time and volatility with the loss capped by long wings, and uses the regime and
price-action work only to decide when **not** to sell.

- **Structure**: sell the ATM call and put of the nearest weekly expiry, buy a call `wing_pts` above
  and a put `wing_pts` below (default 300). Max loss = wing width minus credit, per lot.
- **Entry**: the first bar closing at or after `entry_time` (09:45), once per session, when every
  filter passes: trading days to expiry inside `[dte_min, dte_max]`, not an `event_dates` day, open
  gap below `gap_max_pct`, move since the open below `open_move_max_pct`, VIX inside `[vix_min, vix_max]`
  and not above `vix_spike_ratio` x its 20-day mean, 15m ADX below `adx_max`, and (live) PCR not extreme.
- **Exit**: the structure's close-out value is marked every bar. Take profit when `tp_frac` of the
  credit has decayed, stop when the loss reaches `sl_mult` x credit (checked at the bar's spot
  extremes), otherwise close at `exit_time` (14:45) or `expiry_exit_time` (13:30) on expiry day.
- **Orders**: the executor buys the wings first, then sells the straddle; on exit it buys the shorts
  back first. A leg that fails on entry unwinds the legs already filled.

### pa_short: price-action shorts (bought puts)

The four short-side setups that survived the 9-year study (VWAP rejection, VWAP reclaim,
prior-day-high sweep, prior-day-low break-and-hold, each on a bearish bar with the 15m trend down),
expressed as an ATM weekly put with a 1 ATR stop, half booked at 1.5R, target 3R, 24-bar time stop.
The spot edge is real (about +0.1R per trade after costs) but thin, and weekly put theta eats most
of it; it is kept as a signal source, not as the money-maker.

### confluence: v1 multi-factor option buying

The original scorer, kept for comparison. It loses over nine years.

Every completed 5-minute bar is evaluated in three stages. A signal is emitted only if all three pass.

**1. Hard vetoes** (any one blocks the bar)

| Veto | Rule |
|---|---|
| time | entries only 09:30-14:45 (13:30 on expiry day); first 30 min of the session skipped |
| vix | India VIX outside 9-24 |
| atr_pct | 5m ATR percentile outside 20-95 (dead or panicking market) |
| chop / er | ADX < 17 with efficiency ratio < 0.30, or efficiency ratio < 0.25 |
| gap | gap > 1.2% vs previous close during the first hour |
| htf | 15m EMA20/EMA50 and 15m close not aligned with the direction |
| ltf | 5m close vs EMA21, EMA9 vs EMA21, Supertrend(10,3) not aligned |
| daily | previous close on the wrong side of the daily EMA20 |
| rsi | RSI14 outside 48-70 (CE) / 30-52 (PE) |
| extended | continuation entries more than 1.6 ATR from EMA21 |
| squeeze | Bollinger bandwidth below its 25th percentile unless the trigger is a breakout |
| pcr / pcr_extreme | PCR(OI) outside 0.75-1.60 for CE, 0.55-1.35 for PE, or outside 0.45-2.2 |
| iv | ATM IV above 24 |
| wall | dominant OI wall closer than 0.25% in the trade direction |

**2. Trigger** (exactly one must fire on the current bar; bar must close strong: body >= 50%, close in top/bottom 35%)

- `deep_pb` - pullback that reached the EMA21 zone within the last 6 bars (>= 2 counter-trend bars), then a bar that reclaims the 3-bar high/low and the fast EMA
- `vwap_rc` - strong close through session VWAP in the trend direction
- `dc` - close beyond the 20-bar Donchian channel with range expansion (0.8-2.5 ATR)
- `orb` - first close beyond the opening range (first 15 min) within the first two hours

**3. Confluence score** - weighted evidence across independent categories; the score is normalised
over the factors that could be evaluated (option-chain factors only count when a live chain is
available). Default threshold 70 with at least 4 categories agreeing.

| Category | Factors |
|---|---|
| trend | ADX >= 20, ADX rising, DI alignment |
| momentum | RSI in the sweet spot (52-68 / 32-48), MACD histogram sign and slope |
| htf | 15m RSI side, 15m Supertrend, 15m ADX >= 18 |
| daily | daily bias, close vs previous day close |
| vwap | close on the right side of session VWAP |
| volatility | ATR percentile 30-85, efficiency ratio >= 0.30 |
| candle | strong trigger candle, regression slope sign |
| options | OI flow near ATM (put build for CE / call build for PE), unwinding on the far side, PCR trend, room to the OI wall |

**Trade management** (spot terms, converted to premium with Black-Scholes at the live IV)

- Stop: 1.5 ATR, tightened to the last swing if closer (never below 1.0 ATR)
- T1 = 1R: book half, stop to entry, then trail the tighter of Supertrend / EMA21
- T2 = 3R: full exit. Time stop 18 bars if T1 not reached. Forced exit at 15:10, on Supertrend flip, or when an opposite setup passes.
- Cooldown 3 bars after any exit, 6 after a stop-out. Max 4 entries per day, one position at a time.
- Strike: ATM; one strike ITM on expiry day. Premiums outside 40-400 are skipped.
- Set `capital` in `[opt]` to get lot sizing (1% risk per trade by default, lot size 75).

## Backtest results

Replay of the default `iron_fly` strategy on real NIFTY 5-minute bars with real India VIX, option
premiums simulated with Black-Scholes (IV = VIX x 1.05, wings +2 vol points for skew), 6 index points
of round-trip cost per structure, one lot (75). Entries are opportunity-based: any bar between 09:45
and 13:00 on the two sessions before expiry while the filters pass, up to three structures a day
with re-entry after a stop or take-profit.

| | 2026 (Jan-7 Oct) | 2018-2026 |
|---|---|---|
| Sessions / structures sold | 189 / 67 | 2,166 / 680 |
| Win rate | 81% | 83% |
| Profit factor | 5.6 | 6.0 |
| Net P&L, 1 lot | +1,669 pts = Rs 1,25,200 | +16,714 pts = Rs 12,53,600 |
| Average per structure | +24.9 pts = Rs 1,870 | +24.6 pts = Rs 1,844 |
| Worst structure / max drawdown | Rs 5,100 / Rs 7,400 | Rs 6,000 / Rs 10,000 |
| Positive years | - | 9 of 9 |
| Exits | 51 time, 13 take-profit, 3 stop | 476 / 164 / 40 |

```bash
python run.py backtest --bars cache/hist_5m.parquet --vix cache/india_vix_1d.parquet --from 2026-01-01 --no-chain -q
```

What drives it, from the parameter sweeps in `research/fly_sweep.py` and `fly_sweep2.py`
(full tables in `logs/fly_sweep*.txt`):

- **Opportunity, not a clock.** Moving from one fixed 09:45 entry to a 09:45-13:00 window, dropping
  the gap and ADX filters (they only removed profitable days: `logs/fly_sweep3.txt`), holding expiry
  day to 14:45 and tightening the stop to 0.35x credit took the nine-year net from +9,035 to +16,714
  points with a smaller worst trade. Re-entry after a stop or take-profit is enabled but rarely fires
  (once in nine years), because take-profits land after the last-entry time.
- **Only the last two sessions before expiry carry net theta.** At 3-6 days to expiry the wings decay
  as fast as the straddle and the fly loses on 89% of days; at 0-1 days it wins on 85-90%. `dte_max = 2`
  is therefore structural, not tuned. With Tuesday expiry that means Monday and Tuesday only.
- **The filters cost trades, not safety.** Without any entry filter the same period shows 80 structures
  in 2026 and a larger net, but a deeper drawdown; the filters are kept because the simulation cannot
  see the event days and vol spikes that cause the real tail.
- **Sensitivity** (`logs/fly_sweep4.txt`): IV at VIX x 1.00 instead of 1.05 keeps 90% of the net; 10 points
  of cost instead of 6 keeps 83%; 500-point wings earn 15% more but raise the max loss per structure to
  about Rs 25,000, too much for a 1 lakh account; removing every remaining filter adds trades but
  doubles the drawdown.

Read this with care. Premiums are simulated, not real ticks: the model prices every leg at a
constant IV from the previous VIX close, so it does not see intraday vega (IV rising on trend days
makes the real loss larger than the modelled one), expiry-week skew, or the fact that real 0-1 DTE
implied vols often sit above VIX. Fills are assumed at mid with a fixed 6-point cost. The 91% win
rate will be lower live; what the model supports is that the *sign* of the edge is positive in every
year and that the loss per structure is capped by the wings. Paper-trade the live structure on real
chains for several weeks before risking capital, and expect real results well below the table.

Capital: one hedged lot needs roughly Rs 30-50k of exchange margin (set `margin_per_lot` to what
Groww actually blocks) plus the max loss buffer. At that size the 2026 model result is about Rs 7,000
a month per lot. It is not a daily-income machine: roughly two structures a week, some of them losers.

**Buying only.** `strategy = "pa_short"` runs the best-found buying form (300 points
in the money, three of the four triggers, entries before 12:00, fixed 1-point slippage): 158 trades
over nine years, profit factor 0.96, 2026 so far 17 trades for Rs -8,800 per lot. Every bought-option
variant tested is negative or break-even (`research/buy_sweep.py`, `buy_sweep2.py`,
[RESEARCH.md s.8](docs/RESEARCH.md)); the setups earn about 2.5 index points per trade in spot terms,
which is less than an option's round-trip cost.

## Capital needed and expected P&L

Model numbers (simulated premiums on real 2018-2026 bars and real VIX, one lot of 75). Real results
will be lower than the fly row and no better than the buying row.

| | iron_fly (hedged seller, default) | pa_short (buying only) |
|---|---|---|
| What is held | short ATM straddle + long wings 400 pts out, intraday | one weekly put 300 pts ITM, intraday |
| Broker margin / premium per lot | ~Rs 40,000 margin (check what Groww blocks) | ~Rs 25,000 premium paid |
| Largest possible loss per structure | wing width minus credit: ~Rs 18,000 | stop at 1 ATR: ~Rs 2,000-3,000 |
| Worst seen in 9 years / in 2026 | Rs 7,600 / Rs 3,100 | Rs 2,200 / Rs 2,200 |
| **Minimum to start** | **Rs 60,000** (margin + one max loss); 1 lakh recommended | Rs 30,000 |
| Trades per month | 7 (Mon/Tue only, up to 3 a day) | 1-2 |
| Average per trade, 9 years | +Rs 1,840 | -Rs 30 |
| Average per trade, 2026 | +Rs 1,870 | -Rs 520 |
| Expected monthly P&L per lot, model | +Rs 12,000 (9-yr) to +Rs 13,500 (2026) | about zero to -Rs 1,000 |
| On Rs 1,00,000 | ~12-13% a month before the unmodelled costs | negative |
| Worst month seen (2026) | +Rs 4,200 (every 2026 month positive) | - |
| Drawdown to plan for | Rs 25,000 (one max-loss day + a losing week) | Rs 11,000 (2026) |

Haircuts the model does not include for the fly: intraday IV rises on trend days (bigger losses than
modelled), 0-1 DTE skew, and real fills versus mid. Halving the model's monthly figure is a sensible
planning number until a month of paper trades on live chains says otherwise. A second lot needs
another Rs 60,000; do not run two lots on 1 lakh.

## Automatic order placement

Signals can be routed to an executor that places intraday (MIS) market orders on Groww.

```toml
[exec]
enabled = true
mode = "paper"      # start here: orders are written to logs/orders.jsonl, nothing is sent
max_lots = 1
max_trades_per_day = 3
max_daily_loss = 1500
kill_file = "STOP"
```

Switch `mode = "live"` only after the paper log shows sensible fills for a while. Rails that are
always on: one position (or one structure) at a time, lot cap, daily trade cap, daily realised-loss
halt, no entries after 14:45, everything flattened at 15:10, and a kill switch (create an empty file named `STOP` in the
project folder to stop new buys and close the open position on the next bar). Every order, skip and
error is appended to `logs/orders.jsonl`. Buy fills are confirmed through the order-status API before
the position is tracked, so a rejected order never leads to a phantom sell.

## Deploy on a VPS (Linux, static IP)

Groww binds API access to the IP you register, so run the engine on the VPS itself.

```bash
sudo apt install -y python3 python3-venv && git clone <your repo> ~/ClaudeTrader && cd ~/ClaudeTrader && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Put credentials in `/etc/nifty-signals.env` (mode 600) rather than in `config.toml`:

```
GROWW_API_KEY=...
GROWW_API_SECRET=...
```

Create `/etc/systemd/system/nifty-signals.service`:

```ini
[Unit]
Description=Nifty options signal engine
After=network-online.target

[Service]
WorkingDirectory=/home/<user>/ClaudeTrader
EnvironmentFile=/etc/nifty-signals.env
Environment=TZ=Asia/Kolkata
ExecStart=/home/<user>/ClaudeTrader/.venv/bin/python run.py live -q
Restart=always
RestartSec=15
User=<user>

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now nifty-signals && journalctl -u nifty-signals -f
```

The service idles outside market hours and restarts itself on any crash. Signals are appended to
`logs/signals.jsonl`; set `telegram_token` / `telegram_chat_id` in `[alert]` to get them on your phone.
Keep the machine clock synced (`timedatectl set-ntp true`): bar scheduling is wall-clock driven.

## Project layout

```
run.py                        CLI (live / scan / backtest / paper-replay / status / groww-check)
config.example.toml           copy to config.toml (git-ignored) and add your Groww credentials
data/                         NIFTY 5m bars 2017-2026 and daily India VIX used by the backtests
docs/                         STRATEGY, PROOF (+ proof/ artefacts), ARCHITECTURE, OPERATIONS, RESEARCH
nifty_signals/
  config.py                   typed defaults + TOML overrides
  data/feed.py                bar frame conventions, CSV source, resampling
  data/groww.py               Groww candles (parquet-cached) + option chain adapter
  data/chain.py               ChainSnapshot analytics (PCR, walls, max pain, near-ATM flow) + ChainHistory
  indicators/core.py          numba-compiled indicators (EMA, ATR, RSI, ADX, Supertrend, MACD, BB, ER, Donchian, VWAP, pivots...)
  engine/features.py          multi-timeframe feature frame with no look-ahead
  engine/scorer.py            vetoes, triggers, confluence score (v1)
  engine/pa_scorer.py         price-action short setups (pa_short)
  engine/premium.py           iron-fly premium-selling engine (iron_fly)
  engine/signals.py           directional position state machine -> BUY / EXIT signals; engine factory
  engine/options.py           Black-Scholes, IV solver, strike selection
  engine/calendar.py          weekly expiry (Tuesday) with holiday roll, DTE
  backtest/runner.py          replay + metrics
  alerts/sink.py              console / JSONL / webhook / Telegram
  execution/broker.py         Groww order executor (paper / live) with risk rails
  live.py                     bar-close scheduler
research/                     mechanical setup studies and parameter sweeps on the 9-year history
docs/RESEARCH.md              research synthesis (what has an edge, what does not, and why)
tests/                        38 unit tests (pytest)
```

## Performance notes

- All indicators are numba JIT functions on float64 arrays (full 60-day 5m feature build: ~50 ms after the one-time compile; compile results are cached on disk). A full 60-day backtest runs in ~0.3 s.
- Bars are cached in parquet; each live cycle only fetches the tail and recomputes the frame.
- The option chain is throttled (`chain_min_refresh_sec`) and fetched once per bar.
- To plug in another broker, implement the `BarSource` protocol in `data/feed.py` and a chain class exposing `expiries()`, `nearest_expiry()` and `snapshot()` (see `data/groww.py`).

## Before you push this repository

- `config.toml` is git-ignored because it holds your Groww keys; `config.example.toml` is the
  committed template. Regenerate any secret that has ever been displayed on screen.
- `cache/`, `logs/` and `data_raw/` are ignored; `data/` (5 MB) and `docs/proof/` are meant to be committed.
- The India VIX history is not redistributed (Yahoo terms); fetch it with `python research/fetch_vix.py`.
- Run `python -m pytest -q tests` (38 tests) before each push.

## Contributing and licence

MIT licence (`LICENSE`). See `CONTRIBUTING.md` for how changes are judged (replay evidence, no
look-ahead, executor failure-path tests) and `SECURITY.md` for credential handling. Spot data:
NIFTY 50 1-minute history from `technovusin/nifty50-historical-data` (MIT).

## Disclaimer

This software is provided for research and education. It is not investment advice, the authors are
not registered advisors, and nothing here is a solicitation to trade. Options selling, even hedged,
can lose the full width of the wings on a single structure; options buying can lose the full premium.
Backtests use simulated option prices and are not a record of real trades. SEBI's own data shows
that most individual index-option traders lose money. If you run this with real money you do so
entirely at your own risk; validate on paper first, size conservatively, and keep the holiday list
and expiry weekday in `config.toml` current.
