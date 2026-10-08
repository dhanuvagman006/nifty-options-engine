# Research: where the money is in NIFTY options, and what this system should become

Date: 2026-10-08. Sources are linked inline. Evidence grades: **A** peer-reviewed or regulator data,
**B** exchange/broker research with stated method, **C** practitioner backtest with partial method,
**D** blog/folklore.

## 1. The headline finding: the current strategy loses over 9 years

The signal engine (multi-timeframe trend + pullback/breakout triggers + ATR stops, buying ATM weekly
options) was replayed on 2,351 sessions of 1-minute NIFTY data (Apr-2017 to Oct-2026, resampled to
5-minute bars, premiums simulated with Black-Scholes at realised-vol-plus-premium):

| | 42 sessions (Aug-Oct 2026) | 2,351 sessions (2017-2026) |
|---|---|---|
| Trades | 13 | 437 |
| Win rate | 61.5% | 46.5% |
| Profit factor | 2.48 | 0.69 |
| Expectancy per trade | +7.1% | -2.4% |
| Positive years | n/a | 3 of 10 |

The 42-session result was noise. No trigger type, direction or hour of entry was positive over the
long sample. This matches the external evidence below: intraday directional option buying on an
index has negative expectancy after theta and costs unless the trader can predict trend days, and
nothing cheap predicts trend days.

## 2. What the 9-year spot data says about intraday patterns

Tested directly on the same data (script in the session scratchpad; daily stats saved to
`cache/daily_stats.parquet`):

| Pattern | Result on NIFTY | Grade |
|---|---|---|
| First 30 min predicts last 30 min (the US "intraday momentum" effect) | Sign agreement 51.1%, correlation -0.04. No edge. Unstable year to year. | A (own test, n=2,346) |
| First 30 min predicts rest of day | 52.7% agreement, correlation -0.11 (slight reversal). | A (own test) |
| Gap and go | Close continues the gap direction 47-51% regardless of gap size. Gaps > 1% fill only 20% of the time but do not continue either. | A (own test) |
| 60-minute opening range breakout | 58% of up-breaks close above the range high, average +0.07% (about 15 points). Not enough to pay an option's theta and spread. | A (own test, n=1,083 up / 1,110 down) |
| Trend days | 12.9% of sessions. Probability rises to 24% when the first 30 min moved > 0.5%, and 30% when price is 0.6 ATR from the open by 10:15, but the average follow-through from 10:15 to close is zero. | A (own test) |
| Volatility by hour | 09:15-10:00 has 2x the per-bar volatility of midday; midday is dead; a modest pickup after 14:00. | A (own test) |
| Volatility clustering | After a > 1% day the next day's range is 1.15x ATR; direction is a coin flip (52%). | A (own test) |

Conclusion: NIFTY intraday direction is close to unpredictable with price-only features. Volatility
(size of moves) is somewhat predictable; direction is not.

## 3. External evidence on option buying vs selling

- Zerodha's ORB study on NIFTY weekly options, Jan-2022 to Feb-2026, after costs and 0.2% slippage: buying wins ~48% with a max drawdown near 45%; selling the same breakouts had a smoother curve with ~6% drawdown and every year positive. [Zerodha In The Money, ORB part 2](https://inthemoneybyzerodha.substack.com/p/how-to-trade-opening-range-breakout) (B)
- SEBI: 91% of individual F&O traders lost money in FY2024-25, net losses Rs 1.06 lakh crore. [Business Standard on the SEBI study](https://www.business-standard.com/amp/markets/news/net-losses-of-traders-in-fo-widens-in-fy25-sebi-study-125070701221_1.html) (A)
- US retail option data: 0DTE trades lose 4.7% more than other option trades; option sales are more profitable than purchases. [Bogousslavsky & Muravyev](https://www.lsu.edu/business/files/event-files/2025-finance-mardi-gras/retail_option_trading_v2.pdf) (A)
- India VIX is an unbiased forecast of realised vol and typically sits above it; a GitHub replication found average VIX 16.6 vs realised 14.1, a positive volatility risk premium of ~2.5 points. [Global Business Perspectives](https://link.springer.com/article/10.1007/s40196-013-0025-4), [VRP India repo](https://github.com/RajolKumar2003/volatility-risk-premium-india) (A/C)
- Implied vol rises into scheduled events (RBI, Budget) and falls after; VIX closed lower on essentially every Budget day. [Zerodha Budget analysis](https://inthemoneybyzerodha.substack.com/p/budget-2026-trading-strategies-what), [Shaikh & Padhi](https://ideas.repec.org/a/spr/trstrv/v19y2013i4p445-460.html) (B/A)
- Expiry-day decay on NIFTY is back-loaded into the afternoon; weekly expiry moved to Tuesday from Sep-2025. [Navia](https://navia.co.in/blog/weekly-fo-expiry-insights/) (C)
- Option-chain folklore (PCR thresholds, max pain) has no published predictive test on NIFTY; US pinning evidence is modest and statistical. [CXO on pinning](https://www.cxoadvisory.com/equity-options/stock-price-pinning-at-options-expiration/) (C)
- Machine learning on minute data overfits; out-of-sample accuracy converges to ~50%. [SPY minute-level study](https://arxiv.org/html/2412.15448v1) (A)
- Dealer gamma matters for intraday momentum/reversal in futures markets, but measuring it needs option positioning data retail does not have. [Baltussen, Da, Lammers, Martens, JFE 2021](https://academicweb.nd.edu/~zda/intramom.pdf) (A)

## 4. What this means for the system

The edge that exists for a retail systematic trader on NIFTY is **being paid for volatility and
time**, not predicting direction:

1. **Sell premium with defined risk** (short straddle/strangle or iron condor on the weekly, hedged
   wings, hard stop on each leg, time-based exit). This is the only approach with multi-year positive
   results in Indian broker research and consistent with the volatility-risk-premium literature.
   Needs margin: roughly 1.0-1.5 lakh per lot for a naked straddle, 30-50k for a hedged condor.
2. **Keep the directional engine as a filter, not a trade**: use its trend/chop classification to
   decide when NOT to sell (strong trend days, event days, VIX spikes) and to skew the structure.
3. **Event-vol rules**: avoid selling into RBI/Budget/Fed sessions; consider selling after the event
   once IV crushes; never buy premium into an expected IV crush.
4. **Expiry-day awareness**: Tuesday afternoon decay favours sellers; the engine already stops
   directional entries at 13:30 on expiry day.

What is not realistic: a consistent daily profit, or any strategy at 10k capital. One NIFTY lot of a
hedged condor needs ~30-50k margin; a 10k account cannot run a defined-risk selling structure and a
single long option is a coin flip with negative drift.

## 5. Price action, tested mechanically on 9 years (research/pa_study.py, pa_study2.py)

Every setup was defined as a rule, entered at the bar close, and run through the same simulator
(stop 1 ATR, target 2 ATR, 24-bar time stop, same session, stop-first when both touched). Results in
R multiples with a 2017-2022 / 2023-2026 split. Random baseline: +0.003R.

| Setup (5m, 09:30-14:45) | n | win % | expR | train | test | +years | verdict |
|---|---|---|---|---|---|---|---|
| VWAP rejection, short | 1,632 | 38.7 | +0.097 | +0.097 | +0.098 | 9/10 | **survives** |
| VWAP reclaim (first close below after 3 above), short | 3,648 | 36.8 | +0.068 | +0.082 | +0.045 | 9/10 | survives |
| Prior-day low break and hold, short | 574 | 37.3 | +0.090 | +0.091 | +0.090 | 5/10 | survives |
| Prior-day high sweep and reject, short | 676 | 36.8 | +0.072 | +0.059 | +0.093 | 7/10 | survives |
| Fair value gap return, short | 3,264 | 36.4 | +0.044 | +0.091 | -0.018 | 8/10 | fades out of sample |
| Open above PDH and holding, long | 395 | 41.3 | +0.049 | +0.040 | +0.070 | 5/10 | weak |
| Inside-bar breakout (either side) | ~1,700 | 35 | +0.02 | ~0 | +0.07 | mixed | noise |
| Engulfing anywhere / at a level | ~4,400 | 34-35 | -0.01 to +0.03 | | | | noise |
| Break of structure + retest, long | 4,137 | 31.9 | -0.081 | -0.064 | -0.109 | 0/10 | **loses** |
| Session high/low sweep reversal | ~1,900 each | 31-33 | -0.09 / -0.04 | | | 3-4/10 | loses |
| Order block retest, long / short | 83 / 67 | | -0.15 / +0.28 | | | | too few |
| Round-number (x100) rejection | ~1,000 each | 33-34 | -0.08 / -0.02 | | 1/10 | | loses |
| VWAP rejection / reclaim, long | 1,756 / 3,595 | 34-35 | -0.054 / -0.015 | | | 2-4/10 | loses |
| Prior-day low sweep, long | 532 | 32.9 | -0.039 | -0.105 | +0.056 | 6/10 | unstable |

Three things stand out. First, every long-side setup loses intraday while its short mirror works: NIFTY's
intraday drift is negative (its gains accrue overnight), so intraday price action has a short bias.
Second, the "smart money" vocabulary (break of structure, order blocks, liquidity sweeps of session
extremes, round numbers) does not survive a mechanical test. Third, the setups that do survive are the
oldest ideas: VWAP rejection, prior-day levels, acceptance below support.

Stage 2 added a 0.08R cost haircut (about 2 index points round trip) and context filters:

| Filter on the four surviving shorts | expR after costs | train | test | t |
|---|---|---|---|---|
| none | ~0.00 to +0.02 | | | |
| 15m trend aligned (EMA20 < EMA50) | +0.055 | +0.051 | +0.060 | 2.0 |
| ... and target widened to 3 ATR | **+0.106** | +0.114 | +0.095 | 3.2 |
| ... stop 0.7 ATR, target 2 ATR | +0.106 | +0.095 | +0.123 | 3.1 |
| VWAP rejection with ADX >= 25 | +0.134 | +0.191 | +0.047 | 2.5 |
| PDH sweep in the first 90 minutes | +0.183 | +0.189 | +0.174 | 1.9 |
| Any setup 13:00-14:45 | negative | | | |

Positive in 6 of 10 years with the 1:3 payoff. That is a real but thin edge: about 2.5 index points
per trade net, roughly 280 trades a year. In option terms (delta ~0.5, ATM weekly premium ~100), that
is about 1.2% of premium per trade before theta, and an hour of theta on a weekly ATM option costs
roughly the same. The combined rule set is implemented as the `pa_short` strategy in
`nifty_signals/engine/pa_scorer.py`; section 6 reports its full-engine replay with simulated option
premiums.

## 6. The price-action strategy through the full engine, in option terms

The four surviving short setups with their context filters were implemented as the `pa_short`
strategy and replayed through the complete engine (one position at a time, stop 1 ATR, book half at
1.5R, target 3R, 24-bar time stop, Supertrend-flip exit, 15:10 square-off) with Black-Scholes
premiums on the weekly ATM put, so theta and the premium's own path are included:

| 2017-2026, 2,351 sessions | pa_short (PE buying) |
|---|---|
| Trades | 471 |
| Win rate | 41.8% |
| Avg win / loss | +10.1% / -8.6% of premium |
| Profit factor | 0.83 |
| Expectancy per trade | -0.8% |
| Positive years | 1 of 10 (2021) |
| Only positive slot | entries 09:30-10:00: 51 trades, 63% wins, +2.4% |

So the +0.1R spot edge does not survive being expressed through bought options: an hour of weekly
ATM theta plus spread and brokerage is about the same size as the edge, and the engine's protective
exits (Supertrend flip, breakeven after T1) cut the 3R winners the edge depends on. Exit reasons were
172 stops, 155 flips, 68 trails, 68 targets.

### What this leaves

1. **Direction is not where the money is on NIFTY intraday.** Nine years of data, 30 mechanical
   price-action setups, four research threads and the regulator's own numbers all point the same way.
   The short-biased VWAP / prior-day-level setups are real but worth ~2-3 index points a trade, which
   only a futures position (no theta, 1-point spread, ~1.3 lakh margin per lot) could keep.
2. **Time and volatility are.** Implied volatility on NIFTY runs above realised on average, expiry-day
   decay is steep, and the only strategies with multi-year positive evidence in India and abroad sell
   premium with defined risk. The price-action and regime work stays useful there, as the filter that
   decides when not to sell (trend days, event days, VIX spikes, gap opens) and which side to lean.
3. **Capital decides feasibility.** A hedged weekly iron condor or fly needs ~30-50k margin per lot;
   a naked straddle ~2.4 lakh. 10k cannot run any of it.

### Recommended next build (if capital allows)

Weekly defined-risk premium selling on NIFTY: short ATM straddle with protective wings bought
~250-300 points out (iron fly), entered after the first 30-45 minutes on non-event, non-trend days as
classified by the existing regime module, hard stop per leg at 1.5x credit, exit at 50-60% of max
profit or 14:45, no positions into expiry afternoon. Validate on the same 9 years first with simulated
premiums, then on recorded live chains. The executor, calendar, risk rails and data layer already
exist; the new work is the structure builder, margin-aware sizing and the hedged backtest.

## 7. The build that followed: iron fly on the 9 years, and on 2026 (2026-10-08)

The recommendation in section 6 was implemented as the `iron_fly` strategy (`engine/premium.py`,
`[sell]` in config.toml) and replayed with real India VIX history (Yahoo, one-off research download)
and Black-Scholes legs. Exit variants, wing widths, entry timing, filters, IV and cost assumptions
were swept (`research/fly_sweep.py`, `fly_sweep2.py`; `logs/fly_sweep*.txt`).

| Variant (2018-2026, 1 lot) | Structures | Win | PF | Net pts | Max DD | 2026 pts |
|---|---|---|---|---|---|---|
| any DTE, 300 wings, stop 1.0x credit (first draft) | 1,026 | 50% | 1.82 | +3,414 | 318 | +148 |
| DTE 3-6 only | 382 | 11% | 0.03 | -2,199 | 2,199 | -275 |
| DTE 0-1 only (expiry day and the day before), 300 wings | 436 | 83% | 5.3 | +5,784 | 121 | +503 |
| DTE 0-1, 400 wings, stop 0.5x credit (**default**) | 436 | 88% | 8.3 | +9,035 | 101 | +875 |
| default with IV = VIX x 1.00 | 436 | 86% | 7.1 | +8,399 | 98 | +833 |
| default with 10-point cost | 436 | 85% | 6.0 | +7,291 | 115 | +739 |
| default without entry filters | 789 | 85% | 5.4 | +15,082 | 266 | +1,389 |
| default, 500 wings | 436 | 90% | 10.3 | +11,020 | 109 | +1,130 |

Findings:

1. **Net theta exists only in the last two sessions.** A 300-400 point fly at 3-6 DTE has almost no
   net decay (the wings decay as fast as the straddle: 182.8 -> 181.3 points over a flat day), so
   every point of realised movement is a loss. The same structure at 0-1 DTE decays 20-40% in a
   session. The DTE restriction is a property of the structure, not a fitted parameter.
2. **Every year is positive at 0-1 DTE**, including 2024, the year that was negative for everything
   else. 2026 to date: 34 structures, 31 winners, +875 points, worst -47.
3. **The result is model-dependent in a known direction.** Constant IV from the previous VIX close
   ignores intraday vega (real losses on trend days are larger), expiry-week skew and the usual
   premium of 0-1 DTE implied vol over VIX. The sign of the edge is robust to IV x0.95-1.05 and to
   cost 6-10 points; the size is not something to plan on until it has been measured on live chains.
4. **The directional buyer stays unprofitable.** `pa_short` through the full engine with real VIX:
   521 trades, PF 0.72; removing the supertrend-flip and breakeven exits (as section 6 suggested)
   improves it only to PF 0.81. The 09:30-10:00 window reaches PF 1.7 on 58 trades in nine years,
   which is not a usable sample.

What is in the code now: the iron-fly engine with regime filters, multi-leg paper/live execution
(wings first, shorts bought back first, unwind on a failed leg), offline backtests from parquet
(`--bars`, `--vix`, `--from`, `--to`, `--strategy`), and the directional engines kept behind
`strategy = "pa_short"` / `"confluence"`.

Next: paper-trade the structure on live Groww chains, record every chain snapshot at entry and exit,
and re-price the 2026 replay with recorded IVs. Only then size it.

### 7b. Final configuration: opportunity-based entries (2026-10-08)

Sweeps 3 and 4 (`logs/fly_sweep3.txt`, `fly_sweep4.txt`) replaced the single 09:45 entry with a
09:45-13:00 window (13:00 on expiry day), up to three structures a day with re-entry after an exit,
and tested each filter and exit one at a time:

| Change from the section-7 default | Structures | Net pts | Max DD | Worst |
|---|---|---|---|---|
| entry window instead of one fixed bar | 498 | +9,755 | 101 | -101 |
| + drop gap filter and ADX filter | 676 | +13,093 | 153 | -101 |
| + hold expiry day to 14:45 | 679 | +16,530 | 183 | -101 |
| + stop at 0.35x credit (**final**) | 680 | +16,714 | 133 | -80 |
| final with 500-pt wings | 679 | +19,259 | 180 | -114 |
| final with no filters at all | 793 | +18,853 | 338 | -117 |

The final configuration is 9 of 9 years positive, 2026: 67 structures, 81% winners, +1,669 points
(Rs 1.25 lakh per lot, every month positive). The 500-point wings and the no-filter variant earn
more but push the per-structure max loss or the drawdown beyond what a 1 lakh account should carry.
Re-entry adds almost nothing (take-profits land after the last-entry time), so "several a day" in
practice means one structure on most eligible days and a second only after an early stop.
The usual caveat applies with more force the further the config is pushed: constant-IV pricing,
no intraday vega, mid fills.

## 8. Option buying only, pushed as far as it goes (2026-10-08)

Requested constraint: no short options. The buyer sweeps (`research/buy_sweep.py`, `buy_sweep2.py`;
`logs/buy_sweep*.txt`) and a decomposition of the engine's 504 `pa_short` trades:

| Variant, 2018-2026 | Trades | Win | PF | Net pts | 2026 pts |
|---|---|---|---|---|---|
| pa_short ATM, 0.5% slippage | 504 | 43% | 0.81 | -640 | -114 |
| only DTE >= 3 (theta nearly zero intraday) | 252 | 41% | 0.70 | -475 | -26 |
| only DTE 0-1 | 171 | 46% | 0.93 | -86 | -166 |
| ATM, fixed 1-pt slippage | 504 | 42% | 0.71 | -1,053 | -141 |
| 300 pts ITM (delta ~0.85), 1-pt slippage | 505 | 44% | 0.88 | -623 | -52 |
| 300 pts ITM, drop vwap_reclaim | 249 | 47% | 0.97 | -84 | -189 |
| 300 pts ITM, drop vwap_reclaim, entries before 12:00 (**config now**) | 158 | 47% | 0.96 | -57 | -118 |
| confluence (v1) | 463 | 38% | 0.62 | -1,293 | -220 |

Why it cannot be made positive: the engine's trades do carry the spot edge (+2.5 index points per
trade on average, the same +0.1 ATR the mechanical study found), but a bought option keeps only
delta x that move, then pays time value and two spreads. Theta is not the main leak (restricting to
3-6 DTE, where intraday decay is near zero, made it worse; 0-1 DTE was the best DTE slice); the leak
is that 2.5 points is smaller than any option's round-trip cost. By trigger, `pdh_sweep` (+18 pts
spot, 19 trades) and morning entries (+14 pts, 58 trades) are the only subsets with meaningful size,
and they are too rare to build on. Overnight NIFTY drift (+0.10%/day 2018-2025, 65% up-gaps) was
checked as a CE-holding idea and has faded: 2025 +0.04%, 2026 -0.01%, 49% up.

Conclusion: the best buying configuration found is break-even before costs over nine years and
negative in 2026. It is wired up as the default so it can be paper-traded, but there is no evidence it
makes money. The defined-risk fly in section 7 remains the only configuration with positive
expectancy, and its margin (about Rs 40k per lot) fits a 1 lakh account.

## 9. Appendices: agent research reports

- [How the big players make money, and the SEBI rule changes](research/big-players.md): Jane Street's alleged expiry-day index push (Rs 4,844 cr impounded), market makers on colocation and FPGAs, Dolat's delta-neutral book; prop desks took ~Rs 44,000 cr in FY26 while individuals lost ~Rs 92,000 cr net. Speed and market-making edges are closed to retail; volatility-premium and event-vol trades are the scaled-down analogues.
- [Systematic option strategies: evidence](research/strategies.md): the volatility risk premium is real (Bakshi-Kapadia, Cboe PUT index ~10%/yr with 24% lower drawdowns than the S&P), delta-hedged long gamma loses on average, the 9:20 straddle edge has faded and is crowded, directional buying has no credible positive evidence. Ranked shortlist: defined-risk condor/fly (2-5 lakh), delta-hedged straddle (5-10 lakh), filtered straddle (3-5 lakh). Nothing is feasible at 10k.
- [NIFTY intraday evidence vs folklore](research/intraday-evidence.md): ORB is a thin PF ~1.2 edge pre-cost, PCR works only at a days horizon, OI walls and max pain are untested, event-day vol selling has paid with fat tails.
- [Price action and SMC/ICT evidence](research/price-action.md): no verified cost-adjusted intraday edge for any price-action or smart-money concept in the literature; StatOasis found order blocks, FVGs and OTE at chance level on US ETFs; Marketcalls found Nifty VWAP and PDH/PDL rules profitable only before costs. Credible tests need fixed definitions, random baselines, multiple-testing control and full costs, which is how section 5 was run.
- [Tooling and costs](research/tooling.md): Groww paid API Rs 499/mo (option chain, candles from 2020), Dhan Rs 499/mo for 5 years of expired option bars, VPS Rs 500-1,000/mo, SEBI retail-algo rules (static IP, 10 orders/sec, daily 2FA, limit orders). Minimal stack ~Rs 1,800/mo. No audited retail track records exist.
