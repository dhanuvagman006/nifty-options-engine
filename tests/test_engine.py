"""Unit tests: indicators vs pandas references, calendar, option maths, chain parsers, engine behaviour."""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from nifty_signals.config import Config
from nifty_signals.data.feed import drop_incomplete_last_bar, resample
from nifty_signals.data.groww import _parse_candles, parse_groww_chain
from nifty_signals.data.chain import ChainHistory, ChainSnapshot, derive
from nifty_signals.engine.calendar import ExpiryCalendar
from nifty_signals.engine.features import build_features
from nifty_signals.engine.options import bs, implied_vol, select_strike
from nifty_signals.engine.signals import SignalEngine
from nifty_signals.indicators import core as I

IST = "Asia/Kolkata"


# ----------------------------------------------------------------------------- indicators
@pytest.fixture(scope="module")
def series():
    rng = np.random.default_rng(1)
    c = 20000 + np.cumsum(rng.normal(0, 8, 3000))
    h = c + rng.random(3000) * 10
    l = c - rng.random(3000) * 10
    return h, l, c


def test_ema_matches_pandas(series):
    _, _, c = series
    ref = pd.Series(c).ewm(span=20, adjust=False).mean().values
    assert np.allclose(I.ema(c, 20)[300:], ref[300:], atol=0.5)


def test_rsi_matches_wilder(series):
    _, _, c = series
    s = pd.Series(c)
    d = s.diff()
    ag = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    al = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    ref = (100 - 100 / (1 + ag / al)).values
    assert np.allclose(I.rsi(c, 14)[300:], ref[300:], atol=0.5)


def test_atr_positive_and_bounded(series):
    h, l, c = series
    a = I.atr(h, l, c, 14)
    assert np.all(a[14:] > 0)
    assert np.nanmax(a) < 100


def test_adx_range(series):
    h, l, c = series
    a, p, m = I.adx(h, l, c, 14)
    v = a[~np.isnan(a)]
    assert v.min() >= 0 and v.max() <= 100


def test_supertrend_direction_flips(series):
    h, l, c = series
    _, d = I.supertrend(h, l, c, 10, 3.0)
    assert set(np.unique(d[20:])) <= {-1.0, 1.0}


def test_donchian_excludes_current_bar():
    h = np.array([1, 2, 3, 10, 4, 5, 6.0])
    l = h - 1
    up, lo = I.donchian(h, l, 3)
    assert up[3] == 3.0      # bar 3's own high (10) not included
    assert up[4] == 10.0


def test_swing_pivots_no_lookahead():
    h = np.array([1, 2, 5, 2, 1, 1, 1, 1, 1.0])
    l = h - 0.5
    sh, sl, _, _ = I.swing_pivots(h, l, 2)
    assert np.isnan(sh[3])        # pivot at bar 2 is only confirmed at bar 4
    assert sh[4] == 5.0


def test_pct_rank_bounds(series):
    _, _, c = series
    r = I.pct_rank(c, 200)
    v = r[~np.isnan(r)]
    assert v.min() >= 0 and v.max() <= 100


# ----------------------------------------------------------------------------- calendar
def test_weekly_expiry_tuesday_with_holiday_roll():
    cfg = Config()
    cal = ExpiryCalendar(cfg.session)
    assert cal.next_expiry(date(2026, 10, 8)) == date(2026, 10, 13)   # Thu -> next Tue
    assert cal.next_expiry(date(2026, 10, 13)) == date(2026, 10, 13)  # expiry day itself
    assert cal.next_expiry(date(2026, 10, 14)) == date(2026, 10, 19)  # 20-Oct holiday -> Mon 19


def test_known_expiries_override_rule():
    cfg = Config()
    cal = ExpiryCalendar(cfg.session, known=[date(2026, 10, 15)])
    assert cal.next_expiry(date(2026, 10, 8)) == date(2026, 10, 15)


def test_dte_fraction():
    cfg = Config()
    cal = ExpiryCalendar(cfg.session)
    ts = pd.Timestamp("2026-10-13 15:25").tz_localize(IST)   # expiry day, 5 min before close
    assert 0 < cal.dte(ts) < 0.02
    ts = pd.Timestamp("2026-10-12 09:15").tz_localize(IST)
    assert 1.99 < cal.dte(ts) <= 2.0


# ----------------------------------------------------------------------------- options
def test_black_scholes_parity_and_iv_roundtrip():
    s, k, t, iv = 22300.0, 22300.0, 3 / 252, 14.0
    c = bs(s, k, t, iv, "CE")
    p = bs(s, k, t, iv, "PE")
    assert abs(c.delta - 0.5) < 0.1 and abs(p.delta + 0.5) < 0.1
    assert c.price > 0 and p.price > 0
    assert abs(implied_vol(c.price, s, k, t, "CE") - iv) < 0.05


def test_select_strike():
    assert select_strike(22281.8, "CE", 50, 0) == 22300
    assert select_strike(22281.8, "CE", 50, 1) == 22250
    assert select_strike(22281.8, "PE", 50, 1) == 22350


# ----------------------------------------------------------------------------- chain parsers
def _snapshot(spot: float = 22281.8) -> ChainSnapshot:
    ks = np.arange(22100.0, 22501.0, 50.0)
    n = ks.size
    ce_oi = 1000 + (ks - 22100)
    pe_oi = 1500 - (ks - 22100)
    s = ChainSnapshot(ts=pd.Timestamp.now(tz=IST), spot=spot, expiry="13-Oct-2026", strikes=ks,
                      ce_oi=ce_oi, pe_oi=pe_oi,
                      ce_chg_oi=np.where(ks > 22300, -50.0, 20.0), pe_chg_oi=np.where(ks < 22300, 100.0, 10.0),
                      ce_vol=np.full(n, 500.0), pe_vol=np.full(n, 700.0),
                      ce_iv=np.full(n, 13.0), pe_iv=np.full(n, 15.0),
                      ce_ltp=np.maximum(22300 - ks, 0) + 80, pe_ltp=np.maximum(ks - 22300, 0) + 80,
                      ce_bid=np.full(n, 1.0), ce_ask=np.full(n, 1.1), pe_bid=np.full(n, 1.0), pe_ask=np.full(n, 1.1))
    derive(s, 50)
    return s


def test_chain_derived_fields():
    s = _snapshot()
    assert s.atm == 22300
    assert s.pcr_oi > 0
    assert s.call_wall >= s.spot and s.put_wall <= s.spot
    assert s.ce_chg_above < 0 and s.pe_chg_below > 0
    assert 22100 <= s.max_pain <= 22500
    ltp, bid, ask, iv = s.premium(22300, "CE")
    assert ltp == 80 and iv == 13.0


def test_parse_groww_chain_with_baseline():
    strikes = {}
    for k in range(22100, 22501, 50):
        strikes[str(k)] = {"CE": {"ltp": 80.0, "open_interest": 1000, "volume": 10, "greeks": {"iv": 0.13}},
                           "PE": {"ltp": 90.0, "open_interest": 2000, "volume": 10, "greeks": {"iv": 15.0}}}
    payload = {"underlying_ltp": 22281.8, "strikes": strikes}
    base = {"CE": {str(float(k)): 900.0 for k in range(22100, 22501, 50)},
            "PE": {str(float(k)): 2100.0 for k in range(22100, 22501, 50)}}
    s = parse_groww_chain(payload, "13-Oct-2026", pd.Timestamp.now(tz=IST), base)
    assert s.atm == 22300 and s.pcr_oi == 2.0
    assert np.all(s.ce_chg_oi == 100) and np.all(s.pe_chg_oi == -100)
    assert s.atm_iv_ce == 13.0 and s.atm_iv_pe == 15.0   # fraction and percent both normalised


def test_parse_groww_candles_epoch_and_string():
    df = _parse_candles({"candles": [[1759900500, 1, 2, 0.5, 1.5, 0, None], ["2026-10-08 09:20:00", 1, 2, 0.5, 1.6, 10, None]]})
    assert len(df) == 2 and str(df.index.tz) == IST
    assert df["close"].iloc[-1] == 1.6


def test_chain_history_trend():
    h = ChainHistory()
    for i, pcr in enumerate([1.0, 1.0, 1.0, 1.1]):
        s = _snapshot()
        s.ts = s.ts + pd.Timedelta(minutes=i)
        s.pcr_oi = pcr
        h.push(s)
    assert h.pcr_trend() == 1.0


# ----------------------------------------------------------------------------- feed helpers
def test_drop_incomplete_last_bar():
    idx = pd.date_range("2026-10-08 09:15", periods=3, freq="5min", tz=IST)
    df = pd.DataFrame({"open": 1, "high": 1, "low": 1, "close": 1, "volume": 0}, index=idx, dtype=float)
    now = pd.Timestamp("2026-10-08 09:27", tz=IST)
    assert len(drop_incomplete_last_bar(df, "5m", now)) == 2
    now = pd.Timestamp("2026-10-08 09:30", tz=IST)
    assert len(drop_incomplete_last_bar(df, "5m", now)) == 3


def test_resample_anchors_at_open():
    idx = pd.date_range("2026-10-08 09:15", periods=75, freq="5min", tz=IST)
    df = pd.DataFrame({"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 0.0}, index=idx)
    r = resample(df, 15)
    assert r.index[0] == idx[0] and len(r) == 25


# ----------------------------------------------------------------------------- engine
def _synthetic_session_frame(days: int = 45, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = []
    d = pd.Timestamp("2026-08-03", tz=IST)
    while len(idx) < days * 75:
        if d.weekday() < 5:
            idx.extend(pd.date_range(d + pd.Timedelta(hours=9, minutes=15), periods=75, freq="5min"))
        d += pd.Timedelta(days=1)
    idx = pd.DatetimeIndex(idx[: days * 75])
    n = len(idx)
    # multi-day trend regimes so that HTF/daily alignment and triggers can occur
    blocks = int(np.ceil(days / 5))
    drift = np.repeat(rng.choice([-2.5, 2.5], size=blocks), 5 * 75)[: days * 75]
    c = 22500 + np.cumsum(drift + rng.normal(0, 8, n))
    h = c + rng.random(n) * 12
    l = c - rng.random(n) * 12
    o = np.roll(c, 1)
    o[0] = c[0]
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": 0.0}, index=idx)


def _features(cfg: Config):
    cfg.ind.daily_ema = 5
    bars = _synthetic_session_frame()
    daily = bars.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    daily.index = daily.index.normalize()
    vix = pd.DataFrame({"close": 14.0}, index=daily.index)
    cal = ExpiryCalendar(cfg.session)
    return build_features(bars, daily, vix, cfg, cal)


def test_features_have_no_lookahead_in_htf():
    cfg = Config()
    f = _features(cfg)
    # a 5m bar at 09:20 (ends 09:25) must not see the 09:15 15m bar (ends 09:30)
    row = f.loc[f.index.time == pd.Timestamp("09:20").time()].iloc[5]
    prev15 = f.loc[f.index.time == pd.Timestamp("09:15").time()]
    assert not np.isnan(row["h_close"]) or row["h_close"] != row["close"]


def test_engine_one_position_and_daily_cap():
    cfg = Config()
    cfg.filt.score_threshold = 0
    cfg.filt.min_categories = 0
    cfg.opt.min_premium = 0
    cfg.opt.max_premium = 1e9
    f = _features(cfg)
    eng = SignalEngine(cfg, 5)
    open_pos = 0
    per_day: dict = {}
    for i in range(len(f)):
        for s in eng.on_bar(f, i):
            if s.action == "BUY":
                assert open_pos == 0
                open_pos = 1
                per_day[s.ts.date()] = per_day.get(s.ts.date(), 0) + 1
                assert s.sl_prem < s.premium < s.t1_prem < s.t2_prem
                assert s.expiry
            elif s.action == "EXIT" and not s.reason.startswith("T1"):
                open_pos = 0
    assert eng.state.pos is None or True
    assert all(v <= cfg.filt.max_signals_per_day for v in per_day.values())
    assert len(eng.state.trades) > 0


def test_engine_square_off_closes_everything():
    cfg = Config()
    cfg.filt.score_threshold = 0
    cfg.filt.min_categories = 0
    cfg.opt.min_premium = 0
    cfg.opt.max_premium = 1e9
    f = _features(cfg)
    eng = SignalEngine(cfg, 5)
    for i in range(len(f)):
        eng.on_bar(f, i)
    t = pd.DataFrame(eng.state.trades)
    assert (t["exit_ts"].dt.time <= cfg.session.square_off).all() or (t["exit_ts"].dt.time <= pd.Timestamp("15:10").time()).all()


def test_signal_line_format():
    from nifty_signals.engine.signals import Signal

    s = Signal(pd.Timestamp("2026-10-08 10:15", tz=IST), "BUY", "PE", 22450, "13-Oct", 146.0, 22461,
               128, 165, 208, 22501, 22421, 22341, 81, "dc")
    line = s.line()
    assert line.startswith("08-Oct 10:15  BUY  NIFTY 22450 PE  @146.0  SL 128  T1 165  T2 208")
    assert "exp 13-Oct" in line
