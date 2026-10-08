"""Replay the price-action buyer (pa_short) through the full engine under the exit variants the
research suggested (no supertrend-flip exit, no breakeven move after T1, morning-only window).

    python -u research/pa_sweep.py [--from 2018-01-01]
"""
from __future__ import annotations

import argparse
import copy
import sys

import pandas as pd

sys.path.insert(0, ".")
from nifty_signals.backtest import runner  # noqa: E402
from nifty_signals.config import Config  # noqa: E402
from nifty_signals.engine.calendar import ExpiryCalendar  # noqa: E402
from nifty_signals.engine.signals import make_engine  # noqa: E402
from nifty_signals.indicators.core import warmup  # noqa: E402
from nifty_signals.live import DataHub  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--from", dest="start", default="2018-01-01")
a = ap.parse_args()

warmup()
base = Config.load("config.toml")
base.filt.strategy = "pa_short"
base.data.csv_path = "cache/hist_5m.parquet"
base.data.vix_path = "cache/india_vix_1d.parquet"
base.data.use_chain = False
hub = DataHub(base)
feats = hub.load(4000)
start = int((feats.index < pd.Timestamp(a.start, tz="Asia/Kolkata")).sum())
print(f"{len(feats)} bars, replay from {feats.index[start]}")


def run(label: str, **over):
    cfg = copy.deepcopy(base)
    for k, v in over.items():
        sec, key = k.split(".")
        setattr(getattr(cfg, sec), key, v)
    eng = make_engine(cfg, 5, cal=ExpiryCalendar(cfg.session))
    eng.state.last_i = start - 1
    for i in range(start, len(feats)):
        eng.on_bar(feats, i)
    tr = pd.DataFrame(eng.state.trades)
    sessions = int(feats["session"].iloc[start:].nunique())
    m = runner.metrics_for(tr, cfg, cfg.opt.slippage_pct / 100.0, sessions)
    if not m:
        print(f"{label:<40} no trades")
        return
    by = m["by_year"]
    print(f"{label:<40} n {m['trades']:>4}  win {m['win_rate']:>4.0f}%  PF {m['profit_factor']:>4.2f}  "
          f"exp {m['expectancy']:>+5.1f}%  net {m['total_pts']:>+6.0f} pts  dd {m['max_dd_pts']:>4.0f}  "
          f"2026 {by.get(2026, '-'):<18} exits {m['reasons']}")


run("current (flip + breakeven, all day)")
run("no flip exit", **{"filt.exit_on_flip": False})
run("no flip, no breakeven", **{"filt.exit_on_flip": False, "filt.breakeven_after_t1": False})
run("no flip, no BE, no trail", **{"filt.exit_on_flip": False, "filt.breakeven_after_t1": False, "filt.trail_after_t1": False})
run("09:30-10:00 window (post-hoc)", **{"filt.pa_entry_end": "10:00"})
run("09:30-10:00, no flip/BE", **{"filt.pa_entry_end": "10:00", "filt.exit_on_flip": False, "filt.breakeven_after_t1": False})
run("09:30-11:00, no flip/BE", **{"filt.pa_entry_end": "11:00", "filt.exit_on_flip": False, "filt.breakeven_after_t1": False})
run("no flip/BE, t1 3.0 (single target)", **{"filt.exit_on_flip": False, "filt.breakeven_after_t1": False, "filt.t1_r": 3.0})
