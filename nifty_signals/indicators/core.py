"""Vectorised / JIT-compiled technical indicators on float64 numpy arrays.

Every function is pure and O(n) (percentile rank / donchian are O(n*w)).
numba is optional: if unavailable the same code runs as plain Python/numpy.
"""
from __future__ import annotations

import numpy as np

try:  # pragma: no cover - import guard
    from numba import njit
except Exception:  # noqa: BLE001
    def njit(*args, **kwargs):  # type: ignore
        if args and callable(args[0]):
            return args[0]
        return lambda f: f

NAN = np.nan


@njit(cache=True)
def ema(x: np.ndarray, n: int) -> np.ndarray:
    out = np.empty_like(x)
    out[:] = NAN
    if n <= 0 or x.size == 0:
        return out
    a = 2.0 / (n + 1.0)
    cnt = 0
    s = 0.0
    start = -1
    for i in range(x.size):
        if np.isnan(x[i]):
            continue
        s += x[i]
        cnt += 1
        if cnt == n:
            out[i] = s / n
            start = i
            break
    if start < 0:
        return out
    prev = out[start]
    for i in range(start + 1, x.size):
        v = x[i]
        if np.isnan(v):
            out[i] = prev
        else:
            prev = a * v + (1.0 - a) * prev
            out[i] = prev
    return out


@njit(cache=True)
def sma(x: np.ndarray, n: int) -> np.ndarray:
    out = np.empty_like(x)
    out[:] = NAN
    if n <= 0:
        return out
    s = 0.0
    for i in range(x.size):
        s += x[i]
        if i >= n:
            s -= x[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


@njit(cache=True)
def rma(x: np.ndarray, n: int) -> np.ndarray:
    """Wilder smoothing."""
    out = np.empty_like(x)
    out[:] = NAN
    if n <= 0 or x.size < n:
        return out
    s = 0.0
    for i in range(n):
        s += x[i]
    prev = s / n
    out[n - 1] = prev
    a = 1.0 / n
    for i in range(n, x.size):
        prev = a * x[i] + (1.0 - a) * prev
        out[i] = prev
    return out


@njit(cache=True)
def true_range(h: np.ndarray, l: np.ndarray, c: np.ndarray) -> np.ndarray:
    tr = np.empty_like(c)
    tr[0] = h[0] - l[0]
    for i in range(1, c.size):
        hl = h[i] - l[i]
        hc = abs(h[i] - c[i - 1])
        lc = abs(l[i] - c[i - 1])
        tr[i] = max(hl, max(hc, lc))
    return tr


@njit(cache=True)
def atr(h: np.ndarray, l: np.ndarray, c: np.ndarray, n: int) -> np.ndarray:
    return rma(true_range(h, l, c), n)


@njit(cache=True)
def rsi(c: np.ndarray, n: int) -> np.ndarray:
    out = np.empty_like(c)
    out[:] = NAN
    if c.size <= n:
        return out
    gain = np.zeros_like(c)
    loss = np.zeros_like(c)
    for i in range(1, c.size):
        d = c[i] - c[i - 1]
        if d > 0:
            gain[i] = d
        else:
            loss[i] = -d
    ag = rma(gain[1:], n)
    al = rma(loss[1:], n)
    for i in range(ag.size):
        if np.isnan(ag[i]):
            continue
        if al[i] == 0.0:
            out[i + 1] = 100.0
        else:
            rs = ag[i] / al[i]
            out[i + 1] = 100.0 - 100.0 / (1.0 + rs)
    return out


@njit(cache=True)
def adx(h: np.ndarray, l: np.ndarray, c: np.ndarray, n: int):
    """Returns (adx, +DI, -DI)."""
    size = c.size
    pdm = np.zeros(size)
    mdm = np.zeros(size)
    for i in range(1, size):
        up = h[i] - h[i - 1]
        dn = l[i - 1] - l[i]
        if up > dn and up > 0:
            pdm[i] = up
        if dn > up and dn > 0:
            mdm[i] = dn
    tr = true_range(h, l, c)
    atr_ = rma(tr, n)
    spdm = rma(pdm, n)
    smdm = rma(mdm, n)
    pdi = np.empty(size)
    mdi = np.empty(size)
    dx = np.empty(size)
    pdi[:] = NAN
    mdi[:] = NAN
    dx[:] = NAN
    for i in range(size):
        if np.isnan(atr_[i]) or atr_[i] == 0.0:
            continue
        pdi[i] = 100.0 * spdm[i] / atr_[i]
        mdi[i] = 100.0 * smdm[i] / atr_[i]
        s = pdi[i] + mdi[i]
        dx[i] = 0.0 if s == 0.0 else 100.0 * abs(pdi[i] - mdi[i]) / s
    out = np.empty(size)
    out[:] = NAN
    first = -1
    for i in range(size):
        if not np.isnan(dx[i]):
            first = i
            break
    if first < 0 or size - first < n:
        return out, pdi, mdi
    s = 0.0
    for i in range(first, first + n):
        s += dx[i]
    prev = s / n
    out[first + n - 1] = prev
    a = 1.0 / n
    for i in range(first + n, size):
        prev = a * dx[i] + (1.0 - a) * prev
        out[i] = prev
    return out, pdi, mdi


@njit(cache=True)
def supertrend(h: np.ndarray, l: np.ndarray, c: np.ndarray, n: int, mult: float):
    """Returns (line, direction) where direction is +1 (up) / -1 (down)."""
    size = c.size
    a = atr(h, l, c, n)
    line = np.empty(size)
    direc = np.zeros(size)
    line[:] = NAN
    ub_prev = NAN
    lb_prev = NAN
    d_prev = 1
    for i in range(size):
        if np.isnan(a[i]):
            continue
        mid = (h[i] + l[i]) / 2.0
        ub = mid + mult * a[i]
        lb = mid - mult * a[i]
        if not np.isnan(lb_prev):
            if lb < lb_prev and c[i - 1] > lb_prev:
                lb = lb_prev
            if ub > ub_prev and c[i - 1] < ub_prev:
                ub = ub_prev
        d = d_prev
        if np.isnan(ub_prev):
            d = 1 if c[i] > ub else -1
        elif d_prev == 1 and c[i] < lb_prev:
            d = -1
        elif d_prev == -1 and c[i] > ub_prev:
            d = 1
        if d != d_prev:
            ub = mid + mult * a[i]
            lb = mid - mult * a[i]
        line[i] = lb if d == 1 else ub
        direc[i] = d
        ub_prev = ub
        lb_prev = lb
        d_prev = d
    return line, direc


@njit(cache=True)
def macd(c: np.ndarray, fast: int, slow: int, sig: int):
    m = ema(c, fast) - ema(c, slow)
    s = ema(m, sig)
    return m, s, m - s


@njit(cache=True)
def bollinger(c: np.ndarray, n: int, k: float):
    """Returns (mid, upper, lower, bandwidth_pct)."""
    size = c.size
    mid = np.empty(size)
    up = np.empty(size)
    lo = np.empty(size)
    bw = np.empty(size)
    mid[:] = NAN
    up[:] = NAN
    lo[:] = NAN
    bw[:] = NAN
    s = 0.0
    s2 = 0.0
    for i in range(size):
        s += c[i]
        s2 += c[i] * c[i]
        if i >= n:
            s -= c[i - n]
            s2 -= c[i - n] * c[i - n]
        if i >= n - 1:
            m = s / n
            var = s2 / n - m * m
            if var < 0.0:
                var = 0.0
            sd = np.sqrt(var)
            mid[i] = m
            up[i] = m + k * sd
            lo[i] = m - k * sd
            bw[i] = 0.0 if m == 0.0 else (up[i] - lo[i]) / m * 100.0
    return mid, up, lo, bw


@njit(cache=True)
def efficiency_ratio(c: np.ndarray, n: int) -> np.ndarray:
    out = np.empty_like(c)
    out[:] = NAN
    for i in range(n, c.size):
        net = abs(c[i] - c[i - n])
        vol = 0.0
        for j in range(i - n + 1, i + 1):
            vol += abs(c[j] - c[j - 1])
        out[i] = 0.0 if vol == 0.0 else net / vol
    return out


@njit(cache=True)
def donchian(h: np.ndarray, l: np.ndarray, n: int):
    """Highest high / lowest low of the PREVIOUS n bars (excludes current bar)."""
    size = h.size
    up = np.empty(size)
    lo = np.empty(size)
    up[:] = NAN
    lo[:] = NAN
    for i in range(n, size):
        mx = -1e300
        mn = 1e300
        for j in range(i - n, i):
            if h[j] > mx:
                mx = h[j]
            if l[j] < mn:
                mn = l[j]
        up[i] = mx
        lo[i] = mn
    return up, lo


@njit(cache=True)
def pct_rank(x: np.ndarray, w: int) -> np.ndarray:
    """Percentile rank (0-100) of x[i] within the trailing window of w values."""
    out = np.empty_like(x)
    out[:] = NAN
    for i in range(x.size):
        if np.isnan(x[i]):
            continue
        lo = i - w + 1
        if lo < 0:
            lo = 0
        cnt = 0
        below = 0
        for j in range(lo, i + 1):
            v = x[j]
            if np.isnan(v):
                continue
            cnt += 1
            if v <= x[i]:
                below += 1
        if cnt >= 20:
            out[i] = 100.0 * below / cnt
    return out


@njit(cache=True)
def session_vwap(tp: np.ndarray, vol: np.ndarray, sess: np.ndarray) -> np.ndarray:
    """Session-anchored VWAP. If volume is all zero the result is the session TWAP."""
    out = np.empty_like(tp)
    pv = 0.0
    vv = 0.0
    cur = -1
    for i in range(tp.size):
        if sess[i] != cur:
            cur = sess[i]
            pv = 0.0
            vv = 0.0
        v = vol[i] if vol[i] > 0 else 1.0
        pv += tp[i] * v
        vv += v
        out[i] = pv / vv
    return out


@njit(cache=True)
def session_opening_range(h: np.ndarray, l: np.ndarray, sess: np.ndarray, k: int):
    """High/low of first k bars of each session, available from bar k onwards."""
    size = h.size
    orh = np.empty(size)
    orl = np.empty(size)
    orh[:] = NAN
    orl[:] = NAN
    cur = -1
    cnt = 0
    hh = -1e300
    ll = 1e300
    for i in range(size):
        if sess[i] != cur:
            cur = sess[i]
            cnt = 0
            hh = -1e300
            ll = 1e300
        if cnt < k:
            if h[i] > hh:
                hh = h[i]
            if l[i] < ll:
                ll = l[i]
            cnt += 1
        if cnt >= k:
            orh[i] = hh
            orl[i] = ll
    return orh, orl


@njit(cache=True)
def session_bar_index(sess: np.ndarray) -> np.ndarray:
    out = np.zeros(sess.size, dtype=np.int64)
    cur = -1
    n = 0
    for i in range(sess.size):
        if sess[i] != cur:
            cur = sess[i]
            n = 0
        out[i] = n
        n += 1
    return out


@njit(cache=True)
def swing_pivots(h: np.ndarray, l: np.ndarray, k: int):
    """Confirmed swing highs/lows (fractal strength k), forward-filled with no lookahead.

    Returns (last_swing_high, last_swing_low, prev_swing_high, prev_swing_low).
    A pivot at bar j is only known at bar j+k.
    """
    size = h.size
    lsh = np.empty(size)
    lsl = np.empty(size)
    psh = np.empty(size)
    psl = np.empty(size)
    lsh[:] = NAN
    lsl[:] = NAN
    psh[:] = NAN
    psl[:] = NAN
    cur_h = NAN
    cur_l = NAN
    prev_h = NAN
    prev_l = NAN
    for i in range(size):
        j = i - k
        if j >= k:
            is_h = True
            is_l = True
            for m in range(1, k + 1):
                if h[j] <= h[j - m] or h[j] <= h[j + m]:
                    is_h = False
                if l[j] >= l[j - m] or l[j] >= l[j + m]:
                    is_l = False
                if not is_h and not is_l:
                    break
            if is_h:
                prev_h = cur_h
                cur_h = h[j]
            if is_l:
                prev_l = cur_l
                cur_l = l[j]
        lsh[i] = cur_h
        lsl[i] = cur_l
        psh[i] = prev_h
        psl[i] = prev_l
    return lsh, lsl, psh, psl


@njit(cache=True)
def linreg_slope(c: np.ndarray, n: int) -> np.ndarray:
    """Slope of least-squares line over trailing n bars, normalised by price (% per bar)."""
    out = np.empty_like(c)
    out[:] = NAN
    sx = 0.0
    sxx = 0.0
    for j in range(n):
        sx += j
        sxx += j * j
    den = n * sxx - sx * sx
    for i in range(n - 1, c.size):
        sy = 0.0
        sxy = 0.0
        for j in range(n):
            y = c[i - n + 1 + j]
            sy += y
            sxy += j * y
        slope = (n * sxy - sx * sy) / den
        out[i] = 0.0 if c[i] == 0.0 else slope / c[i] * 100.0
    return out


@njit(cache=True)
def rolling_max(x: np.ndarray, n: int) -> np.ndarray:
    out = np.empty_like(x)
    out[:] = NAN
    for i in range(n - 1, x.size):
        m = -1e300
        for j in range(i - n + 1, i + 1):
            if x[j] > m:
                m = x[j]
        out[i] = m
    return out


@njit(cache=True)
def rolling_min(x: np.ndarray, n: int) -> np.ndarray:
    out = np.empty_like(x)
    out[:] = NAN
    for i in range(n - 1, x.size):
        m = 1e300
        for j in range(i - n + 1, i + 1):
            if x[j] < m:
                m = x[j]
        out[i] = m
    return out


def warmup() -> None:
    """Trigger numba compilation once (cached on disk afterwards)."""
    x = np.linspace(100.0, 110.0, 80)
    h = x + 0.5
    l = x - 0.5
    s = np.zeros(80, dtype=np.int64)
    ema(x, 5); sma(x, 5); rma(x, 5); atr(h, l, x, 5); rsi(x, 5); adx(h, l, x, 5)
    supertrend(h, l, x, 5, 2.0); macd(x, 5, 10, 3); bollinger(x, 5, 2.0)
    efficiency_ratio(x, 5); donchian(h, l, 5); pct_rank(x, 30)
    session_vwap(x, s.astype(np.float64), s); session_opening_range(h, l, s, 3)
    session_bar_index(s); swing_pivots(h, l, 2); linreg_slope(x, 5); rolling_max(x, 5); rolling_min(x, 5)
