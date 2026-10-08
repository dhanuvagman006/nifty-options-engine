# Systematic NIFTY index-option strategies: evidence review (agent report, 2026-10-08)

Evidence caveat: most sources were abstracts and secondary summaries. [V] = seen in a fetched source; [U] = unverified estimate.

## Evidence by strategy

**(a) Volatility risk premium (short straddle / strangle / condor)**
- Bakshi & Kapadia (RFS 2003): delta-hedged S&P 500 option returns are negative on average, worse in high-vol periods. [V]
- Israelov & Nielsen (JPM 2015, "Still Not Cheap"): delta-hedged puts lose even when IV is low; a 1987-size crash would need to recur every ~10 years for put buying to break even. [V]
- Cboe option-writing indexes 1986-2015: PUT ~10% a year, ~10% st.dev., drawdowns ~24% lower than the S&P 500; negative skew. BFLY worst drawdown 47%, CNDR 19%. [V]
- Practice: held as a small sleeve, delta-hedged, defined-risk wings. A vendor example: a 50% allocation to condors lost 67%. [V]
- India margin: ATM short straddle ~2.4 lakh per lot; iron fly ~0.94 lakh; expiry-day extra 2% ELM; calendar-spread margin offset removed on expiry day. [V]
- Killed by: gap/vol-shock days, clustered losses, leverage.

**(b) Delta-hedged long gamma**
- Pays only when realised vol beats implied: P&L ~ 0.5 x gamma x (RV^2 - IV^2). On average the buyer loses. Works on event days, trend days, regime breaks.
- Vaasa thesis (Kumar 2025): long delta-neutral Nifty straddles consistently negative (theta); weekly short straddles steadier than monthly. [V]

**(c) 9:20 short straddle (intraday)**
- Blog/broker grade only. 20-day sample +434 pts at 60% wins without costs; Marketcalls: edge diminished since 2023, crowded, SL-M stop hunting, 10:30 entry beat 9:20; AlgoTest heatmap (Dec 2024) negative across slots, 50-100 pt stops beat tighter stops; removing the top 10% of trades turns 5 years negative. [V]
- No post-Tuesday-expiry results found.
- Rule changes: weekly expiry only on Nifty (Nov 2024), expiry-day ELM, higher margins, Tuesday expiry from 1 Sep 2025, lot 25 -> 75 (Nov 2024); one source says 65 from Jan 2026 (unconfirmed, check NSE circular).

**(d) Directional option buying**
- No credible positive-expectancy evidence. US retail 0DTE loses ~$358k/day aggregate, >60% of it costs (Beckmeyer et al. 2023). SEBI FY25-26: 87.7% of individual F&O traders lost, ~92% of losses from options; profits went to prop/FPI algos. [V]
- Gao, Han, Li, Zhou (JFE 2018): first half-hour predicts last half-hour on SPY, gross of costs; our own NIFTY test (docs/RESEARCH.md section 2) finds no such effect.
- Upfront premium rule since Feb 2025 removes intraday leverage for buyers.

**(e) India-specific academic work**: weak and conflicting. Hora (2021-2025 working paper): positive VRP, sellers profit in normal regimes, lose in shocks. Vaasa thesis: no seller premium after costs. Bangur: short strangles do better on far-OTM legs. IV forecasts RV better than HV for Nifty (2010-2018).

## Professional operations to copy
Position-level Greeks aggregated across expiries; scenario P&L (spot +/-3-5%, vol +/-5 pts); hard limits on vega, gamma near expiry, daily loss, margin use; threshold delta-hedging with futures; defined-risk wings; event-calendar filters; kill switch; broker position reconciliation; premium sized as a small diversifier.

## Ranked shortlist (1-10 lakh, broker API) - returns are estimates, not measured Nifty results
1. Defined-risk weekly/monthly iron fly or condor with a vol-regime filter. Capital 2-5 lakh (~1 lakh margin per lot). Realistic 8-15%/yr gross, drawdowns 15-30%. [U]
2. Delta-hedged short straddle/strangle at 30-45 DTE, small size. Capital 5-10 lakh. 6-12%/yr with gap tails. [U]
3. 9:20 (or 10:30) straddle with 50-100 pt stops and wings. Capital 3-5 lakh. Crowded; 0-10%/yr. [U]
4. Covered-call overlay only on an existing Nifty holding.
5. Event-day / regime-filtered long gamma as a small satellite, only when forecast RV clearly exceeds IV.
Not recommended: unfiltered directional option buying.

## With only 10k
Nothing above is feasible (fly margin ~0.9 lakh, straddle ~2.4 lakh). A one-lot long option is possible and is exactly the profile SEBI shows losing. Realistic use of 10k: paper-trade and accumulate capital.

## Sources
AQR (Covered Calls; Understanding the VRP; Still Not Cheap), Bakshi & Kapadia RFS 2003, Cboe option-selling index studies, Vaasa thesis (osuva.uwasa.fi/handle/11111/19466), TradingQnA and Marketcalls 9:20 straddle posts, AlgoTest 9:20 page, Zerodha on SEBI rules, Moneylife and Outlook Money on SEBI studies, Business Standard on Tuesday expiry, Beckmeyer et al. 0DTE summary, Alpha Architect on Gao et al.
