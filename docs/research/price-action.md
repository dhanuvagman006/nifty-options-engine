# Price-action and SMC/ICT evidence review (agent report, 2026-10-08)

Grades: A peer-reviewed with multiple-testing correction; B peer-reviewed or stated-method broker study; C stated-method blog/vendor backtest; D folklore.

## Bottom line
- No price-action or SMC concept has a verified, cost-adjusted intraday edge on NIFTY or Bank Nifty in the literature.
- Best evidence is for mechanical level features: round numbers, prior-day levels, opening range / first-half-hour direction. Edges are small and costs eat most of them.
- Candlestick patterns and discretionary SMC concepts have no positive out-of-sample evidence.

## Chart and candlestick patterns
- Lo, Mamaysky & Wang (2000, J. Finance; US stocks 1962-1996): several patterns carry incremental information; trading profits not tested. B.
- Caginalp & Laurent (1998; S&P 500 stocks 1992-1996): 3-day candlestick patterns ~1% over 2 days; one window, not replicated. B.
- Marshall, Young & Rose (2006; DJIA 1992-2002, 28 signals, 10-day hold): no signal predicts price; holds in subperiods. B, negative.
- Indian studies: Manoharan & Mamilla (17 Nifty stocks 2000-2015) report Harami profitable without significance tests; a 2025 Welch t-test on bullish engulfing in six large caps: no edge (p ~0.87 at 1 day). The circulating "65% after hammer" claim has no source. D.
- Park & Irwin (2007 survey): 56 of 95 studies positive, profits concentrated before the 1990s and weakened under snooping and cost controls. A.

## Support/resistance, round numbers, stop clustering
- Osler (2000, 2003; FX): dealer S/R levels interrupt intraday trends; stop-loss and take-profit orders cluster at round numbers; trends accelerate through stop clusters (continuation, not reversal). B, FX only.
- "Liquidity sweep reversal": no futures/index study; StatOasis SPY (547 events, +0.119% at 5 days, t=0.94) not significant. C.
- Round numbers in US stocks: 5-20 bp/day drift, judged unprofitable standalone. B.
- Marketcalls PDH/PDL breakout on Nifty futures (1-min, 2010-2017): long+short 797 trades, 37% wins, 17% a year with 47% drawdown; long-only profitable, short-only not, with 0.02% costs. C.

## SMC / ICT
- No independently verified ICT track record. D.
- StatOasis (2026; SPY/QQQ/DIA/IWM daily, 648 backtests, random-entry baselines, no costs): order block 736 events t=1.22; FVG 1,122 events t=-0.08; OTE t=-0.17; only 1 of 32 t-stats above 2 (chance level); none beat buy-and-hold. BOS/CHoCH untested. C.
- Backtrex (vendor; 1h FVG + 15m engulfing on Nasdaq 100, 10 years): ~27% wins over 852 trades. C.
- "64.8% of 15m FVGs revisited" and "order block PF 1.3-1.8": no method. D.

## Market profile / auction
No independent tests of open types, the 80% value-area rule or initial-balance extension; published IB rates are vendor NQ numbers and do not transfer. D.

## VWAP and intraday momentum
- Zarattini & Aziz VWAP (QQQ/TQQQ 2018-2023): big claimed growth; independent replication shows Sharpe decaying to ~0.7 and the edge gone above ~1 bp round-trip cost. C.
- Gao, Han, Li & Zhou (JFE 2018; SPY 1993-2013): first half-hour predicts last half-hour, stronger on volatile days. B. (Own NIFTY test: no effect.)
- Zarattini, Aziz & Barbon SPY intraday momentum: claimed Sharpe 1.33 net; re-implementations weaker. C.
- ORB replication on five index CFDs 2015-2026: gross reproduces, net about zero. C.
- Marketcalls Nifty VWAP (15m, 2011-2019, 30-pt target / 20-pt stop): profitable only before costs; Bank Nifty unprofitable even before costs. C.

## NIFTY price action
No published win-rate backtests for pin bar, inside bar, NR7 or engulfing on Nifty/Bank Nifty 5m/15m. Bank Nifty 2PM ORB 48% wins ignores costs. Al Brooks setups: no quantitative test; measured-move hit rates reported ~50-52%. Grant, Wolf & Yu (JBF 2005): US index futures intraday reversals sharply reduced after a bid-ask cost proxy. B.

## Meta-evidence
Sullivan, Timmermann & White (1999): 7,846 rules on 100 years of DJIA, significant in-sample, gone out-of-sample. Bajgrowicz & Scaillet (JFE 2012): FDR control, low costs cancel in-sample performance. A. Credible test = mechanical definitions fixed in advance, declared rule universe with multiple-testing correction, frozen out-of-sample, random-entry baseline, full costs, de-clustered events, expectancy and trade count reported.

## Summary table
| Concept | Best evidence | Grade | Testable rule |
|---|---|---|---|
| Round-number / prior-day H/L reaction | Osler (FX); Marketcalls PDH/PDL Nifty | B/C | touch of x50/x100 or PDH/PDL; forward 5/15/30-min return vs matched random times |
| Liquidity sweep reversal | StatOasis t=0.94 | C/D | wick beyond 20-bar low or PDL by >=0.1 ATR, close back inside within 3 bars |
| BOS / CHoCH | none | D | close beyond 3-bar fractal swing, vol-scaled stop |
| Order block | StatOasis t=1.22 | C | down-close bar then >=1.5 ATR impulse in 3 bars; enter first retrace |
| FVG | StatOasis t=-0.08; Backtrex 27% | C | 3-bar gap >=0.3 ATR; enter on retest; 1R-2R exits |
| Candlesticks | Marshall null; Caginalp positive | B | engulfing/pin bar with range filter at a level |
| Opening range / first-half-hour direction | Gao et al.; ORB net ~0 | B/C | first-30-min vs last-30-min; 15-min ORB with 1:1-1:2 targets |
| VWAP side / reclaim / rejection | Marketcalls Nifty pre-cost only | C | close beyond VWAP by >=0.1 ATR, retest within 6 bars, one trade/day |
| IB extension, open types, 80% rule | vendor NQ only | D | IB = first 60 min; measure reach vs time-matched controls |
| Gap fill | illustrative tables | D | 0.2-0.6% gaps; fill = touch prior close by 10:30 |

Suggested weighting: no SMC, candlestick or auction features as standalone signals; level-proximity, VWAP-side and opening-direction only as candidates after an own out-of-sample test with multiple-comparison control and Indian costs.

Sources: NBER 7613 (Lo et al.), CFA Digest, SAGE summary of Caginalp & Laurent, CXO on Marshall et al. and on Sullivan et al., IJISRT 2025 engulfing study, Park & Irwin (IDEAS), NY Fed Osler papers (EPR 2000, Staff Reports 125 and 150), Marketcalls PDH/PDL and VWAP studies, StatOasis ICT backtest, Backtrex FVG page, Concretum VWAP, WashU profile of Gao et al., SFI paper on SPY intraday momentum, MQL5 ORB replication, TradingQnA 2PM ORB, Bajgrowicz & Scaillet.
