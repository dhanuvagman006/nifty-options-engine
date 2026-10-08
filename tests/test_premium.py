"""Premium-selling engine: one fly per session, exits, P&L accounting and entry filters."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nifty_signals.backtest.runner import run_backtest
from nifty_signals.config import Config
from nifty_signals.engine.premium import PremiumEngine
from nifty_signals.engine.signals import make_engine
from tests.test_engine import _features

IST = "Asia/Kolkata"


@pytest.fixture
def cfg():
    c = Config()
    c.filt.strategy = "iron_fly"
    c.sell.gap_max_pct = 99
    c.sell.open_move_max_pct = 99
    c.sell.adx_max = 99
    c.sell.vix_spike_ratio = 99
    c.sell.dte_max = 6          # structural tests: allow every session, not just the two before expiry
    return c


def test_factory_picks_premium_engine(cfg):
    assert isinstance(make_engine(cfg), PremiumEngine)
    cfg.filt.strategy = "pa_short"
    assert not isinstance(make_engine(cfg), PremiumEngine)


def test_one_fly_per_session_and_closed_by_exit_time(cfg):
    f = _features(cfg)
    eng = PremiumEngine(cfg, 5)
    opens: dict = {}
    for i in range(len(f)):
        for s in eng.on_bar(f, i):
            if s.action == "SELL":
                assert s.kind == "FLY" and len(s.legs) == 4 and s.structure == "IRON FLY"
                assert s.premium > 0 and s.t1_prem < s.premium < s.t2_prem
                sides = sorted(l["side"] for l in s.legs)
                assert sides == ["BUY", "BUY", "SELL", "SELL"]
                assert (s.ts + pd.Timedelta(minutes=5)).time() >= cfg.sell.entry_time
                opens[s.ts.date()] = opens.get(s.ts.date(), 0) + 1
    assert opens and max(opens.values()) == 1
    t = pd.DataFrame(eng.state.trades)
    assert len(t) == len(opens)
    assert (t["exit_ts"].dt.time <= pd.Timestamp("14:40").time()).all()
    # P&L = credit - close-out value - cost, in points
    assert np.allclose(t["pnl_pts"], t["entry_prem"] - t["exit_prem"] - cfg.sell.cost_pts)
    assert np.allclose(t["pnl_pct"], t["pnl_pts"] / t["entry_prem"] * 100)


def test_stop_triggers_on_large_move(cfg):
    cfg.sell.sl_mult = 0.2
    f = _features(cfg)
    # inject a violent 2% up-move right after the usual entry time on one session
    day = f.index.normalize().unique()[30]
    sel = (f.index.normalize() == day) & (f.index.time >= pd.Timestamp("10:00").time())
    bump = f.loc[sel, "close"].iloc[0] * 0.02
    for col in ("open", "high", "low", "close"):
        f.loc[sel, col] += bump
    eng = PremiumEngine(cfg, 5)
    for i in range(len(f)):
        eng.on_bar(f, i)
    t = pd.DataFrame(eng.state.trades)
    hit = t[t["entry_ts"].dt.normalize() == day]
    assert hit["reason"].iloc[0] == "SL" and hit["pnl_pts"].iloc[0] < 0
    assert len(hit) >= 2                      # re-entry after the stop, re-centred at the new ATM
    assert hit["strike"].iloc[1] != hit["strike"].iloc[0]
    cfg.sell.reentry_after_sl = False
    eng2 = PremiumEngine(cfg, 5)
    for i in range(len(f)):
        eng2.on_bar(f, i)
    t2 = pd.DataFrame(eng2.state.trades)
    assert len(t2[t2["entry_ts"].dt.normalize() == day]) == 1


def test_gap_and_dte_filters_block_entry(cfg):
    f = _features(cfg)
    eng = PremiumEngine(cfg, 5)
    i = int(np.where(f.index.time == pd.Timestamp("09:40").time())[0][20])
    w = eng._row(f, i)
    r = eng.evaluate_entry(w, [], None)
    assert r.passed
    cfg.sell.gap_max_pct = -1.0
    assert "gap" in eng.evaluate_entry(w, [], None).vetoes
    cfg.sell.gap_max_pct = 99
    cfg.sell.dte_max = -1
    assert "dte" in eng.evaluate_entry(w, [], None).vetoes
    cfg.sell.dte_max = 6.0
    cfg.sell.event_dates = [w["ts"].strftime("%Y-%m-%d")]
    eng2 = PremiumEngine(cfg, 5)
    assert "event_day" in eng2.evaluate_entry(w, [], None).vetoes


def test_backtest_runner_reports_margin_metrics(cfg):
    f = _features(cfg)
    res = run_backtest(f, cfg, 5)
    assert res.metrics["trades"] > 0
    assert "ret_on_margin" in res.metrics and res.metrics["margin"] == cfg.sell.margin_per_lot
    assert "Return on margin" in res.report()
    assert any(s.action == "SELL" and "IRON FLY" in s.line() for s in res.signals)


def test_structure_signal_line_format():
    from nifty_signals.engine.signals import Signal

    legs = [{"kind": "CE", "strike": 22450, "side": "SELL", "premium": 120.0},
            {"kind": "PE", "strike": 22450, "side": "SELL", "premium": 110.0},
            {"kind": "CE", "strike": 22750, "side": "BUY", "premium": 30.0},
            {"kind": "PE", "strike": 22150, "side": "BUY", "premium": 28.0}]
    s = Signal(pd.Timestamp("2026-10-08 09:40", tz=IST), "SELL", "FLY", 22450, "13-Oct", 172.0, 22461,
               t1_prem=86, t2_prem=258, legs=legs, structure="IRON FLY")
    line = s.line()
    assert line.startswith("08-Oct 09:40  SELL IRON FLY NIFTY 22450  wings 22150/22750  credit 172.0  TP 86  SL 258")
    assert "S22450CE@120.0" in line and "B22150PE@28.0" in line
    x = Signal(pd.Timestamp("2026-10-08 14:40", tz=IST), "EXIT", "FLY", 22450, "13-Oct", 140.0, 22470,
               reason="TIME", legs=legs, structure="IRON FLY")
    x.pnl_pct = 15.1
    assert x.line() == "08-Oct 14:40  EXIT IRON FLY NIFTY 22450  @140.0  TIME  +15% of credit  | spot 22470"
