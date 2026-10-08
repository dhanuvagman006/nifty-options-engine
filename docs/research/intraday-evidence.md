# NIFTY intraday patterns: evidence vs folklore (agent report, 2026-10-08)

Bottom line: no strong, replicated NIFTY-specific evidence for any intraday directional pattern. Grades: P peer-reviewed, W working paper, R regulator, B broker/exchange research, X blog/vendor.

## 1. Intraday momentum / time of day
- Baltussen, Da, Lammers, Martens (JFE 2021, P): across 60+ futures 1974-2020 the rest-of-day return predicts the last 30 min (gamma-hedging mechanism). Global, not NIFTY-specific.
- Gao, Han, Li, Zhou (SPY 1993-2013, P): first half-hour predicts last half-hour; stronger on volatile/news days.
- Motwani, Burrin, Sharma (Indian futures, preprint 2024, W): net-gamma signal at 14:20; worked less well than in the US; no retrievable R2.
- Singh & Gangwar (MPRA 2018, 1-min Nifty futures 2011-2018, W): U-shaped volatility; 11:00-12:00 quietest; hourly vol declined over the sample.
- Our own 9-year test (docs/RESEARCH.md section 2): first-30-min to last-30-min sign agreement 51.1%, correlation -0.04. No effect on NIFTY.
- "All NIFTY gains come overnight" (X, 2000-2023: overnight +39,084 pts vs intraday -15,620) is unverified but directionally consistent with weak intraday drift.

## 2. Gaps and GIFT Nifty
- No published NIFTY gap-fill table; SPY proxy (X): fill falls from 78% (0.1-0.25%) to 26% (1-2%). Our own NIFTY test: 85% -> 20% by gap size, with no directional continuation edge.
- GIFT Nifty as open predictor: only practitioner claims (~95% of open "explained"); mechanism plausible, thresholds untested, must adjust for futures premium.
- Futures lead spot by 10-25 min (Pati & Rajib 2011, P). Irrelevant unless the spot feed is stale.

## 3. Opening-range breakout
- IntradayLab (X): Nifty spot 15-min, Jul 2017-Mar 2026, 30-min OR, 2R target, 2,122 trades: win 48.7%, PF 1.23, Sharpe 1.16, no costs (author estimates 15-25% haircut); 8 of 9 years positive; 51% of trades exited on time, only 13% hit 2R; shorts ~75% of profit; Tuesday weakest, Friday strongest. Code on the page does not match the stated exit rule.
- Bank Nifty 15-min ORB 2015-2023 (X): win 43%, RR 1.54, PF ~1.16.
- US ORB (1.18M trades, X): expectancy near zero.
- Takeaway: ORB on NIFTY is a thin edge (PF ~1.2 before costs) from payoff ratio, not hit rate. Not enough for option buying after theta and spread (our test: avg +0.07% follow-through).

## 4. Trend vs range day
- No published NIFTY study for ADX/ATR/inside-day classification. India VIX beats GARCH for realised-vol forecasting (IIM Calcutta, W). VIX asymmetry: rises more on down moves (P). Use VIX/ATR as volatility regime features; trend-vs-range prediction is unproven (our test: 13% of days are trend days, predictors lift that to ~30% at best with zero average follow-through).

## 5. Expiry day
- SEBI Jane Street order (R): morning index push with short options book, afternoon reversal; "extended marking the close". Evidence that expiry-day spot can be pushed by one very large actor, not a general rule.
- Expiry days and weeks raise spot volatility (NSE 2000-2015, GARCH, P), pre-weekly-expiry era.
- Theta by hour (X): ATM loses 70-80% of remaining value 13:00-15:00 on expiry day, unverified.
- 9:20 short straddle (Quintalmind 2019-2024, X): 65-70% wins with 25% stop, average loss 2-3x average win; real results 15-30% worse.
- Max pain: pinning exists on Indian stock options, no max-pain effect (IIM Bangalore, W). No NIFTY test.
- SEBI FY26 (R): ~44% of predominantly option sellers lost vs ~90% of option buyers; sellers were ~2% of the sample.

## 6. Option-chain signals
- Jena, Tiwari, Mitra (Economies 2019, P; Nifty 2001-2013): volume PCR predicts returns at ~2.5 days, OI PCR at ~12 days. Not intraday; old sample.
- S&P 500 PCR R2 ~0.006 (B). PCR thresholds, OI walls, "OI up + price up = bullish" are untested folklore. No NIFTY IV-skew test found.

## 7. Cross-asset leads
- Bank Nifty leading Nifty intraday: no study. FII/DII flows: published after close; returns drive flows (2024 VAR). USDINR: weak weekly correlation (-18%), no intraday study. US futures: US-only evidence.

## 8. Event days
- Budget day: intraday range 2-3% in 10 of 12 years (B); 15-year average close-to-close 0.19% vs range 2.65% (B). Budget-day short straddle entered the day before: 79% wins, mean +16 pts, worst -195 pts (X, sample unstated).
- 4 Jun 2024 election: ~6% intraday fall, VIX ~27-31. RBI/Fed day data: none found.

## Summary table
| Pattern | Direction | Effect size | Grade | Feature |
|---|---|---|---|---|
| Intraday momentum (first/rest-of-day -> last 30 min) | continuation | global small; NIFTY: none (own test) | B global / C India | rest-of-day return conditioned on vol |
| U-shaped intraday vol, 11-12 lull | - | qualitative, confirmed by own test | B | time-of-day vol scaler |
| Gap size vs fill | bigger gap, lower fill | 85% -> 20% (own test) | B | gap bucket |
| ORB | slight continuation | PF ~1.2 pre-cost, +0.07% own test | C | OR width, breakout flag |
| VIX/ATR regime | wider ranges when high | VIX beats GARCH | B | VIX pct, ATR ratio |
| Trend vs range classifiers | unknown | none measured | D | do not weight |
| Expiry-day push/reversal | morning push, close reversal | one actor, alleged | B existence | expiry flag, hour |
| Theta decay / 9:20 straddle | seller edge, fat tails | 65-70% wins, loss 2-3x win | C/D | minutes to expiry |
| PCR | days-horizon only | modest | C daily / D intraday | slow feature |
| OI walls / max pain | magnet | none shown | D | low weight |
| Event-day vol selling | sell vol | 79% wins, -195 pt tail | C | event flag |

Recommendation: weight only volatility structure (time of day, VIX, ATR, expiry flag) and overnight gap; leave D-grade items unweighted until tested on own data with costs.

Sources: Alpha Architect on Baltussen et al. and Gao et al.; Motwani et al. (ResearchGate); Singh & Gangwar (MPRA 89689); IntradayLab ORB backtest; orbsetups; Saimohanreddy Bank Nifty ORB; Capitalmind gaps; thetrading.tools gap analysis; TradingHub on the SEBI Jane Street order; Jena et al. 2019 (IDEAS); IIM Bangalore pinning paper; Quintalmind straddle study; OptionsIQ Budget straddle; Multibagg overnight vs intraday; Business Standard on SEBI studies.
