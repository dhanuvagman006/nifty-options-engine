"""Iron-fly sweep 4: combinations of the opportunity-adding changes from sweep 3."""
from __future__ import annotations
import sys
from datetime import time
sys.path.insert(0, ".")
sys.argv = [sys.argv[0], "--quick"]
exec(open("research/fly_sweep.py", encoding="utf-8").read().split("run(\"base")[0])  # noqa: S102
A = {"sell.gap_max_pct": 99, "sell.adx_max": 99}
X = {"sell.expiry_exit_time": time(14, 45), "sell.expiry_last_entry_time": time(13, 0)}
run("A: no gap, no adx", **A)
run("B: A + expiry exit 14:45", **{**A, **X})
run("C: B + wing 500", **{**A, **X, "sell.wing_pts": 500})
run("D: no filters + expiry exit 14:45", **{**A, **X, "sell.open_move_max_pct": 99, "sell.vix_max": 99, "sell.vix_spike_ratio": 99})
run("E: A + wing 500", **{**A, "sell.wing_pts": 500})
run("F: A + dte<=3", **{**A, "sell.dte_max": 3.0})
run("G: B + sl 0.35", **{**A, **X, "sell.sl_mult": 0.35})
run("H: B iv x1.00", iv_mult=1.0, **{**A, **X})
run("I: B cost 10", **{**A, **X, "sell.cost_pts": 10.0})
