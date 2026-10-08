"""Option-buying sweep 2: deep ITM (futures-like) expression with fixed-point slippage."""
from __future__ import annotations
import sys
sys.path.insert(0, ".")
sys.argv = sys.argv[:1] + ["--from", "2018-01-01"]
src = open("research/pa_sweep.py", encoding="utf-8").read().split('run("current')[0]
exec(src)  # noqa: S102
B = {"filt.exit_on_flip": False, "filt.breakeven_after_t1": False, "opt.slippage_pts": 1.0, "opt.max_premium": 2000.0}
run("ATM, 1pt slip", **B)
run("ITM2 (100 pts), 1pt slip", **{**B, "opt.itm_strikes": 2})
run("ITM4 (200 pts), 1pt slip", **{**B, "opt.itm_strikes": 4})
run("ITM6 (300 pts), 1pt slip", **{**B, "opt.itm_strikes": 6})
run("ITM6, 2pt slip", **{**B, "opt.itm_strikes": 6, "opt.slippage_pts": 2.0})
run("ITM6 dte>=3, 1pt slip", **{**B, "opt.itm_strikes": 6, "filt.buy_dte_min": 3.0})
run("ITM6 no vwap_reclaim", **{**B, "opt.itm_strikes": 6, "filt.pa_triggers": "vwap_reject,pdh_sweep,pdl_break"})
run("ATM no vwap_reclaim", **{**B, "filt.pa_triggers": "vwap_reject,pdh_sweep,pdl_break"})
run("ITM6 no reclaim, 09:30-12:00", **{**B, "opt.itm_strikes": 6, "filt.pa_triggers": "vwap_reject,pdh_sweep,pdl_break", "filt.pa_entry_end": "12:00"})
run("ATM no reclaim, 09:30-12:00", **{**B, "filt.pa_triggers": "vwap_reject,pdh_sweep,pdl_break", "filt.pa_entry_end": "12:00"})
