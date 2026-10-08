"""Iron-fly sweep 3: opportunity-based entries (window + re-entry + several structures a day),
each filter removed one at a time, take-profit levels that make re-entry worthwhile.

    python -u research/fly_sweep3.py
"""
from __future__ import annotations
import sys
from datetime import time
sys.path.insert(0, ".")
sys.argv = [sys.argv[0], "--quick"]
exec(open("research/fly_sweep.py", encoding="utf-8").read().split("run(\"base")[0])  # noqa: S102

run("new default (window 09:45-13:00, 3/day, reentry)")
run("1 per day (old)", **{"sell.max_structures_per_day": 1})
run("tp 0.3", **{"sell.tp_frac": 0.3})
run("tp 0.4", **{"sell.tp_frac": 0.4})
run("tp 0.3 cooldown 0", **{"sell.tp_frac": 0.3, "sell.reentry_cooldown_bars": 0})
run("no reentry after SL", **{"sell.reentry_after_sl": False})
run("last entry 14:00 / expiry 13:00", **{"sell.last_entry_time": time(14, 0), "sell.expiry_last_entry_time": time(13, 0)})
run("expiry exit 14:45", **{"sell.expiry_exit_time": time(14, 45)})
run("expiry exit 14:45 + last entry 13:00 on expiry", **{"sell.expiry_exit_time": time(14, 45), "sell.expiry_last_entry_time": time(13, 0)})
run("no gap filter", **{"sell.gap_max_pct": 99})
run("no open-move filter", **{"sell.open_move_max_pct": 99})
run("no vix level filter", **{"sell.vix_max": 99})
run("no vix spike filter", **{"sell.vix_spike_ratio": 99})
run("no adx filter", **{"sell.adx_max": 99})
run("no filters at all", **{"sell.gap_max_pct": 99, "sell.open_move_max_pct": 99, "sell.vix_max": 99, "sell.vix_spike_ratio": 99, "sell.adx_max": 99})
run("dte<=3 (adds the day before Monday)", **{"sell.dte_max": 3.0})
run("wing 500", **{"sell.wing_pts": 500})
run("sl 0.35", **{"sell.sl_mult": 0.35})
run("5 per day", **{"sell.max_structures_per_day": 5})
