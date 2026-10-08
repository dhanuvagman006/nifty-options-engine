# Retail systematic NIFTY options stack, India, Oct 2026 (agent report)

Mostly vendor blogs and forum posts; NSE circulars/FAQ could not be opened directly.

## Historical option prices
| Source | Option history | Cost | Confidence |
|---|---|---|---|
| Groww API (paid) | candles 1m-1M from 2020 plus Expiries/Contracts endpoints (changelog 3 Oct 2025) | included in plan | whether expired strikes are gap-free is unverified; test first |
| Dhan Data API | expired options up to 5 years, 1/5/15/25/60-min bars with OI, IV, volume, spot; rolling ATM+/-N strikes, 30-day window per call | Rs 499/mo + tax | docs solid, quality unverified |
| Zerodha Kite | no expired options | Connect Rs 500/mo | - |
| Upstox | expired-contract API, users report missing weeklies / 404s | not found | weak |
| TrueData | 1-min and tick over REST; F&O depth unpublished; API excluded from Rs 1,440-2,288/mo plans | quote-based | opaque |
| GDFL | tick/1-min on request; ~Rs 17,400/yr (2018 quote) | stale | - |
| Free GitHub/Kaggle option dumps | inconsistent strike counts | free | avoid for serious work |
Many vendors resell NSE 1-second snapshots as "tick"; ask explicitly.

## Broker APIs
| Broker | Cost | Notes |
|---|---|---|
| Groww | free tier: orders, OCO/GTT, positions, margin only. Paid (Rs 499/mo or Rs 4,999/yr + 18% GST): live quotes, option chain + Greeks, historical candles | limits 10 orders/s, 250/min; 10 live-data calls/s, 300/min; 20 non-trading/s, 500/min; 1,000-3,000 feed subscriptions; 5 sessions; daily token (TOTP/OAuth); static IP required for self-hosted order placement (Groww Cloud avoids it). API first released Oct 2025, young; no API-specific outage reports found (consumer app froze on expiry days, Jan 2024 outage) |
| Zerodha Kite | free orders, Rs 500/mo with data | mature; median order latency 99 ms |
| Dhan | trading free; data Rs 499 | slowest in AlgoTest speedtest: median 124 ms, p90 272 ms |
| Upstox | free | median 120 ms |
| Fyers | free | median 92 ms; daily 2FA; no shared IPs |
| Angel SmartAPI | free | median 95 ms; static IP only for Orders/GTT |
Latency figures are AlgoTest's own Sept-2026 speedtest; Groww not tested.

## Backtest platforms
AlgoTest (25 free backtests/week; packs Rs 499-5,999; claims 7.5+ years with slippage; data source unstated), StockMock (freemium; Nifty from 2019), Tradetron (Rs 300-15,000/mo, Rs 20/backtest, data from 2020), QuantMan (Rs 1,300-3,300/mo), Streak (free for Zerodha; no options backtests on new platform), OpenAlgo (free self-hosted execution bridge with a Groww connector of unverified maturity). None states whether it uses recorded bid/ask or traded candles. Backtest on your own data pull.

## VPS
No measured latency to NSE/Groww found; measure yourself. AWS Lightsail Mumbai from $3.50/mo (+$3.60/mo public IPv4); DigitalOcean Bangalore $4-6/mo (reserved IP free while attached); E2E ~Rs 2,450/mo for 2 cores with dedicated IP (2025 listing; prices changed 1 Jul 2026). For a few trades a day the provider does not matter; a stable IP and 09:15 availability do.

## SEBI/NSE retail algo framework (circular 4 Feb 2025; fully applicable 1 Apr 2026)
- Register one primary static IP (+ optional backup) with the broker; order placement needs it, data calls generally do not; one IP per client (family exception); changes ~weekly.
- Under 10 orders/second per exchange-segment: no registration, generic Algo-ID, one API key per user. Above: exchange registration.
- Daily 2FA; sessions logged out end of day.
- Do not distribute strategies; third-party strategies need an empanelled vendor; black-box needs an RA licence.
- Market orders may be converted to market-protection orders; one summary says an NSE FAQ bars market orders from algos: use marketable limit orders.
- Broker keeps API logs, applies risk checks, can shut the algo down.
Sources disagree on whether registration is needed below 10 OPS (Kotak, Angel say yes). NSE circular NSE/INVG/73992 (Client Direct API category) could not be read. Confirm with Groww support in writing.

## Track records
No verifiable audited retail NIFTY algo track record found. Zerodha Verified P&L lets the holder pick the window (selection effect). SEBI: ~91% of individual F&O traders lost in FY25 (avg ~Rs 1.1 lakh); ~96% of prop profit from algos (unverified against the primary doc). Treat any retail consistency claim as weak unless 360-day verified P&L net of costs.

## Recommended minimal stack (1-lot NIFTY)
| Item | Choice | Rs/month |
|---|---|---|
| Execution + live data | Groww paid API | 490-590 incl. GST |
| VPS with static IP | DigitalOcean BLR or AWS Mumbai 1 vCPU | 500-1,000 |
| Historical option data | Groww history; Dhan Data as one-off cross-check | 0-590 |
| Backtest tooling | AlgoTest free tier or own code | 0-499 |
| Total | | ~1,000-2,700, typically ~1,800 |

Build order: (1) before paying for anything else, pull 3 months of expired NIFTY option 1-min candles from Groww and Dhan, check bars/day vs 375 and compare closes; (2) record live option-chain snapshots daily from now on (nobody sells historical bid/ask cheaply); (3) paper-trade with limit orders and realistic slippage before going live.

Sources: Groww changelog and blog (API trading, static IP setup), Groww SDK docs, Dhan expired-options docs and support, Zerodha Kite forum and support, Upstox community, TrueData pricing/blog, marketcalls on GDFL and data quality, AlgoTest pricing/speedtest/FAQ, TradingQnA threads, OpenAlgo GitHub, AWS/DigitalOcean pricing pages, Sahi and Fyers on the SEBI algo rules, Zerodha Z-Connect on the NSE retail algo circular, Business Standard on SEBI studies.
