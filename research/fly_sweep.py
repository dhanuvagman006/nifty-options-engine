"""Sensitivity sweep for the iron-fly engine on the 9-year 5m history.

    python research/fly_sweep.py [--from 2018-01-01] [--quick]

Builds the feature frame once and replays the engine under parameter variants, printing one row per
variant: trades, win %, profit factor, net points, max drawdown, worst trade and the per-year points
for 2024 and 2026 (the two weakest / most recent years). Used to pick *structurally* sensible defaults
and to show how fragile the result is to the IV assumption, not to pick the best cell.
"""
from __future__ import annotations

import argparse
import copy
import sys
from datetime import time

import pandas as pd

sys.path.insert(0, ".")
from nifty_signals.backtest.runner import run_backtest  # noqa: E402
from nifty_signals.config import Config  # noqa: E402
from nifty_signals.indicators.core import warmup  # noqa: E402
from nifty_signals.live import DataHub  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--from", dest="start", default="2018-01-01")
ap.add_argument("--quick", action="store_true")
a = ap.parse_args()

warmup()
base = Config.load("config.toml")
base.filt.strategy = "iron_fly"
base.data.csv_path = "cache/hist_5m.parquet"
base.data.vix_path = "cache/india_vix_1d.parquet"
base.data.use_chain = False
hub = DataHub(base)
feats = hub.load(4000)
start = int((feats.index < pd.Timestamp(a.start, tz="Asia/Kolkata")).sum())
print(f"{len(feats)} bars, replay from {feats.index[start]}")


def run(label: str, iv_mult: float = 1.05, **over):
    cfg = copy.deepcopy(base)
    for k, v in over.items():
        sec, key = k.split(".")
        setattr(getattr(cfg, sec), key, v)
    from nifty_signals.backtest import runner
    from nifty_signals.engine.calendar import ExpiryCalendar
    from nifty_signals.engine.signals import make_engine

    eng = make_engine(cfg, 5, cal=ExpiryCalendar(cfg.session), iv_mult=iv_mult)
    eng.state.last_i = start - 1
    for i in range(start, len(feats)):
        eng.on_bar(feats, i)
    tr = pd.DataFrame(eng.state.trades)
    sessions = int(feats["session"].iloc[start:].nunique())
    m = runner.metrics_for(tr, cfg, 0.0, sessions)
    if not m:
        print(f"{label:<44} no trades")
        return
    by = m["by_year"]
    print(f"{label:<44} n {m['trades']:>5}  win {m['win_rate']:>4.0f}%  PF {m['profit_factor']:>4.2f}  "
          f"net {m['total_pts']:>+6.0f}  dd {m['max_dd_pts']:>4.0f}  worst {m['worst_pts']:>+5.0f}  "
          f"2024 {by.get(2024, '-'):<18} 2026 {by.get(2026, '-'):<18} exits {m['reasons']}")


run("base (tp .5 sl 1.0 wing 300 iv x1.05)")
run("iv x1.00", iv_mult=1.0)
run("iv x0.95", iv_mult=0.95)
run("iv x0.90", iv_mult=0.90)
run("sl 0.5", **{"sell.sl_mult": 0.5})
run("sl 0.35", **{"sell.sl_mult": 0.35})
run("sl 0.5 tp 0.3", **{"sell.sl_mult": 0.5, "sell.tp_frac": 0.3})
run("sl 0.5 tp 0.2", **{"sell.sl_mult": 0.5, "sell.tp_frac": 0.2})
run("sl 0.5 iv x1.0", iv_mult=1.0, **{"sell.sl_mult": 0.5})
run("sl 0.5 iv x0.95", iv_mult=0.95, **{"sell.sl_mult": 0.5})
if not a.quick:
    run("wing 200 sl 0.5", **{"sell.wing_pts": 200, "sell.sl_mult": 0.5})
    run("wing 400 sl 0.5", **{"sell.wing_pts": 400, "sell.sl_mult": 0.5})
    run("entry 10:15 sl 0.5", **{"sell.entry_time": time(10, 15), "sell.sl_mult": 0.5})
    run("entry 09:30 sl 0.5", **{"sell.entry_time": time(9, 30), "sell.sl_mult": 0.5})
    run("exit 15:10 sl 0.5", **{"sell.exit_time": time(15, 10), "sell.sl_mult": 0.5})
    run("exit 13:30 sl 0.5", **{"sell.exit_time": time(13, 30), "sell.sl_mult": 0.5})
    run("dte 0 only sl 0.5", **{"sell.dte_max": 0.99, "sell.sl_mult": 0.5})
    run("dte 1-2 sl 0.5", **{"sell.dte_min": 1.0, "sell.dte_max": 2.99, "sell.sl_mult": 0.5})
    run("dte 3-6 sl 0.5", **{"sell.dte_min": 3.0, "sell.sl_mult": 0.5})
    run("no gap/move filter sl 0.5", **{"sell.gap_max_pct": 99, "sell.open_move_max_pct": 99, "sell.sl_mult": 0.5})
    run("no vix filters sl 0.5", **{"sell.vix_max": 99, "sell.vix_spike_ratio": 99, "sell.sl_mult": 0.5})
    run("no adx filter sl 0.5", **{"sell.adx_max": 99, "sell.sl_mult": 0.5})
    run("adx 25 sl 0.5", **{"sell.adx_max": 25, "sell.sl_mult": 0.5})
    run("cost 10 sl 0.5", **{"sell.cost_pts": 10, "sell.sl_mult": 0.5})
    run("no filters at all sl 0.5", **{"sell.gap_max_pct": 99, "sell.open_move_max_pct": 99, "sell.vix_max": 99,
                                       "sell.vix_spike_ratio": 99, "sell.adx_max": 99, "sell.sl_mult": 0.5})
