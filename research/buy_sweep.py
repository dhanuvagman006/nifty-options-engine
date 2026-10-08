"""Option-BUYING sweep on the 9-year history: which conditions let a bought option keep the spot edge?

    python -u research/buy_sweep.py [--from 2018-01-01]
"""
from __future__ import annotations

import sys

sys.path.insert(0, ".")
sys.argv = sys.argv[:1] + ["--from", "2018-01-01"]
src = open("research/pa_sweep.py", encoding="utf-8").read().split('run("current')[0]
exec(src)  # noqa: S102  reuse setup + run()

B = {"filt.exit_on_flip": False, "filt.breakeven_after_t1": False}
run("pa_short all days (ref)", **B)
run("pa_short dte>=2", **{**B, "filt.buy_dte_min": 2.0})
run("pa_short dte>=3", **{**B, "filt.buy_dte_min": 3.0})
run("pa_short dte>=3 ITM1", **{**B, "filt.buy_dte_min": 3.0, "opt.itm_strikes": 1})
run("pa_short dte>=3 ITM2", **{**B, "filt.buy_dte_min": 3.0, "opt.itm_strikes": 2})
run("pa_short dte>=3 time stop 12", **{**B, "filt.buy_dte_min": 3.0, "filt.time_stop_bars": 12})
run("pa_short dte>=3 t1 1.0 t2 2.0", **{**B, "filt.buy_dte_min": 3.0, "filt.t1_r": 1.0, "filt.t2_r": 2.0})
run("pa_short dte>=3 t1 2 t2 4", **{**B, "filt.buy_dte_min": 3.0, "filt.t1_r": 2.0, "filt.t2_r": 4.0})
run("pa_short dte>=3 sl 0.7", **{**B, "filt.buy_dte_min": 3.0, "filt.sl_atr": 0.7, "filt.sl_min_atr": 0.7})
run("pa_short dte>=3 09:30-11:00", **{**B, "filt.buy_dte_min": 3.0, "filt.pa_entry_end": "11:00"})
run("pa_short dte>=3 no trail", **{**B, "filt.buy_dte_min": 3.0, "filt.trail_after_t1": False})
run("pa_short dte 0-1 only (theta check)", **{**B, "filt.buy_dte_max": 1.99})
run("confluence all days", **{"filt.strategy": "confluence"})
run("confluence dte>=3", **{"filt.strategy": "confluence", "filt.buy_dte_min": 3.0})
run("confluence dte>=3 no flip/BE", **{"filt.strategy": "confluence", "filt.buy_dte_min": 3.0, **B})
