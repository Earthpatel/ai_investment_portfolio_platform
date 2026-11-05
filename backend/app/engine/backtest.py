"""Historical backtesting — what WOULD have happened, using only information available
on each date.

Rules that keep it honest:
  * Daily adjusted closes; the test starts once every selected asset has data.
  * Strategy weights at a rebalance date use only prices up to the previous close
    (min-variance looks back over a trailing window; it never sees the future).
  * Transaction costs (bps of traded value) are charged on every trade, including the
    initial purchase.
  * Today's ticker list is used for the whole period — survivorship bias: stocks that
    failed or left the index are missing. The response says so.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .simulate import nearest_psd, shrunk_cov

FREQ_RULE = {"monthly": "ME", "quarterly": "QE", "semiannual": "6ME", "annual": "YE", "never": None}


def _rebalance_dates(idx: pd.DatetimeIndex, freq: str) -> set:
    rule = FREQ_RULE.get(freq)
    if not rule:
        return set()
    s = pd.Series(idx, index=idx)
    # last trading day of each period
    return set(s.groupby(pd.Grouper(freq=rule)).last().dropna().tolist())


def _min_var_weights(rets: pd.DataFrame, max_w: float) -> np.ndarray:
    from scipy.optimize import minimize
    n = rets.shape[1]
    cov, _ = shrunk_cov(rets.to_numpy(float))
    # Annualize: daily variances (~1e-4) are below SLSQP's default tolerance, which made
    # the optimizer stop at its starting point (equal weight) without moving.
    cov = nearest_psd(cov * 252)
    max_w = max(max_w, 1 / n + 1e-9)
    res = minimize(lambda w: w @ cov @ w, np.full(n, 1 / n), method="SLSQP",
                   bounds=[(0, max_w)] * n, constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1}],
                   options={"maxiter": 500, "ftol": 1e-12})
    w = np.clip(res.x, 0, None)
    return w / w.sum()


def run_strategy(prices: pd.DataFrame, target_fn, rebalance: str, initial: float, cost_bps: float):
    """Generic daily engine. target_fn(date_index_position) -> target weights."""
    rets = prices.pct_change().fillna(0.0).to_numpy()
    dates = prices.index
    reb = _rebalance_dates(dates, rebalance)
    n = prices.shape[1]
    cost = cost_bps / 10_000
    w_target = target_fn(0)
    holdings = initial * w_target * (1 - cost)  # pay costs on the initial purchase
    costs_paid = initial * cost
    turnover_total, n_rebal = 1.0, 0
    values = np.empty(len(dates))
    values[0] = holdings.sum()
    events = []
    for i in range(1, len(dates)):
        holdings = holdings * (1 + rets[i])
        v = holdings.sum()
        if dates[i] in reb and i < len(dates) - 1:
            tgt = target_fn(i)
            desired = v * tgt
            traded = np.abs(desired - holdings).sum()
            c = traded * cost
            holdings = (v - c) * tgt
            costs_paid += c
            turnover_total += traded / v
            n_rebal += 1
            events.append({"date": str(dates[i].date()), "turnover": float(traded / v)})
        values[i] = holdings.sum()
    return pd.Series(values, index=dates), {"rebalances": n_rebal, "turnover": float(turnover_total),
                                            "costs_paid": float(costs_paid), "events": events[-60:]}


def metrics(v: pd.Series, rf: float) -> dict:
    r = v.pct_change().dropna()
    years = (v.index[-1] - v.index[0]).days / 365.25
    cagr = (v.iloc[-1] / v.iloc[0]) ** (1 / years) - 1 if years > 0 else 0.0
    vol = float(r.std() * np.sqrt(252))
    dd = 1 - v / v.cummax()
    downside = r[r < 0].std() * np.sqrt(252)
    yearly = v.resample("YE").last()
    first = pd.Series([v.iloc[0]], index=[v.index[0]])
    ann = pd.concat([first, yearly]).pct_change().dropna()
    return {
        "total_return": float(v.iloc[-1] / v.iloc[0] - 1),
        "cagr": float(cagr),
        "volatility": vol,
        "sharpe": float((cagr - rf) / vol) if vol > 0 else None,
        "sortino": float((cagr - rf) / downside) if downside > 0 else None,
        "max_drawdown": float(dd.max()),
        "calmar": float(cagr / dd.max()) if dd.max() > 0 else None,
        "annual_returns": {str(d.year): float(x) for d, x in ann.items()},
        "drawdown_series": dd,
    }


def backtest(prices: pd.DataFrame, weights: np.ndarray, benchmark: pd.Series | None,
             rebalance="quarterly", initial=10_000.0, cost_bps=5.0, rf=0.03, lookback_days=252,
             max_w=0.4) -> dict:
    prices = prices.dropna()  # common period: every asset trades
    if len(prices) < 60:
        raise ValueError("Not enough overlapping history for a backtest (need 60+ common trading days).")
    n = prices.shape[1]
    daily = prices.pct_change()
    w = np.asarray(weights, float)

    def minvar(i):
        if i < lookback_days:
            return np.full(n, 1 / n)  # not enough past data yet -> equal weight
        return _min_var_weights(daily.iloc[i - lookback_days + 1: i + 1], max_w)  # data up to today's close only

    strategies = {
        "buy_and_hold": ("Buy & hold (your weights)", lambda i: w, "never"),
        "rebalanced": (f"Rebalanced {rebalance} (your weights)", lambda i: w, rebalance if rebalance != "never" else "quarterly"),
        "equal_weight": (f"Equal weight, rebalanced {rebalance}", lambda i: np.full(n, 1 / n), rebalance if rebalance != "never" else "quarterly"),
        "min_variance": (f"Min-variance (trailing {lookback_days}d, walk-forward)", minvar, rebalance if rebalance != "never" else "quarterly"),
    }
    out = {}
    for key, (label, fn, freq) in strategies.items():
        v, info = run_strategy(prices, fn, freq, initial, cost_bps)
        m = metrics(v, rf)
        dd = m.pop("drawdown_series")
        out[key] = {"label": label, "metrics": m, "trading": info,
                    "series": _downsample(v), "drawdown": _downsample(dd)}
    if benchmark is not None:
        b = benchmark.reindex(prices.index).ffill().dropna()
        if len(b) > 30:
            bv = initial * b / b.iloc[0]
            m = metrics(bv, rf)
            dd = m.pop("drawdown_series")
            out["benchmark"] = {"label": "Benchmark (SPY buy & hold)", "metrics": m, "trading": None,
                                "series": _downsample(bv), "drawdown": _downsample(dd)}
    return {
        "start": str(prices.index[0].date()), "end": str(prices.index[-1].date()),
        "strategies": out,
        "disclosures": [
            "Uses today's tickers for the whole period (survivorship bias: companies that failed or left the index are excluded).",
            "Starts when every selected asset has price data; earlier history is ignored.",
            f"Transaction costs: {cost_bps:g} bps of traded value; taxes and bid/ask spreads beyond that are ignored.",
            "Past performance is a single historical path, not a forecast. Monte Carlo explores many possible futures instead.",
        ],
    }


def _downsample(s: pd.Series, max_points: int = 600) -> list[list]:
    step = max(1, len(s) // max_points)
    s2 = s.iloc[::step]
    if s2.index[-1] != s.index[-1]:
        s2 = pd.concat([s2, s.iloc[[-1]]])
    return [[str(d.date()), round(float(x), 4)] for d, x in s2.items()]
