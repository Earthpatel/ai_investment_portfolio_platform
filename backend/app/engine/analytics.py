"""Single-asset statistics, technical indicators, and historical stress tests.

Indicators here are DESCRIPTIVE (explorer charts, ML features). They are NOT used to
calibrate Monte Carlo — calibration uses only return means/covariances or resampled
historical returns.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    d = close.diff()
    gain = d.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def macd(close: pd.Series) -> tuple[pd.Series, pd.Series]:
    line = close.ewm(span=12, adjust=False, min_periods=26).mean() - close.ewm(span=26, adjust=False, min_periods=26).mean()
    signal = line.ewm(span=9, adjust=False, min_periods=9).mean()
    return line, signal


PERIODS = {"1m": 21, "6m": 126, "1y": 252, "3y": 756, "5y": 1260, "10y": 2520, "max": None}


def asset_report(close: pd.Series, volume: pd.Series | None, market: pd.Series | None, period: str, rf: float = 0.03) -> dict:
    close = close.dropna()
    full = close
    n = PERIODS.get(period, 1260)
    close = close.iloc[-n:] if n else close
    r = close.pct_change().dropna()
    years = max((close.index[-1] - close.index[0]).days / 365.25, 1e-9)
    cagr = (close.iloc[-1] / close.iloc[0]) ** (1 / years) - 1
    vol = r.std() * np.sqrt(252)
    dd = 1 - close / close.cummax()

    # Indicators computed on FULL history (so warm-up is done), then cut to the window
    sma50 = full.rolling(50).mean().reindex(close.index)
    sma200 = full.rolling(200).mean().reindex(close.index)
    r14 = rsi(full).reindex(close.index)
    m_line, m_sig = macd(full)
    m_line, m_sig = m_line.reindex(close.index), m_sig.reindex(close.index)
    roll_vol = full.pct_change().rolling(63).std().mul(np.sqrt(252)).reindex(close.index)

    corr = beta = None
    if market is not None:
        mr = market.reindex(close.index).pct_change()
        both = pd.concat([r, mr], axis=1, sort=True).dropna()
        if len(both) > 30:
            corr = float(both.corr().iloc[0, 1])
            beta = float(both.cov().iloc[0, 1] / both.iloc[:, 1].var())

    step = max(1, len(close) // 500)
    pts = close.index[::step].append(close.index[-1:]).unique()
    series = [{"date": str(d.date()), "close": round(float(close[d]), 4),
               "sma50": _f(sma50[d]), "sma200": _f(sma200[d]), "rsi": _f(r14[d]),
               "macd": _f(m_line[d]), "signal": _f(m_sig[d]), "drawdown": round(float(dd[d]), 4),
               "vol63": _f(roll_vol[d])} for d in pts]
    hist_counts, edges = np.histogram(r, bins=40)
    return {
        "stats": {"start": str(close.index[0].date()), "end": str(close.index[-1].date()),
                  "total_return": float(close.iloc[-1] / close.iloc[0] - 1), "cagr": float(cagr),
                  "volatility": float(vol), "sharpe": float((cagr - rf) / vol) if vol > 0 else None,
                  "max_drawdown": float(dd.max()), "corr_with_spy": corr, "beta_vs_spy": beta,
                  "best_day": float(r.max()), "worst_day": float(r.min()),
                  "skew": float(r.skew()), "kurtosis": float(r.kurt()),
                  "last_price": float(close.iloc[-1]), "rsi_now": _f(r14.iloc[-1])},
        "series": series,
        "return_hist": [{"x": float((edges[i] + edges[i + 1]) / 2), "count": int(c)} for i, c in enumerate(hist_counts)],
        "normal_ref": {"mean": float(r.mean()), "std": float(r.std())},
    }


def _f(x):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) or pd.isna(x) else round(float(x), 4)


CRISES = {
    "dotcom": ("Dot-com bust", "2000-03-24", "2002-10-09"),
    "gfc": ("Global Financial Crisis", "2007-10-09", "2009-03-09"),
    "euro2011": ("2011 debt-ceiling / euro crisis", "2011-04-29", "2011-10-03"),
    "covid": ("COVID-19 crash", "2020-02-19", "2020-03-23"),
    "rates2022": ("2022 rate-hike bear market", "2022-01-03", "2022-10-12"),
}


def stress_tests(close: pd.DataFrame, weights: np.ndarray, proxy: pd.Series | None, initial: float) -> list[dict]:
    """Replay real crisis periods on today's weights (buy & hold through the window).

    If an asset did not exist yet, the benchmark (SPY) stands in and the result says so.
    """
    out = []
    tickers = list(close.columns)
    for key, (label, a, b) in CRISES.items():
        a, b = pd.Timestamp(a), pd.Timestamp(b)
        cols, proxied = [], []
        for t in tickers:
            s = close[t].loc[a:b].dropna()
            if len(s) > 5 and s.index[0] - a < pd.Timedelta(days=10):
                cols.append(s / s.iloc[0])
            elif proxy is not None and len(proxy.loc[a:b].dropna()) > 5:
                p = proxy.loc[a:b].dropna()
                cols.append(p / p.iloc[0])
                proxied.append(t)
            else:
                cols = None
                break
        if cols is None:
            out.append({"key": key, "label": label, "start": str(a.date()), "end": str(b.date()), "available": False})
            continue
        growth = pd.concat(cols, axis=1).ffill().dropna()
        path = initial * (growth.to_numpy() @ weights)
        dd = 1 - path / np.maximum.accumulate(path)
        step = max(1, len(path) // 120)
        out.append({"key": key, "label": label, "start": str(a.date()), "end": str(b.date()), "available": True,
                    "total_return": float(path[-1] / path[0] - 1), "max_drawdown": float(dd.max()),
                    "proxied": proxied,
                    "path": [[str(d.date()), round(float(v), 2)] for d, v in zip(growth.index[::step], path[::step])]})
    return out
