"""Portfolio optimization (long-only, with per-asset and per-sector caps).

All inputs are annualized SIMPLE returns: mean = 12 x monthly mean, cov = 12 x monthly cov
(Ledoit-Wolf shrunk). Optimizers are notoriously sensitive to the expected-return
estimate, so `sensitivity()` re-optimizes on bootstrap resamples and reports how much
the weights move.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from .simulate import nearest_psd, shrunk_cov


def estimates(monthly_log: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    simple = np.expm1(monthly_log.to_numpy(float))
    cov, _ = shrunk_cov(simple)
    return simple.mean(axis=0) * 12, nearest_psd(cov * 12)


def _stats(w, mu, cov, rf):
    ret = float(w @ mu)
    vol = float(np.sqrt(max(w @ cov @ w, 0)))
    return {"weights": w.round(6).tolist(), "expected_return": ret, "volatility": vol,
            "sharpe": (ret - rf) / vol if vol > 0 else None}


def _constraints(n, sectors, sector_cap):
    cons = [{"type": "eq", "fun": lambda w: w.sum() - 1}]
    if sectors and sector_cap and sector_cap < 1:
        for s in set(sectors):
            mask = np.array([x == s for x in sectors], float)
            cons.append({"type": "ineq", "fun": lambda w, m=mask: sector_cap - w @ m})
    return cons


def _solve(obj, n, max_w, cons, x0=None):
    x0 = np.full(n, 1 / n) if x0 is None else x0
    res = minimize(obj, x0, method="SLSQP", bounds=[(0, max_w)] * n, constraints=cons,
                   options={"maxiter": 500, "ftol": 1e-12})
    w = np.clip(res.x, 0, None)
    return w / w.sum(), bool(res.success)


def optimize(mu, cov, rf=0.03, max_w=1.0, sectors=None, sector_cap=None, target_vol=None) -> dict:
    n = len(mu)
    max_w = max(max_w, 1 / n + 1e-9)  # caps below 1/n are infeasible
    cons = _constraints(n, sectors, sector_cap)
    out: dict[str, dict] = {}
    notes: list[str] = []

    out["equal_weight"] = _stats(np.full(n, 1 / n), mu, cov, rf)

    w, ok = _solve(lambda w: w @ cov @ w, n, max_w, cons)
    out["min_variance"] = _stats(w, mu, cov, rf)

    w, ok2 = _solve(lambda w: -(w @ mu - rf) / np.sqrt(w @ cov @ w + 1e-16), n, max_w, cons)
    out["max_sharpe"] = _stats(w, mu, cov, rf)

    # Risk parity: each asset contributes equally to portfolio variance
    def rp(w):
        pv = w @ cov @ w
        rc = w * (cov @ w) / (pv + 1e-16)
        return np.sum((rc - 1 / n) ** 2)
    w, _ = _solve(rp, n, max_w, cons)
    out["risk_parity"] = _stats(w, mu, cov, rf)

    if target_vol:
        tv_cons = cons + [{"type": "ineq", "fun": lambda w: target_vol ** 2 - w @ cov @ w}]
        w, _ = _solve(lambda w: -(w @ mu), n, max_w, tv_cons, np.array(out["min_variance"]["weights"]))
        if out["min_variance"]["volatility"] > target_vol + 1e-6:
            notes.append(f"Target volatility {target_vol:.0%} is below the minimum achievable "
                         f"({out['min_variance']['volatility']:.1%}); showing min-variance instead.")
            out["target_volatility"] = out["min_variance"]
        else:
            out["target_volatility"] = _stats(w, mu, cov, rf)
    if not (ok and ok2):
        notes.append("An optimizer did not fully converge; results are approximate.")
    return {"portfolios": out, "notes": notes}


def frontier(mu, cov, max_w=1.0, sectors=None, sector_cap=None, points=30, rf=0.03) -> list[dict]:
    n = len(mu)
    max_w = max(max_w, 1 / n + 1e-9)
    cons = _constraints(n, sectors, sector_cap)
    w_min, _ = _solve(lambda w: w @ cov @ w, n, max_w, cons)
    w_max, _ = _solve(lambda w: -(w @ mu), n, max_w, cons)
    lo, hi = float(w_min @ mu), float(w_max @ mu)
    pts = []
    x0 = w_min
    for target in np.linspace(lo, hi, points):
        c = cons + [{"type": "eq", "fun": lambda w, t=target: w @ mu - t}]
        w, ok = _solve(lambda w: w @ cov @ w, n, max_w, c, x0)
        if ok:
            pts.append(_stats(w, mu, cov, rf))
            x0 = w
    return pts


def random_portfolios(mu, cov, k=1500, seed=0, rf=0.03) -> list[dict]:
    rng = np.random.default_rng(seed)
    W = rng.dirichlet(np.ones(len(mu)) * 0.7, size=k)
    rets = W @ mu
    vols = np.sqrt(np.einsum("ij,jk,ik->i", W, cov, W))
    return [{"expected_return": float(r), "volatility": float(v), "sharpe": float((r - rf) / v)}
            for r, v in zip(rets, vols)]


def sensitivity(monthly_log: pd.DataFrame, rf=0.03, max_w=1.0, sectors=None, sector_cap=None,
                resamples=40, seed=7) -> dict:
    """Re-run max-Sharpe on bootstrap resamples of history: how stable are the weights?"""
    x = monthly_log.to_numpy(float)
    rng = np.random.default_rng(seed)
    ws = []
    for _ in range(resamples):
        sample = pd.DataFrame(x[rng.integers(0, len(x), len(x))], columns=monthly_log.columns)
        mu, cov = estimates(sample)
        ws.append(optimize(mu, cov, rf, max_w, sectors, sector_cap)["portfolios"]["max_sharpe"]["weights"])
    W = np.array(ws)
    return {"mean": W.mean(0).tolist(), "p10": np.percentile(W, 10, 0).tolist(),
            "p90": np.percentile(W, 90, 0).tolist(), "resamples": resamples}
