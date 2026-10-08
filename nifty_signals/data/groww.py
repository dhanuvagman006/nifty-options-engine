"""Groww trade API adapter: historical/live NIFTY candles and the option chain.

Requires `pip install growwapi pyotp`. Credentials come from config.toml [groww] or environment
variables GROWW_ACCESS_TOKEN | GROWW_API_KEY + GROWW_API_SECRET | GROWW_TOTP_TOKEN + GROWW_TOTP_SECRET.

Groww's option chain carries LTP / OI / volume / greeks(iv) but not change-in-OI or bid/ask, so the
adapter derives intraday change-in-OI against the first snapshot of the session (kept on disk so a
restart mid-session does not lose the baseline).
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from ..config import GrowwConfig
from .feed import IST, COLS, _normalise, drop_incomplete_last_bar, interval_minutes
from .chain import ChainSnapshot, derive

log = logging.getLogger(__name__)

# max days per request by interval minutes (Groww get_historical_candles limits)
_CHUNK_DAYS = {1: 30, 2: 30, 3: 30, 5: 30, 10: 90, 15: 90, 30: 90, 60: 180, 240: 180, 1440: 180}
_INTERVAL_CONST = {1: "1minute", 2: "2minute", 3: "3minute", 5: "5minute", 10: "10minute", 15: "15minute",
                   30: "30minute", 60: "1hour", 240: "4hour", 1440: "1day"}


class GrowwClient:
    """Lazy, thread-safe wrapper around growwapi.GrowwAPI with token acquisition."""

    def __init__(self, cfg: GrowwConfig):
        self.cfg = cfg
        self._api = None
        self._lock = threading.Lock()

    def _token(self) -> str:
        c = self.cfg
        tok = c.access_token or os.getenv("GROWW_ACCESS_TOKEN", "")
        if tok:
            return tok
        from growwapi import GrowwAPI

        key = c.api_key or os.getenv("GROWW_API_KEY", "")
        secret = c.api_secret or os.getenv("GROWW_API_SECRET", "")
        totp_token = c.totp_token or os.getenv("GROWW_TOTP_TOKEN", "")
        totp_secret = c.totp_secret or os.getenv("GROWW_TOTP_SECRET", "")
        if totp_token and totp_secret:
            import pyotp

            res = GrowwAPI.get_access_token(api_key=totp_token, totp=pyotp.TOTP(totp_secret).now())
        elif key and secret:
            res = GrowwAPI.get_access_token(api_key=key, secret=secret)
        else:
            raise RuntimeError("Groww credentials missing: set [groww] in config.toml or GROWW_* env vars")
        if isinstance(res, dict):
            for k in ("token", "access_token", "accessToken"):
                if res.get(k):
                    return str(res[k])
            raise RuntimeError(f"unexpected token response: {list(res.keys())}")
        return str(res)

    @property
    def api(self):
        with self._lock:
            if self._api is None:
                from growwapi import GrowwAPI

                self._api = GrowwAPI(self._token())
            return self._api

    def reset(self) -> None:
        with self._lock:
            self._api = None

    def call(self, method: str, **kw):
        """Call an SDK method with one re-auth retry on failure."""
        last: Exception | None = None
        for attempt in range(2):
            try:
                return getattr(self.api, method)(**kw)
            except Exception as exc:  # noqa: BLE001
                last = exc
                if "credentials missing" in str(exc):
                    raise RuntimeError(str(exc)) from None
                log.warning("groww %s failed (%s); re-authenticating", method, exc)
                self.reset()
                time.sleep(1.0)
        raise RuntimeError(f"groww {method} failed: {last}")


def _parse_candles(payload: dict) -> pd.DataFrame:
    rows = payload.get("candles") or []
    if not rows:
        return pd.DataFrame(columns=COLS, index=pd.DatetimeIndex([], tz=IST))
    ts = []
    for r in rows:
        t = r[0]
        if isinstance(t, (int, float)):
            ts.append(pd.Timestamp(int(t), unit="s", tz="UTC").tz_convert(IST))
        else:
            ts.append(pd.Timestamp(str(t)).tz_localize(IST))
    df = pd.DataFrame({
        "open": [float(r[1]) for r in rows], "high": [float(r[2]) for r in rows],
        "low": [float(r[3]) for r in rows], "close": [float(r[4]) for r in rows],
        "volume": [float(r[5]) if len(r) > 5 and r[5] is not None else 0.0 for r in rows],
    }, index=pd.DatetimeIndex(ts))
    return _normalise(df)


class GrowwBarSource:
    """BarSource implementation on Groww historical candles with a parquet cache."""

    def __init__(self, client: GrowwClient, groww_symbol: str = "NSE-NIFTY", segment: str = "CASH",
                 cache_dir: str | Path = "cache"):
        self.client = client
        self.symbol = groww_symbol
        self.segment = segment
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, interval: str) -> Path:
        return self.cache_dir / f"groww_{self.symbol.replace('-', '_')}_{interval}.parquet"

    def _fetch(self, mins: int, start: datetime, end: datetime) -> pd.DataFrame:
        chunk = _CHUNK_DAYS.get(mins, 30)
        frames = []
        cur = start
        while cur < end:
            nxt = min(cur + timedelta(days=chunk), end)
            payload = self.client.call(
                "get_historical_candles", exchange="NSE", segment=self.segment, groww_symbol=self.symbol,
                start_time=cur.strftime("%Y-%m-%d %H:%M:%S"), end_time=nxt.strftime("%Y-%m-%d %H:%M:%S"),
                candle_interval=_INTERVAL_CONST[mins])
            frames.append(_parse_candles(payload))
            cur = nxt
            time.sleep(0.25)  # stay well inside rate limits
        return _normalise(pd.concat(frames)) if frames else _parse_candles({})

    def bars(self, interval: str, days: int) -> pd.DataFrame:
        mins = interval_minutes(interval)
        path = self._cache_path(interval)
        cached = pd.DataFrame()
        if path.exists():
            try:
                cached = _normalise(pd.read_parquet(path))
            except Exception as exc:  # noqa: BLE001
                log.warning("cache read failed: %s", exc)
        now = pd.Timestamp.now(tz=IST)
        end = now.tz_localize(None).to_pydatetime() + timedelta(minutes=1)
        if cached.empty:
            start = (now - timedelta(days=days)).tz_localize(None).to_pydatetime().replace(hour=9, minute=0, second=0)
        else:
            start = (cached.index[-1] - timedelta(days=2)).tz_localize(None).to_pydatetime()
        fresh = self._fetch(mins, start, end)
        df = _normalise(pd.concat([cached, fresh])) if not cached.empty else fresh
        df = drop_incomplete_last_bar(df, interval, now)
        try:
            df.to_parquet(path)
        except Exception as exc:  # noqa: BLE001
            log.warning("cache write failed: %s", exc)
        return df[df.index >= now - timedelta(days=days)]

    def ltp(self) -> float:
        res = self.client.call("get_ltp", exchange_trading_symbols=(self.symbol.replace("-", "_"),), segment=self.segment)
        if isinstance(res, dict):
            for v in res.values():
                if isinstance(v, (int, float)):
                    return float(v)
        return float("nan")


def parse_groww_chain(payload: dict, expiry: str, ts: pd.Timestamp, baseline_oi: dict | None,
                      strike_step: int = 50) -> ChainSnapshot:
    """Convert Groww's option chain payload to a ChainSnapshot.

    baseline_oi: {"CE": {strike: oi}, "PE": {strike: oi}} captured at session start, for change-in-OI.
    """
    spot = float(payload.get("underlying_ltp") or 0.0)
    strikes_raw = payload.get("strikes") or {}
    ks = sorted(float(k) for k in strikes_raw.keys())
    n = len(ks)
    z = lambda: np.zeros(n)  # noqa: E731
    ce_oi, pe_oi, ce_vol, pe_vol, ce_iv, pe_iv, ce_ltp, pe_ltp = (z() for _ in range(8))
    ce_sym: list[str] = [""] * n
    pe_sym: list[str] = [""] * n
    for i, k in enumerate(ks):
        row = strikes_raw.get(str(int(k))) or strikes_raw.get(str(k)) or strikes_raw.get(f"{k:.1f}") or {}
        for side, oi, vol, iv, ltp in (("CE", ce_oi, ce_vol, ce_iv, ce_ltp), ("PE", pe_oi, pe_vol, pe_iv, pe_ltp)):
            d = row.get(side) or {}
            (ce_sym if side == "CE" else pe_sym)[i] = str(d.get("trading_symbol") or "")
            oi[i] = float(d.get("open_interest") or 0)
            vol[i] = float(d.get("volume") or 0)
            ltp[i] = float(d.get("ltp") or 0)
            g = d.get("greeks") or {}
            ivv = g.get("iv")
            iv[i] = float(ivv) * (100.0 if ivv is not None and float(ivv) < 3 else 1.0) if ivv is not None else 0.0
    strikes = np.array(ks)
    ce_chg = z()
    pe_chg = z()
    if baseline_oi:
        for i, k in enumerate(ks):
            b_ce = baseline_oi.get("CE", {}).get(str(k))
            b_pe = baseline_oi.get("PE", {}).get(str(k))
            ce_chg[i] = ce_oi[i] - b_ce if b_ce is not None else 0.0
            pe_chg[i] = pe_oi[i] - b_pe if b_pe is not None else 0.0
    snap = ChainSnapshot(
        ts=ts, spot=spot, expiry=expiry, strikes=strikes,
        ce_oi=ce_oi, pe_oi=pe_oi, ce_chg_oi=ce_chg, pe_chg_oi=pe_chg, ce_vol=ce_vol, pe_vol=pe_vol,
        ce_iv=ce_iv, pe_iv=pe_iv, ce_ltp=ce_ltp, pe_ltp=pe_ltp,
        ce_bid=ce_ltp.copy(), ce_ask=ce_ltp.copy(), pe_bid=pe_ltp.copy(), pe_ask=pe_ltp.copy(),
        extras={"ce_sym": ce_sym, "pe_sym": pe_sym},
    )
    derive(snap, strike_step)
    return snap


class GrowwOptionChain:
    """Option chain via Groww, exposing expiries() / nearest_expiry() / snapshot()."""

    def __init__(self, client: GrowwClient, underlying: str = "NIFTY", min_refresh_sec: int = 20,
                 strike_step: int = 50, cache_dir: str | Path = "cache"):
        self.client = client
        self.underlying = underlying
        self.min_refresh = min_refresh_sec
        self.strike_step = strike_step
        self.cache_dir = Path(cache_dir)
        self._expiries: list[str] = []
        self._last: ChainSnapshot | None = None
        self._last_fetch = 0.0
        self._lock = threading.Lock()

    def expiries(self, force: bool = False) -> list[str]:
        """Expiry dates formatted like NSE ('13-Oct-2026'), chronological."""
        if self._expiries and not force:
            return self._expiries
        today = date.today()
        out: list[date] = []
        for y, m in ((today.year, today.month), ((today + timedelta(days=32)).year, (today + timedelta(days=32)).month)):
            res = self.client.call("get_expiries", exchange="NSE", underlying_symbol=self.underlying, year=y, month=m)
            for e in (res.get("expiries") or []):
                try:
                    out.append(date.fromisoformat(str(e)[:10]))
                except ValueError:
                    continue
        self._expiries = [d.strftime("%d-%b-%Y") for d in sorted(set(out))]
        return self._expiries

    def nearest_expiry(self, now: pd.Timestamp | None = None) -> str:
        now = now or pd.Timestamp.now(tz=IST)
        for e in self.expiries():
            if datetime.strptime(e, "%d-%b-%Y").date() >= now.date():
                return e
        return self.expiries()[-1]

    # -- session baseline for change-in-OI --------------------------------------
    def _baseline_path(self, expiry: str) -> Path:
        return self.cache_dir / f"groww_oi_baseline_{expiry}_{date.today().isoformat()}.json"

    def _baseline(self, expiry: str, payload: dict) -> dict:
        p = self._baseline_path(expiry)
        if p.exists():
            try:
                return json.loads(p.read_text())
            except Exception:  # noqa: BLE001
                pass
        base = {"CE": {}, "PE": {}}
        for k, row in (payload.get("strikes") or {}).items():
            for side in ("CE", "PE"):
                d = row.get(side) or {}
                base[side][str(float(k))] = float(d.get("open_interest") or 0)
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(base))
        except Exception as exc:  # noqa: BLE001
            log.warning("baseline write failed: %s", exc)
        return base

    def snapshot(self, expiry: str | None = None, force: bool = False) -> ChainSnapshot:
        with self._lock:
            if self._last is not None and not force and time.time() - self._last_fetch < self.min_refresh:
                return self._last
            expiry = expiry or self.nearest_expiry()
            iso = datetime.strptime(expiry, "%d-%b-%Y").strftime("%Y-%m-%d")
            payload = self.client.call("get_option_chain", exchange="NSE", underlying=self.underlying, expiry_date=iso)
            if not payload.get("strikes"):
                raise RuntimeError("empty Groww option chain")
            base = self._baseline(expiry, payload)
            snap = parse_groww_chain(payload, expiry, pd.Timestamp.now(tz=IST).floor("s"), base, self.strike_step)
            self._last = snap
            self._last_fetch = time.time()
            return snap
