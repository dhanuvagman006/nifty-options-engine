# How the large Indian index-derivatives players make money (agent report, 2026-10-08)

Firm-level profit and infrastructure claims come from job postings, rating notes or press unless marked as read from a SEBI document.

## Firm by firm

**Jane Street (SEBI interim order, 3 Jul 2025, read directly)**
- Jan 2023 to Mar 2025: Rs 36,502 cr total; index options Rs 43,289 cr; stock futures, index futures and cash lost Rs 7,687 cr. BANKNIFTY options alone Rs 17,319 cr.
- Alleged pattern on 15 BANKNIFTY expiry days: morning aggressive buying of constituents and futures (Rs 4,370 cr) while holding a bearish options book ~Rs 32,115 cr cash-equivalent (long puts, short calls); from ~11:49 reverse the cash/futures leg (Rs 5,372 cr) so the index falls into expiry. The cash leg lost Rs 199.7 cr; the options leg paid for it. Best day 17 Jan 2024: Rs 734.9 cr options profit.
- Also alleged: "extended marking the close" on 3 BANKNIFTY and 3 NIFTY days (May 2025). NSE caution letter 6 Feb 2025; pattern allegedly repeated 15 May 2025.
- Rs 4,843.57 cr impounded (options profit on 21 identified days). Ban lifted after deposit in Jul 2025. Jane Street calls it index arbitrage; case was still at SAT in Oct 2026.
- Why it worked: options settle off an index that is a basket of ~12 liquid bank stocks; the options book was ~7x the cash trade. Margin posted: Rs 15,325 cr of government securities.

**Graviton**: fully automated short-hold alpha and market making; FPGA / kernel-bypass stack per job postings; revenue figures conflict; raided by the income-tax department Oct 2025.
**AlphaGrep**: latency-sensitive prop, FPGA developers, among the largest by volume; no profit data.
**Quadeye**: low-latency C++ market making; no profit data.
**Tower Research**: HFT market maker (Gurugram, GIFT City); minority stake in NCDEX Aug 2025.
**Dolat Algotech (CRISIL, Mar 2026)**: "risk neutral delta hedged" F&O, arbitrage and HFT, no directional bets. PAT Rs 405 cr FY25, Rs 127 cr H1 FY26 (down from Rs 241 cr): CRISIL blames SEBI rules, higher STT and price shocks hurting delta-neutral books. RBI from 1 Apr 2026: 100% collateral for bank guarantees in prop trading.
**Optiver / IMC**: classic options market makers; Optiver ~70 India staff in 2024, IMC heading past 150 by end-2026.
**Citadel Securities**: ~10 India staff mid-2025; first full year revenue ~Rs 2,900 cr, net ~Rs 1,468 cr (secondary source); NSE membership segments unconfirmed.

**Industry totals (SEBI study, 20 Aug 2026)**: prop traders ~Rs 44,000 cr gross in FY26; top 10 prop entities took ~75% of that and ~85% of option volume; 99% of prop/FPI profit came from algo entities. Individuals lost ~Rs 91,685 cr net, paying ~Rs 25,000 cr in costs.

## Edge taxonomy

| Edge | Who | Why it works | Retail-replicable |
|---|---|---|---|
| Two-sided options market making (spread capture) | Optiver, IMC, Graviton, Tower, Quadeye, AlphaGrep | Colocation, FPGA, tick data, microsecond hedging | No |
| Latency arbitrage cash/futures/options | Graviton, AlphaGrep, Dolat | Sub-second mispricings | No |
| Cross-exchange NSE/BSE arbitrage | same | Ultra-fast links to both | No |
| Slow parity arbitrage | Dolat, Jane Street | Small, thin after STT hike | Marginal |
| Delta-neutral volatility trading | Dolat, Jane Street, IMC | Systematic hedging and inventory at scale | Partial |
| Expiry-day index-influence trades (alleged) | Jane Street | Enormous size | No (and contested conduct) |
| Volatility risk premium harvesting | everyone at scale | IV usually exceeds RV | Partial, defined risk |
| Event-vol trades (RBI, Budget, results) | prop desks | IV ramp and crush are semi-predictable | Partial |
| Expiry-day structure trades | prop and retail | 59% of index-option turnover still on expiry day | Partial, harder after 2024-25 rules |

Why the fast edges are closed: broker API order path is milliseconds vs microseconds in colocation; no tick-level direct feed; capital orders of magnitude smaller; member/FPI status. The Feb 2025 retail-algo framework caps unregistered strategies at 10 orders/second, needs OAuth, 2FA and (per most sources) a static IP.

Realistic scaled-down analogues: defined-risk variance harvesting (condors, calendars, ratio spreads with wings, sized small), event-vol structures around scheduled events, slow hedged structures where the edge is risk premium, not speed. Expect thin edges: 87.7% of individuals lost net of costs in FY26.

## SEBI and tax changes 2024-2026

| Date | Change |
|---|---|
| 1 Oct 2024 circular | Contract value Rs 15-20 lakh; one weekly index per exchange; upfront option premium; no expiry-day calendar-spread benefit; extra margin on expiry-day shorts; intraday position monitoring |
| 20 Nov 2024 | Weekly BANKNIFTY/FINNIFTY/MIDCPNIFTY end; NIFTY weekly only on NSE; +2 pts ELM on expiry-day shorts; NIFTY lot 25 -> 75 |
| 1 Feb 2025 | Premium upfront; calendar-spread benefit removed on expiry day |
| 1 Apr 2025 | Intraday position-limit monitoring (sources vary) |
| 26 May 2025 | All expiries on Tuesday or Thursday |
| 1 Sep 2025 | NIFTY weekly moves to Tuesday; Sensex to Thursday |
| 1 Sep 2025 circular | Intraday index-derivative limits Rs 5,000 cr net / Rs 10,000 cr gross, 4+ random snapshots a day; expiry-day penalties from 6 Dec 2025 |
| 8 Dec 2025 | Pre-open call auction for F&O |
| Jan 2026 series | NIFTY lot 65, BANKNIFTY 30 (unconfirmed; check NSE circular) |
| 1 Apr 2026 (or 1 Feb) | STT futures 0.02% -> 0.05%, option premium 0.10% -> 0.15% |
| 1 Apr 2026 | Retail algo framework mandatory (10 orders/sec threshold) |

Impact: expiry-day share of index-option turnover fell from 70% to 59%; NSE premium turnover down ~26-29%; higher STT and pricier lots hurt scalpers most; expiry-day short-gamma faces higher margin and no spread offset.

## Most credible sources
SEBI interim order on Jane Street (3 Jul 2025); SEBI "Profitability of Individual Traders in the Equity Derivatives Segment FY25-FY26" (Aug 2026, sebi.gov.in/sebi_data/attachdocs/aug-2026/1787233506209.pdf); SEBI circulars 1 Oct 2024, 26 May 2025, 1 Sep 2025; CRISIL rating rationale on Dolat Algotech (Mar 2026); Reuters 20 Jun 2025 on global trading firms in India; Business Today / Business Standard on the SAT hearings (6 Oct 2026); Bloomberg on Citadel Securities India (Jan 2026) and prop profits (Aug 2026).
Unverified: firm-level profits for Graviton/Quadeye/AlphaGrep/Tower; Citadel's NSE membership; STT effective date; intraday-limit effective date; whether the Jane Street case has a final order.
