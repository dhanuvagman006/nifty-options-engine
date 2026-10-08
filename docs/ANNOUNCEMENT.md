# Launch posts

Copy as-is. Repo: https://github.com/dhanuvagman006/nifty-options-engine
GitHub topics to set on the repo (About, gear icon): `nifty` `options` `algo-trading` `india` `groww`
`quant` `backtesting` `price-action` `options-trading` `python`

---

## Reddit (r/IndiaInvestments, r/IndianStreetBets, r/algotrading)

**Title:** I tested 30 price-action setups and 3 option strategies on 9 years of NIFTY 5-minute data. Almost nothing survives costs. Here is what did, with code and data.

Over the last few weeks I built an open-source NIFTY options engine and, before trusting it with
money, ran every popular intraday idea I could define mechanically through nine years of 5-minute
data (April 2017 to October 2026, about 176,000 bars, real India VIX). Train on 2017-2022, test on
2023-2026, random-entry baselines, costs charged on every trade. Repo with the data, the code and
every table: https://github.com/dhanuvagman006/nifty-options-engine

**What does not work on NIFTY intraday**

- Buying calls on any setup. NIFTY's intraday drift is negative; the index makes its money overnight. Every long-side mirror of every setup lost.
- Smart-money concepts. Break of structure with retest, order blocks, fair value gaps, session liquidity sweeps, round-number rejections: all at or below the random baseline. The published literature says the same (StatOasis found order blocks and FVGs at chance level on US ETFs).
- Opening-range breakouts, gap fades, first-half-hour predicting the last half-hour: no net edge after costs.
- A multi-factor "confluence" option buyer (EMA stack, ADX, RSI, Supertrend, VWAP, option-chain PCR and OI walls, the usual): profit factor 0.62 over nine years, 463 trades. Looked great on a 42-session sample (PF 2.5). That is the trap.

**What does work, a little**

Four short-side setups are real: VWAP rejection, VWAP reclaim, prior-day-high sweep, prior-day-low break-and-hold, each on a bearish 5-minute bar with the 15-minute trend down. With a 1 ATR stop and 3 ATR target they earn about +0.11R per trade after costs over 2,570 trades (t = 3.2), positive in both halves of the data.

**Why that still does not pay as an option buyer**

That edge is about 2.5 index points per trade. An ATM weekly put keeps delta times that, then pays time value and two spreads. I tried everything: ITM strikes up to 300 points, only 3-6 days to expiry (where intraday theta is near zero), morning-only entries, dropping the weakest trigger. Best case is profit factor 0.96, negative in 2026. Theta is not even the main leak; 2.5 points is just smaller than an option's round trip.

**What the data supports: selling time, hedged, in the right two sessions**

Implied vol on NIFTY runs about 1.27x realised on average, every year. A weekly iron fly (short ATM straddle, long wings 400 points out, defined max loss) sold at 09:45-13:00 and closed by 14:45:

| 2018-2026, one lot, simulated premiums on real bars | |
|---|---|
| Structures | 680 |
| Win rate | 83% |
| Profit factor | 6.0 |
| Net | +16,714 points (Rs 12.5 lakh) |
| Worst structure / max drawdown | Rs 6,000 / Rs 10,000 |
| Positive years | 9 of 9 |

The finding that matters: **only the expiry day and the session before it carry net theta.** At 3-6 days to expiry a 400-point fly barely decays (the wings decay as fast as the straddle) and it loses on 89% of days. At 0-1 DTE it wins 85-90%. That restriction is structural, not fitted.

**Please read this part**

Premiums are Black-Scholes at a constant IV from the previous VIX close. The model does not see intraday IV rising on trend days, 0-1 DTE skew, or real fills versus mid. 2025 and 2026 were inside the data used to pick parameters. I have not traded this live; the free Groww API plan refuses market data, so live paper trading starts when the paid plan is on. Treat every number as an upper bound. SEBI's own numbers say most individual option traders lose; nothing here changes that for someone who skips the paper-trading month.

Everything is reproducible: `python run.py backtest --bars data/nifty_5m_2017_2026.parquet --from 2018-01-01`. Sweep tables, trade lists and the research write-up are in `docs/`. MIT licence. The most valuable contribution right now is recording live option chains so the model can be checked against reality (issue #1). Happy to answer questions on method; not giving trading advice.

---

## Hacker News (Show HN)

**Title:** Show HN: Open-source NIFTY options engine, plus 9 years of evidence on what does not work intraday

**Text:**

I built a Python engine for Indian index options (NIFTY weeklies on the Groww API) and, before
trusting it, tested the common intraday ideas on nine years of 5-minute data with train/test split,
random baselines and costs. Repo, data and every table: https://github.com/dhanuvagman006/nifty-options-engine

Findings, briefly:

- No intraday directional edge survives an option's round-trip cost. The best price-action setups (VWAP rejection/reclaim, prior-day-level sweeps, short side only) earn ~2.5 index points per trade, t = 3.2 over 2,570 trades, and every option expression of them loses (best profit factor 0.96).
- "Smart money" setups (order blocks, FVGs, liquidity sweeps, BOS) sit at the random baseline.
- A multi-factor buyer that showed PF 2.5 on 42 sessions shows PF 0.62 on nine years. Small-sample backtests are the industry's main product.
- Selling a hedged weekly iron fly works in simulation (680 structures, 83% win, PF 6, positive every year), but only on expiry day and the day before: earlier in the week the wings decay as fast as the straddle, so the structure has no net theta and loses 89% of days.

Engineering bits that might interest people here: numba-compiled indicators, a feature frame with no look-ahead (15m features aligned by bar end time, daily features from the previous day, fractional days-to-expiry), Black-Scholes leg pricing from real VIX, and one code path shared by backtest, paper replay and live execution (the paper executor writes the exact four-leg order sequence it would send).

Caveats are real: premiums are simulated at constant IV (no intraday vega), 2025-2026 are in-sample for parameter choice, and it has not traded live yet. The open issue that matters is recording live option chains to check the model against reality. MIT licensed. Not advice.
