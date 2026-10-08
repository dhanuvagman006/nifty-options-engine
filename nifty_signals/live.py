"""Live loop on the Groww trade API: wake at each bar close, refresh bars + option chain, run the engine."""
from __future__ import annotations

import logging
import time
from datetime import datetime

import pandas as pd

from .alerts.sink import Dispatcher
from .config import Config
from .data.chain import ChainHistory
from .data.feed import IST, BarSource, CSVSource, interval_minutes
from .data.groww import GrowwBarSource, GrowwClient, GrowwOptionChain
from .engine.calendar import ExpiryCalendar
from .engine.features import build_features
from .engine.signals import BarEngine, make_engine
from .execution.broker import Executor

log = logging.getLogger(__name__)


class DataHub:
    """Owns the Groww client and sources, produces the feature frame on demand."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.groww = GrowwClient(cfg.groww)
        self.cal = ExpiryCalendar(cfg.session)
        self.bar_minutes = interval_minutes(cfg.data.bar_interval)
        if cfg.data.csv_path:                      # offline replay from a CSV export
            self.spot: BarSource = CSVSource(cfg.data.csv_path)
        else:
            self.spot = GrowwBarSource(self.groww, cfg.groww.groww_symbol, cfg.groww.segment, cfg.data.cache_dir)
        self.vix: BarSource | None = None
        if cfg.data.vix_path:                      # offline VIX history (backtests)
            self.vix = CSVSource(cfg.data.vix_path)
        elif cfg.groww.vix_symbol:
            self.vix = GrowwBarSource(self.groww, cfg.groww.vix_symbol, cfg.groww.segment, cfg.data.cache_dir)
        self._vix_failed = False

    def chain(self) -> GrowwOptionChain | None:
        if not self.cfg.data.use_chain:
            return None
        return GrowwOptionChain(self.groww, self.cfg.groww.underlying, self.cfg.data.chain_min_refresh_sec,
                                self.cfg.opt.strike_step, self.cfg.data.cache_dir)

    def load(self, days: int | None = None) -> pd.DataFrame:
        days = days or self.cfg.data.history_days
        bars = self.spot.bars(self.cfg.data.bar_interval, days)
        daily = self.spot.bars("1d", days + 400)
        vix = None
        if self.vix is not None and not self._vix_failed:
            try:
                vix = self.vix.bars("1d", days + 400)
            except Exception as exc:  # noqa: BLE001
                self._vix_failed = True
                log.warning("VIX unavailable from Groww (%s); VIX filter disabled", exc)
        return build_features(bars, daily, vix, self.cfg, self.cal)


def _next_bar_close(now: pd.Timestamp, minutes: int, open_: datetime.time) -> pd.Timestamp:
    """Next instant at which a bar ends, aligned to the 09:15 open."""
    base = now.normalize() + pd.Timedelta(hours=open_.hour, minutes=open_.minute)
    if now < base:
        return base + pd.Timedelta(minutes=minutes)
    elapsed = (now - base).total_seconds() / 60.0
    k = int(elapsed // minutes) + 1
    return base + pd.Timedelta(minutes=k * minutes)


def run_live(cfg: Config, once: bool = False, no_chain: bool = False) -> None:
    hub = DataHub(cfg)
    disp = Dispatcher(cfg.alert)
    eng = make_engine(cfg, hub.bar_minutes, cal=hub.cal)
    chain = None if no_chain else hub.chain()
    chist = ChainHistory()
    execu = Executor(cfg, hub.groww) if cfg.exec.enabled else None
    if execu is not None and cfg.exec.mode == "live":
        log.warning("LIVE ORDER EXECUTION ENABLED on Groww (max %d lot, daily loss cap %.0f)", cfg.exec.max_lots, cfg.exec.max_daily_loss)
    expiry_label = None
    if chain is not None:
        try:
            exps = chain.expiries()
            hub.cal.set_known_expiries([datetime.strptime(e, "%d-%b-%Y").date() for e in exps])
            expiry_label = chain.nearest_expiry()
            log.info("expiries loaded from Groww; nearest %s", expiry_label)
        except Exception as exc:  # noqa: BLE001
            log.warning("expiry list unavailable from Groww, using rule-based expiry: %s", exc)
    feats = hub.load()
    eng.state.last_i = len(feats) - 1          # only act on bars that close from now on
    log.info("engine ready: %d bars, last %s", len(feats), feats.index[-1])
    s = cfg.session

    while True:
        now = pd.Timestamp.now(tz=IST)
        t = now.time()
        if now.weekday() >= 5 or t < s.market_open or t > s.market_close or not hub.cal.is_trading_day(now.date()):
            if once:
                log.info("market closed")
                _scan_once(hub, eng, disp, chain, chist, expiry_label, feats)
                return
            nxt = _next_bar_close(now, hub.bar_minutes, s.market_open)
            time.sleep(min(300, max(5, (nxt - now).total_seconds())))
            continue
        nxt = _next_bar_close(now, hub.bar_minutes, s.market_open)
        wait = (nxt - now).total_seconds() + 5   # a few seconds for the feed to publish the bar
        if not once and wait > 0:
            time.sleep(wait)
        target_start = nxt - pd.Timedelta(minutes=hub.bar_minutes)
        # poll until the just-closed bar is present; give up shortly before the next bar closes
        # (a late bar is then picked up in the next cycle, since every unseen bar is processed)
        deadline = nxt + pd.Timedelta(minutes=hub.bar_minutes) - pd.Timedelta(seconds=20)
        waited = 0
        while True:
            try:
                feats = hub.load()
            except Exception as exc:  # noqa: BLE001
                log.warning("bar refresh failed: %s", exc)
            else:
                if once or feats.index[-1] >= target_start:
                    break
            now2 = pd.Timestamp.now(tz=IST)
            if once or now2 >= deadline:
                log.info("bar %s not published by feed yet; will catch up next cycle", target_start.strftime("%H:%M"))
                break
            if waited % 30 == 0:
                log.info("waiting for %s bar from feed (last %s)", target_start.strftime("%H:%M"), feats.index[-1].strftime("%H:%M"))
            time.sleep(10)
            waited += 10
        snap = None
        if chain is not None:
            try:
                snap = chain.snapshot(expiry_label)
                chist.push(snap)
            except Exception as exc:  # noqa: BLE001
                log.warning("option chain unavailable this bar: %s", exc)
        # process any bars not yet seen (normally exactly one)
        start = eng.state.last_i + 1
        if once:
            start = len(feats) - 1
            eng.state.last_i = start - 1
        for i in range(start, len(feats)):
            for sig in eng.on_bar(feats, i, snap, chist, expiry_label):
                disp.dispatch(sig)
                if execu is not None:
                    execu.on_signal(sig, snap)
            log.info(_heartbeat(cfg, eng, feats, i, snap, hub.bar_minutes))
        if execu is not None:
            now3 = pd.Timestamp.now(tz=IST).time()
            if execu.kill_switch_on() and execu.pos is not None:
                execu.flatten("KILL", snap)
            elif cfg.exec.flatten_at_square_off and now3 >= s.square_off and execu.pos is not None:
                execu.flatten("SQOFF", snap)
        if once:
            return


def _heartbeat(cfg: Config, eng: BarEngine, feats: pd.DataFrame, i: int, snap, bar_minutes: int) -> str:
    """One status line per bar so a watcher can see what the engine is thinking."""
    w = eng._row(feats, i)
    hist = eng._records(feats)[max(0, i - 6):i]
    parts = [f"bar {w['ts'].strftime('%H:%M')} close {w['close']:.0f} atr {w['atr']:.0f} rsi {w['rsi']:.0f} adx {w['adx']:.0f} "
             f"vix {w['vix']:.1f} dte {w['dte']:.1f}"]
    if snap is not None:
        parts.append(f"pcr {snap.pcr_oi:.2f} iv {snap.atm_iv_ce:.1f}/{snap.atm_iv_pe:.1f}")
    parts.append(eng.status(w, hist, snap))
    return " | ".join(parts)


def _scan_once(hub, eng, disp, chain, chist, expiry_label, feats) -> None:
    snap = None
    if chain is not None:
        try:
            snap = chain.snapshot(expiry_label)
            chist.push(snap)
        except Exception as exc:  # noqa: BLE001
            log.warning("option chain unavailable: %s", exc)
    i = len(feats) - 1
    eng.state.last_i = i - 1
    for sig in eng.on_bar(feats, i, snap, chist, expiry_label):
        disp.dispatch(sig)
    log.info(_heartbeat(hub.cfg, eng, feats, i, snap, hub.bar_minutes))
