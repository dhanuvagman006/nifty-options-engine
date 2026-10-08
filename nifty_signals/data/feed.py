"""Bar frame conventions, CSV source and resampling helpers.

All frames are normalised to:
    index  : tz-aware DatetimeIndex (Asia/Kolkata), bar START time
    columns: open, high, low, close, volume  (float64)
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol

import numpy as np
import pandas as pd

IST = "Asia/Kolkata"
log = logging.getLogger(__name__)
COLS = ["open", "high", "low", "close", "volume"]


class BarSource(Protocol):
    """Pluggable interface. Implement this to connect a broker feed (Kite, Dhan, Upstox...)."""

    def bars(self, interval: str, days: int) -> pd.DataFrame: ...


def _normalise(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=COLS, index=pd.DatetimeIndex([], tz=IST))
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = [c[0] for c in df.columns]
    df = df.rename(columns={c: c.lower().replace(" ", "_") for c in df.columns})
    df = df[[c for c in COLS if c in df.columns]].copy()
    for c in COLS:
        if c not in df.columns:
            df[c] = 0.0
    df = df[COLS].astype("float64")
    idx = pd.DatetimeIndex(df.index)
    if idx.tz is None:
        idx = idx.tz_localize(IST)
    else:
        idx = idx.tz_convert(IST)
    df.index = idx
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = df.dropna(subset=["open", "high", "low", "close"])
    df = df[(df["high"] >= df["low"]) & (df["close"] > 0)]
    return df


def interval_minutes(interval: str) -> int:
    if interval.endswith("m"):
        return int(interval[:-1])
    if interval.endswith("h"):
        return int(interval[:-1]) * 60
    if interval.endswith("d"):
        return int(interval[:-1]) * 24 * 60
    raise ValueError(interval)


def drop_incomplete_last_bar(df: pd.DataFrame, interval: str, now: pd.Timestamp | None = None) -> pd.DataFrame:
    """Remove a trailing bar whose period has not finished yet (live polling safety)."""
    if df.empty:
        return df
    now = now or pd.Timestamp.now(tz=IST)
    mins = interval_minutes(interval)
    last_start = df.index[-1]
    if mins >= 1440:
        return df if now.date() > last_start.date() else df.iloc[:-1]
    if last_start + timedelta(minutes=mins) > now:
        return df.iloc[:-1]
    return df


class CSVSource:
    """Reads bars from a CSV with columns: datetime, open, high, low, close[, volume]."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    _cache: dict = {}

    def _load(self) -> pd.DataFrame:
        key = str(self.path)
        if key not in CSVSource._cache:
            if self.path.suffix == ".parquet":
                raw = pd.read_parquet(self.path)
            else:
                raw = pd.read_csv(self.path)
                tcol = next(c for c in raw.columns if c.lower() in ("datetime", "date", "time", "timestamp"))
                raw[tcol] = pd.to_datetime(raw[tcol])
                raw = raw.set_index(tcol)
            CSVSource._cache[key] = _normalise(raw)
        return CSVSource._cache[key]

    def bars(self, interval: str, days: int) -> pd.DataFrame:
        """Resamples the file's bars to the requested interval; `days` limits the tail."""
        df = self._load()
        mins = interval_minutes(interval)
        if mins >= 1440:
            out = df.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna(subset=["open"])
        else:
            base = int(round((df.index[1:] - df.index[:-1]).to_series().dt.total_seconds().median() / 60)) if len(df) > 1 else mins
            out = resample(df, mins) if mins > base else df
        if days and len(out):
            out = out[out.index >= out.index[-1] - pd.Timedelta(days=days)]
        return out


def resample(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """Resample 5m bars to a higher timeframe anchored at the 09:15 session open."""
    if df.empty:
        return df
    rs = df.resample(f"{minutes}min", label="left", closed="left", origin="start_day", offset="555min")
    out = rs.agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
    return out.dropna(subset=["open"])


def session_ids(index: pd.DatetimeIndex) -> np.ndarray:
    """Integer id per trading date, monotonically increasing."""
    d = index.tz_convert(IST).date
    codes, _ = pd.factorize(pd.Index(d), sort=True)
    return codes.astype(np.int64)
