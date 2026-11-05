"""Monte Carlo portfolio simulation.

Return convention (stated once, used everywhere):
  * Asset returns are generated as MONTHLY LOG returns r.  Gross growth = exp(r) > 0,
    so prices can never go negative.
  * Portfolio value is the sum of dollar holdings; each holding grows by exp(r).
    Holdings drift between rebalances, which is what really happens.
  * Annual "expected return" inputs are ARITHMETIC (what people quote); they are
    converted to log-space with the lognormal identities in `_custom_params`.

Three methods:
  parametric  - correlated multivariate normal log returns, mean + covariance
                estimated from history (Ledoit-Wolf shrinkage, PSD repaired)
  bootstrap   - resample whole months of joint historical returns in blocks
                (keeps fat tails, cross-asset correlation, some autocorrelation)
  custom      - user-specified annual mean/volatility per asset, historical
                correlation; clearly labeled as an assumption, not a forecast
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

PCTS = [5, 10, 25, 50, 75, 90, 95]
REBAL_MONTHS = {"never": 0, "monthly": 1, "quarterly": 3, "semiannual": 6, "annual": 12}


@dataclass
class SimConfig:
    weights: np.ndarray
    initial: float = 10_000.0
    contribution: float = 0.0
    contribution_freq: str = "monthly"  # none | weekly | monthly | annual
    contribution_timing: str = "start"  # start | end  (of each period)
    years: int = 10
    n_sims: int = 1_000
    method: str = "parametric"  # parametric | bootstrap | custom
    seed: int = 42
    rebalance: str = "annual"
    fee_annual: float = 0.0  # expense ratio / advisory fee, fraction per year
    inflation: float = 0.025
    drip: bool = True  # reinvest dividends
    goal: float | None = None
    block_months: int = 6
    custom_mu: np.ndarray | None = None  # annual arithmetic mean, per asset
    custom_sigma: np.ndarray | None = None  # annual volatility, per asset
    sample_paths: int = 150
    stress_vol_mult: float = 1.0  # what-if: scale volatility


@dataclass
class Calibration:
    mu: np.ndarray  # monthly log mean
    cov: np.ndarray  # monthly log covariance
    hist: np.ndarray | None  # (T, n) monthly log returns for bootstrap
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Calibration helpers
# ---------------------------------------------------------------------------
def nearest_psd(cov: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    """Clip negative eigenvalues so Cholesky always works (numerical safety)."""
    cov = (cov + cov.T) / 2
    vals, vecs = np.linalg.eigh(cov)
    vals = np.clip(vals, eps, None)
    return (vecs * vals) @ vecs.T


def shrunk_cov(x: np.ndarray) -> tuple[np.ndarray, float]:
    """Ledoit-Wolf shrinkage — sample covariance is noisy with few months of data."""
    from sklearn.covariance import LedoitWolf
    if x.shape[1] == 1:
        return np.atleast_2d(np.var(x, ddof=1)), 0.0
    lw = LedoitWolf().fit(x)
    return lw.covariance_, float(lw.shrinkage_)


def calibrate(monthly_log: pd.DataFrame) -> Calibration:
    x = monthly_log.to_numpy(dtype=float)
    cov, shrink = shrunk_cov(x)
    notes = [f"Calibrated on {len(x)} months ({monthly_log.index[0]:%b %Y} – {monthly_log.index[-1]:%b %Y}).",
             f"Covariance: Ledoit-Wolf shrinkage intensity {shrink:.2f}."]
    return Calibration(mu=x.mean(axis=0), cov=nearest_psd(cov), hist=x, notes=notes)


def _custom_params(mu_a: np.ndarray, sig_a: np.ndarray, corr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Annual arithmetic (mean m, vol s) -> monthly log (mu, cov), assuming lognormal.

    For gross return G ~ LogNormal(a, b^2):  E[G] = 1+m,  Var[G] = s^2
      b^2 = ln(1 + s^2/(1+m)^2),  a = ln(1+m) - b^2/2
    """
    b2 = np.log1p(sig_a ** 2 / (1 + mu_a) ** 2)
    a = np.log1p(mu_a) - b2 / 2
    sd_m = np.sqrt(b2 / 12)
    cov = corr * np.outer(sd_m, sd_m)
    return a / 12, nearest_psd(cov, 0.0) if np.allclose(sd_m, 0) else nearest_psd(cov)


def annualize(mu_m: np.ndarray, cov_m: np.ndarray) -> dict:
    var = np.diag(cov_m)
    return {
        "log_mean": (mu_m * 12).tolist(),
        "volatility": np.sqrt(var * 12).tolist(),
        "arithmetic_mean": (np.exp(mu_m * 12 + var * 6) - 1).tolist(),
        "geometric_mean": (np.exp(mu_m * 12) - 1).tolist(),
    }


# ---------------------------------------------------------------------------
# Contribution schedule
# ---------------------------------------------------------------------------
def contribution_schedule(cfg: SimConfig, steps: int) -> np.ndarray:
    """Dollars added in each month. Weekly = 52/12 contributions per month on average."""
    c = np.zeros(steps)
    if cfg.contribution <= 0 or cfg.contribution_freq == "none":
        return c
    if cfg.contribution_freq == "monthly":
        c[:] = cfg.contribution
    elif cfg.contribution_freq == "weekly":
        c[:] = cfg.contribution * 52 / 12
    elif cfg.contribution_freq == "annual":
        months = np.arange(steps)
        c[(months % 12 == 0) if cfg.contribution_timing == "start" else (months % 12 == 11)] = cfg.contribution
    return c


# ---------------------------------------------------------------------------
# Core simulation
# ---------------------------------------------------------------------------
def _random_returns(cfg: SimConfig, cal: Calibration, rng: np.random.Generator, steps: int):
    """Yields (n_sims, n_assets) monthly log returns for each step."""
    n_sims, n = cfg.n_sims, len(cfg.weights)
    if cfg.method == "bootstrap":
        hist = cal.hist
        T = hist.shape[0]
        if cfg.stress_vol_mult != 1.0:
            m = hist.mean(axis=0)
            hist = m + (hist - m) * cfg.stress_vol_mult
        block = max(1, min(cfg.block_months, T))
        n_blocks = int(np.ceil(steps / block))
        starts = rng.integers(0, T, size=(n_sims, n_blocks))
        offs = np.arange(block)
        idx = ((starts[:, :, None] + offs[None, None, :]) % T).reshape(n_sims, -1)[:, :steps]  # circular blocks
        for t in range(steps):
            yield hist[idx[:, t]]
    else:
        mu, cov = cal.mu, cal.cov
        if cfg.stress_vol_mult != 1.0:
            cov = cov * cfg.stress_vol_mult ** 2
        L = np.linalg.cholesky(cov) if np.any(cov) else np.zeros((n, n))
        for _ in range(steps):
            z = rng.standard_normal((n_sims, n))
            yield mu + z @ L.T


def run(cfg: SimConfig, cal: Calibration, div_yield: np.ndarray | None = None) -> dict:
    w = np.asarray(cfg.weights, float)
    if w.ndim != 1 or len(w) == 0:
        raise ValueError("weights must be a non-empty vector")
    if abs(w.sum() - 1) > 1e-6 or (w < 0).any():
        raise ValueError("weights must be non-negative and sum to 1")
    n = len(w)
    steps = int(cfg.years * 12)
    rng = np.random.default_rng(cfg.seed)
    y_m = (np.zeros(n) if div_yield is None else np.asarray(div_yield, float)) / 12
    fee_m = (1 - cfg.fee_annual) ** (1 / 12)
    rebal_k = REBAL_MONTHS.get(cfg.rebalance, 12)
    contrib = contribution_schedule(cfg, steps)
    start_c = contrib if cfg.contribution_timing == "start" else np.zeros(steps)
    end_c = contrib if cfg.contribution_timing == "end" else np.zeros(steps)

    H = np.zeros((cfg.n_sims, n))  # dollar holdings per asset
    H += cfg.initial * w
    cash = np.zeros(cfg.n_sims)  # dividends paid out when DRIP is off (held as cash)
    twr = np.ones(cfg.n_sims)  # time-weighted return index (ignores cash flows)
    values = np.empty((cfg.n_sims, steps + 1), dtype=np.float64)
    twr_path = np.empty((cfg.n_sims, steps + 1))
    values[:, 0] = H.sum(1)
    twr_path[:, 0] = 1.0

    for t, r in enumerate(_random_returns(cfg, cal, rng, steps)):
        H += start_c[t] * w  # new money buys the target mix
        before = H.sum(1)
        gross = np.exp(r)  # total-return growth (dividends included in adjusted prices)
        if cfg.drip:
            H = H * gross
            paid = 0.0
        else:
            paid_assets = H * y_m  # dividends taken out as cash instead of reinvested
            H = H * gross - paid_assets
            paid = paid_assets.sum(1)
            cash += paid
        H *= fee_m
        after = H.sum(1) + paid
        safe = before > 0
        port_r = np.where(safe, after / np.where(safe, before, 1) - 1, (np.exp(r) - 1) @ w * fee_m)
        twr *= 1 + port_r
        H += end_c[t] * w
        if rebal_k and (t + 1) % rebal_k == 0:
            H = H.sum(1, keepdims=True) * w
        values[:, t + 1] = H.sum(1) + cash
        twr_path[:, t + 1] = twr

    return summarize(cfg, values, twr_path, contrib)


# ---------------------------------------------------------------------------
# Summary statistics
# ---------------------------------------------------------------------------
def max_drawdowns(index_paths: np.ndarray) -> np.ndarray:
    peak = np.maximum.accumulate(index_paths, axis=1)
    return (1 - index_paths / peak).max(axis=1)


def summarize(cfg: SimConfig, values: np.ndarray, twr_path: np.ndarray, contrib: np.ndarray) -> dict:
    steps = values.shape[1] - 1
    months = np.arange(steps + 1)
    cum_contrib = cfg.initial + np.concatenate([[0.0], np.cumsum(contrib)])
    infl = (1 + cfg.inflation) ** (months / 12)
    terminal = values[:, -1]
    terminal_real = terminal / infl[-1]
    total = float(cum_contrib[-1])
    dd = max_drawdowns(twr_path)
    years = steps / 12
    cagr = twr_path[:, -1] ** (1 / years) - 1 if years > 0 else np.zeros_like(terminal)

    pct = np.percentile(values, PCTS, axis=0)
    pct_real = pct / infl
    yearly_idx = list(range(0, steps + 1, 12)) + ([steps] if steps % 12 else [])

    k = min(cfg.sample_paths, cfg.n_sims)
    worst5 = np.sort(terminal)[: max(1, int(0.05 * len(terminal)))]

    summary = {
        "total_contributed": total,
        "median_end": float(np.median(terminal)),
        "mean_end": float(terminal.mean()),
        "median_gain": float(np.median(terminal) - total),
        "median_multiple_of_contributions": float(np.median(terminal) / total) if total > 0 else None,
        "p5_end": float(np.percentile(terminal, 5)),
        "p10_end": float(np.percentile(terminal, 10)),
        "p25_end": float(np.percentile(terminal, 25)),
        "p75_end": float(np.percentile(terminal, 75)),
        "p90_end": float(np.percentile(terminal, 90)),
        "p95_end": float(np.percentile(terminal, 95)),
        "median_end_real": float(np.median(terminal_real)),
        "prob_below_contributions": float(np.mean(terminal < total)),
        "prob_goal": None if not cfg.goal else float(np.mean(terminal >= cfg.goal)),
        "cvar5_end": float(worst5.mean()),
        "median_annualized_twr": float(np.median(cagr)),
        "p10_annualized_twr": float(np.percentile(cagr, 10)),
        "p90_annualized_twr": float(np.percentile(cagr, 90)),
        "median_max_drawdown": float(np.median(dd)),
        "p90_max_drawdown": float(np.percentile(dd, 90)),
        "prob_drawdown_over_30": float(np.mean(dd > 0.30)),
        "n_sims": int(cfg.n_sims),
    }
    return {
        "months": months.tolist(),
        "contributions": cum_contrib.round(2).tolist(),
        "inflation_factor": infl.tolist(),
        "percentiles": {str(p): pct[i].round(2).tolist() for i, p in enumerate(PCTS)},
        "percentiles_real": {str(p): pct_real[i].round(2).tolist() for i, p in enumerate(PCTS)},
        "sample_paths": values[:k].round(2).tolist(),
        "terminal": terminal.tolist(),
        "terminal_real": terminal_real.tolist(),
        "max_drawdowns": dd.round(4).tolist(),
        "annualized_twr": cagr.round(5).tolist(),
        "yearly": [
            {"year": i / 12, "contributed": float(cum_contrib[i]),
             **{f"p{p}": float(pct[j, i]) for j, p in enumerate(PCTS)},
             "median_real": float(pct_real[PCTS.index(50), i])}
            for i in yearly_idx
        ],
        "summary": summary,
    }
