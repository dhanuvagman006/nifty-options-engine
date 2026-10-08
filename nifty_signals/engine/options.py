"""Black-Scholes pricing, greeks and strike selection for index options."""
from __future__ import annotations

import math
from dataclasses import dataclass

RISK_FREE = 0.065  # approx Indian 91-day T-bill; affects premiums marginally


def _ncdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _npdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


@dataclass
class Greeks:
    price: float
    delta: float
    gamma: float
    theta: float   # per calendar day
    vega: float    # per 1 vol point


def bs(spot: float, strike: float, t_years: float, iv_pct: float, kind: str, r: float = RISK_FREE) -> Greeks:
    """European option price + greeks. iv_pct in percent (e.g. 13.5)."""
    sigma = max(iv_pct, 1.0) / 100.0
    t = max(t_years, 1e-5)
    sq = sigma * math.sqrt(t)
    d1 = (math.log(spot / strike) + (r + 0.5 * sigma * sigma) * t) / sq
    d2 = d1 - sq
    disc = math.exp(-r * t)
    if kind == "CE":
        price = spot * _ncdf(d1) - strike * disc * _ncdf(d2)
        delta = _ncdf(d1)
        theta = (-spot * _npdf(d1) * sigma / (2 * math.sqrt(t)) - r * strike * disc * _ncdf(d2)) / 365.0
    else:
        price = strike * disc * _ncdf(-d2) - spot * _ncdf(-d1)
        delta = _ncdf(d1) - 1.0
        theta = (-spot * _npdf(d1) * sigma / (2 * math.sqrt(t)) + r * strike * disc * _ncdf(-d2)) / 365.0
    gamma = _npdf(d1) / (spot * sq)
    vega = spot * _npdf(d1) * math.sqrt(t) / 100.0
    return Greeks(max(price, 0.05), delta, gamma, theta, vega)


def implied_vol(price: float, spot: float, strike: float, t_years: float, kind: str) -> float:
    """Bisection IV solver (percent). Returns 0 if no solution."""
    lo, hi = 1.0, 200.0
    if price <= 0:
        return 0.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        p = bs(spot, strike, t_years, mid, kind).price
        if abs(p - price) < 1e-3:
            return mid
        if p > price:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


def select_strike(spot: float, kind: str, step: int, itm_strikes: int) -> float:
    """ATM strike, optionally shifted ITM by `itm_strikes` steps."""
    atm = round(spot / step) * step
    if itm_strikes <= 0:
        return float(atm)
    return float(atm - itm_strikes * step) if kind == "CE" else float(atm + itm_strikes * step)


def premium_at(spot_level: float, strike: float, t_years: float, iv_pct: float, kind: str) -> float:
    return bs(spot_level, strike, t_years, iv_pct, kind).price
