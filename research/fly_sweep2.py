"""Second iron-fly sweep: entries restricted to the last three sessions before expiry (dte <= 2),
where the structure actually has net theta (at 3-6 DTE the wings decay as fast as the straddle).

    python -u research/fly_sweep2.py
"""
from __future__ import annotations

import sys
from datetime import time

sys.path.insert(0, ".")
sys.argv = [sys.argv[0], "--quick"]
exec(open("research/fly_sweep.py", encoding="utf-8").read().split("run(\"base")[0])  # noqa: S102  reuse setup + run()

D = {"sell.dte_max": 2.0, "sell.sl_mult": 0.5}
run("dte<=2 wing300 sl.5 iv1.05", **D)
run("dte<=2 wing300 sl.5 iv1.00", iv_mult=1.0, **D)
run("dte<=2 wing300 sl.5 iv0.95", iv_mult=0.95, **D)
run("dte<=2 wing400 sl.5 iv1.05", **{**D, "sell.wing_pts": 400})
run("dte<=2 wing400 sl.5 iv1.00", iv_mult=1.0, **{**D, "sell.wing_pts": 400})
run("dte<=2 wing500 sl.5 iv1.05", **{**D, "sell.wing_pts": 500})
run("dte<=2 wing400 sl.35", **{**D, "sell.wing_pts": 400, "sell.sl_mult": 0.35})
run("dte<=2 wing400 cost 10", **{**D, "sell.wing_pts": 400, "sell.cost_pts": 10.0})
run("dte<=2 wing400 expiry exit 14:45", **{**D, "sell.wing_pts": 400, "sell.expiry_exit_time": time(14, 45)})
run("dte<=2 wing400 entry 10:15", **{**D, "sell.wing_pts": 400, "sell.entry_time": time(10, 15)})
run("dte<=2 wing400 no filters", **{**D, "sell.wing_pts": 400, "sell.gap_max_pct": 99, "sell.open_move_max_pct": 99,
                                   "sell.vix_max": 99, "sell.vix_spike_ratio": 99, "sell.adx_max": 99})
run("dte<=1 wing400", **{**D, "sell.wing_pts": 400, "sell.dte_max": 1.0})
run("dte 0 wing400", **{**D, "sell.wing_pts": 400, "sell.dte_max": 0.99})
run("dte 0 wing300", **{**D, "sell.dte_max": 0.99})
