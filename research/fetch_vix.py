"""Download daily India VIX history for backtests (Yahoo Finance, ^INDIAVIX) into cache/india_vix_1d.parquet.

    pip install yfinance
    python research/fetch_vix.py [--start 2017-01-01] [--out cache/india_vix_1d.parquet]

The file is not committed to the repository (Yahoo's terms do not allow redistribution); every
contributor fetches their own copy. Without it the engine falls back to a realised-volatility proxy,
which changes the backtest numbers (see docs/PROOF.md).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument("--start", default="2017-01-01")
ap.add_argument("--out", default="cache/india_vix_1d.parquet")
a = ap.parse_args()

import yfinance as yf  # noqa: E402

raw = yf.download("^INDIAVIX", start=a.start, auto_adjust=False, progress=False)
if raw.empty:
    raise SystemExit("no data returned")
if isinstance(raw.columns, pd.MultiIndex):
    raw.columns = raw.columns.get_level_values(0)
df = raw.rename(columns=str.lower)[["open", "high", "low", "close"]].astype(float)
df["volume"] = 0.0
df = df.dropna(subset=["close"])
df.index = pd.DatetimeIndex(df.index).tz_localize("Asia/Kolkata").normalize()
df.index.name = "ts"
df = df[~df.index.duplicated()].sort_index()
Path(a.out).parent.mkdir(parents=True, exist_ok=True)
df.to_parquet(a.out)
print(f"{len(df)} rows {df.index[0].date()} -> {df.index[-1].date()} written to {a.out}")
