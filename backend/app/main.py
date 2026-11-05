"""FastAPI app — the kitchen's order window.

Run:  uvicorn app.main:app --reload --port 8000   (from the backend/ folder)
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Literal

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from . import config, data
from .engine import analytics, backtest as bt, ml, optimize as opt, simulate as sim

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = FastAPI(title="Monte Carlo Investment Lab API", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class Holding(BaseModel):
    ticker: str
    weight: float = Field(ge=0, le=1)
    custom_mu: float | None = None  # annual arithmetic return (custom method only)
    custom_sigma: float | None = Field(default=None, ge=0)


class PortfolioIn(BaseModel):
    holdings: list[Holding] = Field(min_length=1, max_length=config.MAX_ASSETS)

    @field_validator("holdings")
    @classmethod
    def _sum(cls, v):
        s = sum(h.weight for h in v)
        if abs(s - 1) > 0.005:
            raise ValueError(f"Weights must total 100% (got {s * 100:.1f}%).")
        tick = [h.ticker.upper() for h in v]
        if len(set(tick)) != len(tick):
            raise ValueError("Duplicate tickers in portfolio.")
        return v

    def tickers(self):
        return [h.ticker.upper().replace(".", "-") for h in self.holdings]

    def weights(self):
        w = np.array([h.weight for h in self.holdings], float)
        return w / w.sum()


class SimulateIn(PortfolioIn):
    initial: float = Field(10_000, ge=0, le=1e9)
    contribution: float = Field(0, ge=0, le=1e8)
    contribution_freq: Literal["none", "weekly", "monthly", "annual"] = "monthly"
    contribution_timing: Literal["start", "end"] = "start"
    years: int = Field(10, ge=1, le=config.MAX_YEARS)
    n_sims: int = Field(1000, ge=10, le=config.MAX_SIMS)
    method: Literal["parametric", "bootstrap", "custom"] = "parametric"
    seed: int = Field(42, ge=0, le=2**31 - 1)
    rebalance: Literal["never", "monthly", "quarterly", "semiannual", "annual"] = "annual"
    fee_annual: float = Field(0.0, ge=0, le=0.05)
    inflation: float = Field(0.025, ge=-0.02, le=0.2)
    drip: bool = True
    goal: float | None = Field(None, ge=0)
    window: Literal["1y", "3y", "5y", "10y", "15y", "20y", "max"] = "10y"
    block_months: int = Field(6, ge=1, le=36)
    stress_vol_mult: float = Field(1.0, ge=0.25, le=3)
    use_ml_tilt: bool = False


def _bundle(tickers: list[str]) -> data.PriceBundle:
    b = data.load_prices(tickers)
    missing = [t for t in tickers if t not in b.close.columns]
    if missing:
        raise HTTPException(422, f"No price data available for: {', '.join(missing)}. "
                                 "Check the ticker or your internet connection (yfinance).")
    return b


def _cal_key(tickers, window):
    return (tuple(tickers), window)


_CAL_CACHE: dict = {}


def _calibration(tickers: list[str], window: str):
    key = _cal_key(tickers, window)
    hit = _CAL_CACHE.get(key)
    if hit and time.time() - hit[0] < 3600:
        return hit[1]
    b = _bundle(tickers)
    rets, warnings = data.monthly_log_returns(b, tickers, window)
    cal = sim.calibrate(rets)
    out = (b, rets, cal, warnings)
    _CAL_CACHE[key] = (time.time(), out)
    return out


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {"ok": True, "dev_synthetic": config.DEV_SYNTHETIC, "network": config.ALLOW_NETWORK,
            "local_history": config.LOCAL_HISTORY.exists(), "version": app.version}


@app.get("/api/universe")
def universe():
    return {"assets": data.universe(), "sector_etfs": data.SECTOR_ETF, "etf_holdings": data.ETF_TOP_HOLDINGS,
            "dev_synthetic": config.DEV_SYNTHETIC}


@app.get("/api/quality")
def quality(tickers: str, window: str = "10y"):
    tl = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    b = data.load_prices(tl)
    rep = data.quality_report(b, tl, window)
    try:
        rets, warn = data.monthly_log_returns(b, [t for t in tl if t in b.close.columns], window)
        cal = sim.calibrate(rets)
        rep["calibration"] = {"months": len(rets), "start": str(rets.index[0].date()), "end": str(rets.index[-1].date()),
                              "warnings": warn, "assets": tl, **sim.annualize(cal.mu, cal.cov),
                              "correlation": np.corrcoef(rets.to_numpy().T).round(3).tolist() if len(tl) > 1 else [[1.0]]}
    except Exception as exc:
        rep["calibration"] = {"error": str(exc)}
    rep["synthetic"] = b.synthetic
    return rep


def _run_sim(req: SimulateIn, seed_override: int | None = None) -> dict:
    tickers, w = req.tickers(), req.weights()
    b, rets, cal, warnings = _calibration(tickers, req.window)
    notes = list(cal.notes)
    cfg = sim.SimConfig(weights=w, initial=req.initial, contribution=req.contribution,
                        contribution_freq=req.contribution_freq, contribution_timing=req.contribution_timing,
                        years=req.years, n_sims=req.n_sims, method=req.method,
                        seed=req.seed if seed_override is None else seed_override, rebalance=req.rebalance,
                        fee_annual=req.fee_annual, inflation=req.inflation, drip=req.drip, goal=req.goal,
                        block_months=req.block_months, stress_vol_mult=req.stress_vol_mult)
    used = cal
    assumption_label = {"parametric": "Historical estimates (parametric, correlated lognormal)",
                        "bootstrap": f"Resampled historical months (block bootstrap, {req.block_months}-month blocks)",
                        "custom": "YOUR assumptions (custom) — not a market forecast"}[req.method]
    if req.method == "custom" or req.use_ml_tilt:
        hist_ann = sim.annualize(cal.mu, cal.cov)
        mu_a = np.array([h.custom_mu if (req.method == "custom" and h.custom_mu is not None) else hist_ann["arithmetic_mean"][i]
                         for i, h in enumerate(req.holdings)])
        sig_a = np.array([h.custom_sigma if (req.method == "custom" and h.custom_sigma is not None) else hist_ann["volatility"][i]
                          for i, h in enumerate(req.holdings)])
        if req.use_ml_tilt:
            res = ml.JOB.results()
            if not res or not res.get("usable"):
                raise HTTPException(409, "ML assumptions are disabled: no trained model shows reliable out-of-sample skill.")
            preds = res["latest_predictions"]
            tilt = np.array([12 * preds.get(t, 0.0) * 0.5 for t in tickers])  # half-weight shrinkage
            mu_a = mu_a + tilt
            notes.append("EXPERIMENTAL: expected returns tilted by ML predictions (50% shrinkage). "
                         f"Tickers without a prediction: {[t for t in tickers if t not in preds] or 'none'}.")
            assumption_label = "EXPERIMENTAL ML-tilted assumptions"
            if cfg.method == "bootstrap":
                cfg.method = "parametric"
        sd = np.sqrt(np.diag(cal.cov))
        corr = cal.cov / np.outer(sd, sd) if np.all(sd > 0) else np.eye(len(w))
        mu_m, cov_m = sim._custom_params(mu_a, sig_a, corr)
        used = sim.Calibration(mu=mu_m, cov=cov_m, hist=cal.hist, notes=notes)
        if cfg.method == "custom":
            cfg.method = "parametric"  # same generator, user's parameters
    dy = data.dividend_yields(b, tickers) if not req.drip else None
    t0 = time.perf_counter()
    out = sim.run(cfg, used, dy)
    out["elapsed_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    out["assumptions"] = {"label": assumption_label, "method": req.method, "tickers": tickers, "weights": w.tolist(),
                          **sim.annualize(used.mu, used.cov), "notes": notes, "warnings": warnings,
                          "dividend_yields": dy.tolist() if dy is not None else None,
                          "calibration_start": str(rets.index[0].date()), "calibration_end": str(rets.index[-1].date()),
                          "calibration_months": len(rets)}
    out["data"] = data.info_dict(b)
    out["synthetic"] = b.synthetic
    out["request_hash"] = hashlib.sha256(json.dumps(req.model_dump(), sort_keys=True).encode()).hexdigest()[:12]
    return out


@app.post("/api/simulate")
def simulate(req: SimulateIn):
    try:
        return _run_sim(req)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


class CompareIn(BaseModel):
    scenarios: list[SimulateIn] = Field(min_length=2, max_length=4)
    names: list[str] | None = None


@app.post("/api/simulate/compare")
def compare(req: CompareIn):
    """Same seed for every scenario = common random numbers (fairer comparisons)."""
    seed = req.scenarios[0].seed
    out = []
    for i, s in enumerate(req.scenarios):
        try:
            r = _run_sim(s, seed_override=seed)
        except ValueError as exc:
            raise HTTPException(422, f"Scenario {i + 1}: {exc}")
        out.append({"name": (req.names or [])[i] if req.names and i < len(req.names) else f"Scenario {chr(65 + i)}",
                    "summary": r["summary"], "percentiles": r["percentiles"], "terminal": r["terminal"],
                    "months": r["months"], "contributions": r["contributions"], "assumptions": r["assumptions"]})
    return {"scenarios": out, "seed": seed}


class StressIn(PortfolioIn):
    initial: float = 10_000


@app.post("/api/stress")
def stress(req: StressIn):
    tickers = req.tickers()
    b = _bundle(tickers + [data.BENCHMARK])
    proxy = b.close[data.BENCHMARK] if data.BENCHMARK in b.close else None
    return {"crises": analytics.stress_tests(b.close[tickers], req.weights(), proxy, req.initial),
            "note": "Historical replays of real crisis windows on today's weights (buy & hold). Not a prediction that "
                    "an identical event will recur. Assets that did not exist yet use SPY as a labeled proxy.",
            "synthetic": b.synthetic}


@app.get("/api/asset/{ticker}")
def asset(ticker: str, period: str = Query("5y")):
    t = ticker.upper().replace(".", "-")
    m = data.meta(t)
    sector_etf = data.SECTOR_ETF.get(m.get("sector", ""))
    want = [t, data.BENCHMARK] + ([sector_etf] if sector_etf and sector_etf != t else [])
    b = data.load_prices(want)
    if t not in b.close.columns:
        raise HTTPException(404, f"No price data for {t}.")
    market = b.close[data.BENCHMARK] if data.BENCHMARK in b.close.columns and t != data.BENCHMARK else None
    rep = analytics.asset_report(b.close[t], b.volume.get(t), market, period)
    rep["meta"] = m
    rep["data"] = b.info[t].__dict__
    comps = {}
    for c in [x for x in (data.BENCHMARK, sector_etf) if x and x != t and x in b.close.columns]:
        s = b.close[c].dropna()
        start = rep["series"][0]["date"]
        s = s[s.index >= start]
        tr = b.close[t].dropna()
        tr = tr[tr.index >= start]
        if len(s) > 5:
            comps[c] = {"name": data.meta(c)["name"], "total_return": float(s.iloc[-1] / s.iloc[0] - 1),
                        "series": [[str(d.date()), round(float(v / s.iloc[0] * tr.iloc[0]), 4)]
                                   for d, v in s.iloc[:: max(1, len(s) // 300)].items()]}
    rep["comparisons"] = comps
    rep["synthetic"] = b.synthetic
    return rep


class OptimizeIn(PortfolioIn):
    window: str = "5y"
    rf: float = Field(0.03, ge=0, le=0.2)
    max_weight: float = Field(1.0, gt=0, le=1)
    sector_cap: float | None = Field(None, gt=0, le=1)
    target_vol: float | None = Field(None, gt=0, le=1)


@app.post("/api/optimize")
def optimize(req: OptimizeIn):
    tickers = req.tickers()
    if len(tickers) < 2:
        raise HTTPException(422, "Optimization needs at least two assets.")
    b, rets, cal, warnings = _calibration(tickers, req.window)
    mu, cov = opt.estimates(rets)
    sectors = [data.meta(t).get("sector", "Unknown") for t in tickers]
    res = opt.optimize(mu, cov, req.rf, req.max_weight, sectors, req.sector_cap, req.target_vol)
    res["portfolios"]["current"] = opt._stats(req.weights(), mu, cov, req.rf)
    sd = np.sqrt(np.diag(cov))
    return {**res, "tickers": tickers, "sectors": sectors,
            "frontier": opt.frontier(mu, cov, req.max_weight, sectors, req.sector_cap, rf=req.rf),
            "random": opt.random_portfolios(mu, cov, rf=req.rf),
            "assets": [{"ticker": t, "expected_return": float(mu[i]), "volatility": float(sd[i])} for i, t in enumerate(tickers)],
            "correlation": (cov / np.outer(sd, sd)).round(3).tolist(),
            "sensitivity": opt.sensitivity(rets, req.rf, req.max_weight, sectors, req.sector_cap),
            "warnings": warnings, "window": req.window,
            "period": [str(rets.index[0].date()), str(rets.index[-1].date())], "synthetic": b.synthetic}


class BacktestIn(PortfolioIn):
    start: str | None = None
    rebalance: Literal["never", "monthly", "quarterly", "semiannual", "annual"] = "quarterly"
    initial: float = Field(10_000, gt=0)
    cost_bps: float = Field(5, ge=0, le=200)
    rf: float = Field(0.03, ge=0, le=0.2)
    max_weight: float = Field(0.4, gt=0, le=1)


@app.post("/api/backtest")
def backtest(req: BacktestIn):
    tickers = req.tickers()
    b = _bundle(tickers + [data.BENCHMARK])
    px = b.close[tickers]
    if req.start:
        px = px[px.index >= pd.Timestamp(req.start)]
    try:
        res = bt.backtest(px, req.weights(), b.close.get(data.BENCHMARK), req.rebalance, req.initial,
                          req.cost_bps, req.rf, max_w=req.max_weight)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    res["synthetic"] = b.synthetic
    res["data"] = data.info_dict(b)
    return res


class TrainIn(BaseModel):
    cost_bps: float = Field(10, ge=0, le=100)
    max_tickers: int = Field(500, ge=20, le=600)


def _ml_loader(max_tickers: int):
    def load():
        if config.DEV_SYNTHETIC:
            ticks = [a["ticker"] for a in data.universe() if a["type"] == "Stock"][: min(max_tickers, 80)]
            b = data.load_prices(ticks)
            return b.close, b.volume, True
        df = data._local_history()
        if df is None:
            raise RuntimeError("ML training uses the local S&P 500 history (data/processed/all_history.parquet). "
                               "Run `python scripts/update_data.py` first.")
        df = df.copy()
        df["Date"] = pd.to_datetime(df["Date"], utc=True).dt.tz_convert(None).dt.normalize()
        keep = df["Ticker"].drop_duplicates().iloc[:max_tickers]
        df = df[df["Ticker"].isin(keep)].drop_duplicates(["Date", "Ticker"])
        close = df.pivot(index="Date", columns="Ticker", values="Close").sort_index()
        vol = df.pivot(index="Date", columns="Ticker", values="Volume").sort_index() if "Volume" in df else None
        return close, vol, False
    return load


@app.post("/api/ml/train")
def ml_train(req: TrainIn):
    started = ml.JOB.start(_ml_loader(req.max_tickers), req.cost_bps)
    return {"started": started, **ml.JOB.status()}


@app.get("/api/ml/status")
def ml_status():
    return ml.JOB.status()


@app.get("/api/ml/results")
def ml_results():
    r = ml.JOB.results()
    if r is None:
        raise HTTPException(404, "No trained models yet. Start training first.")
    r = dict(r)
    r["latest_predictions_count"] = len(r.get("latest_predictions", {}))
    r.pop("latest_predictions", None)
    return r


@app.get("/api/ml/predictions")
def ml_predictions(tickers: str):
    r = ml.JOB.results()
    if r is None:
        raise HTTPException(404, "No trained models yet.")
    tl = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    p = r.get("latest_predictions", {})
    allp = np.array(list(p.values())) if p else np.array([0.0])
    return {"usable": r["usable"], "date": r["latest_date"], "best_model": r["best_model"],
            "predictions": {t: ({"pred_rel_21d": p[t], "percentile": float((allp < p[t]).mean())} if t in p else None) for t in tl}}
