"""End-to-end check on REAL market data (run on a machine with internet + your data).

Runs the simulator, optimizer, backtester and stress tests through the real API code
path on real prices, and cross-checks the simulator against independent calculations:
  1. parametric median vs. the analytic lognormal median
  2. bootstrap-simulated mean annual return vs. the historical sample mean
  3. backtest buy-and-hold vs. a hand-computed price ratio
Prints PASS/FAIL per check. Usage:  python scripts/validate_real_data.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.pop("MC_DEV_SYNTHETIC", None)

import numpy as np  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import data  # noqa: E402
from app.engine import simulate as sim  # noqa: E402
from app.main import app  # noqa: E402

c = TestClient(app)
ok = True


def check(name, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")


P = {"holdings": [{"ticker": "SPY", "weight": 0.5}, {"ticker": "AAPL", "weight": 0.25}, {"ticker": "MSFT", "weight": 0.25}]}

print("== Data sources ==")
b = data.load_prices(["SPY", "AAPL", "MSFT", "JPM", "XOM"])
for t, i in b.info.items():
    print(f"  {t:5s} {i.source:34s} {i.first_date} → {i.last_date}  ({i.observations} obs)  synthetic={i.is_synthetic}")
check("no synthetic data in use", not b.synthetic)

print("\n== Simulator on real prices ==")
r = c.post("/api/simulate", json={**P, "n_sims": 5000, "years": 10, "contribution": 500, "goal": 150000, "window": "10y"})
check("simulate 200", r.status_code == 200, r.text[:200] if r.status_code != 200 else "")
d = r.json()
s = d["summary"]
print(f"  calibration {d['assumptions']['calibration_start']} → {d['assumptions']['calibration_end']}; "
      f"median end ${s['median_end']:,.0f}; p10 ${s['p10_end']:,.0f}; p90 ${s['p90_end']:,.0f}; "
      f"P(<contrib) {s['prob_below_contributions']:.1%}; P(goal) {s['prob_goal']:.1%}; {d['elapsed_ms']} ms")
t = np.array(d["terminal"])
check("median matches terminal array", abs(np.median(t) - s["median_end"]) < 0.01)

# 1) analytic check: single asset, no contributions, no rebalancing -> lognormal median
bsp = data.load_prices(["SPY"])
rets, _ = data.monthly_log_returns(bsp, ["SPY"], "10y")
cal = sim.calibrate(rets)
cfg = sim.SimConfig(weights=np.array([1.0]), initial=10_000, contribution=0, years=10, n_sims=40_000, seed=1, rebalance="never")
out = sim.run(cfg, cal)
analytic = 10_000 * np.exp(cal.mu[0] * 120)
check("parametric median ≈ analytic lognormal median", abs(out["summary"]["median_end"] / analytic - 1) < 0.02,
      f"(sim {out['summary']['median_end']:,.0f} vs analytic {analytic:,.0f})")

# 2) bootstrap mean monthly log return ≈ historical mean
cfg_b = sim.SimConfig(weights=np.array([1.0]), initial=10_000, years=10, n_sims=20_000, seed=2, method="bootstrap", rebalance="never")
outb = sim.run(cfg_b, cal)
sim_mu = np.mean(np.log(np.array(outb["terminal"]) / 10_000)) / 120
check("bootstrap mean log return ≈ historical mean", abs(sim_mu - cal.mu[0]) < 0.0008,
      f"(sim {sim_mu * 12:.2%}/yr vs hist {cal.mu[0] * 12:.2%}/yr)")

for m in ["bootstrap", "custom"]:
    body = {**P, "method": m, "n_sims": 1000}
    if m == "custom":
        body["holdings"] = [{**h, "custom_mu": 0.07, "custom_sigma": 0.16} for h in P["holdings"]]
    check(f"method {m} runs", c.post("/api/simulate", json=body).status_code == 200)

print("\n== Optimizer / backtest / stress / explorer ==")
check("optimize", c.post("/api/optimize", json={**P, "max_weight": 0.6}).status_code == 200)
bt = c.post("/api/backtest", json={**P, "start": "2016-01-01", "cost_bps": 0})
check("backtest", bt.status_code == 200)
if bt.status_code == 200:
    j = bt.json()
    px = data.load_prices(["SPY", "AAPL", "MSFT"]).close[["SPY", "AAPL", "MSFT"]].dropna()
    px = px[px.index >= "2016-01-01"]
    manual = 10_000 * float((px.iloc[-1] / px.iloc[0]) @ np.array([0.5, 0.25, 0.25]))
    got = j["strategies"]["buy_and_hold"]["series"][-1][1]
    check("buy & hold equals hand calculation", abs(got / manual - 1) < 1e-6, f"({got:,.2f} vs {manual:,.2f})")
    mv, ew = j["strategies"]["min_variance"]["metrics"], j["strategies"]["equal_weight"]["metrics"]
    check("min-variance differs from equal weight", abs(mv["volatility"] - ew["volatility"]) > 1e-4,
          f"(vol {mv['volatility']:.2%} vs {ew['volatility']:.2%})")
    for k, v in j["strategies"].items():
        print(f"  {v['label']:45s} CAGR {v['metrics']['cagr']:.2%}  vol {v['metrics']['volatility']:.2%}  maxDD {v['metrics']['max_drawdown']:.2%}")
st = c.post("/api/stress", json=P)
check("stress tests", st.status_code == 200)
if st.status_code == 200:
    for cr in st.json()["crises"]:
        if cr["available"]:
            print(f"  {cr['label']:35s} return {cr['total_return']:.1%}  worst fall {cr['max_drawdown']:.1%}  proxied={cr['proxied']}")
check("explorer", c.get("/api/asset/NVDA?period=5y").status_code == 200)

print("\n== Machine learning on the real S&P 500 history ==")
if data._local_history() is None:
    print("  skipped: data/processed/all_history.parquet not found")
else:
    import time
    from app.engine import ml
    from app.main import _ml_loader
    close, vol, synth = _ml_loader(500)()
    t0 = time.time()
    panel = ml.build_dataset(close, vol)
    res = ml.train_and_evaluate(panel)
    print(f"  {res['universe_size']} stocks, {res['months']} months, {res['rows']:,} samples, {len(res['folds'])} folds, {time.time() - t0:.0f}s")
    for k, m in res["models"].items():
        ic = m["ic_mean"]
        ex = (m["strategy"] or {}).get("ann_excess_return")
        print(f"  {m['label']:42s} IC {'   n/a' if ic is None else f'{ic:+.3f}'}  t {m['ic_tstat'] or 0:+.1f}  top-20% excess/yr {'n/a' if ex is None else f'{ex:+.1%}'}")
    print("  VERDICT:", res["verdict"])
    check("ML leakage checks", res["leakage_checks_passed"])
    check("shuffled-label sanity IC ~ 0", abs(res["models"]["shuffled_ridge"]["ic_mean"] or 0) < 0.03)
    res["synthetic"] = False
    from app import config
    import json
    config.ML_DIR.mkdir(parents=True, exist_ok=True)
    (config.ML_DIR / "results.json").write_text(json.dumps(res))
    print("  saved results for the AI & ML page")

print("\nALL CHECKS PASSED" if ok else "\nSOME CHECKS FAILED")
sys.exit(0 if ok else 1)
