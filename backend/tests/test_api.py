"""End-to-end API tests on DEV-MODE synthetic data (labeled as such)."""
from fastapi.testclient import TestClient

from app.main import app

c = TestClient(app)
P = {"holdings": [{"ticker": "SPY", "weight": 0.6}, {"ticker": "AAPL", "weight": 0.4}]}


def test_simulate_endpoint_and_metrics_consistency():
    r = c.post("/api/simulate", json={**P, "n_sims": 300, "years": 5, "goal": 20000, "contribution": 100})
    assert r.status_code == 200, r.text
    d = r.json()
    import numpy as np
    t = np.array(d["terminal"])
    assert d["summary"]["median_end"] == np.median(t).round(2) or abs(d["summary"]["median_end"] - np.median(t)) < 0.02
    assert d["percentiles"]["50"][-1] == round(float(np.percentile(t, 50)), 2) or abs(d["percentiles"]["50"][-1] - np.median(t)) < 0.02
    assert d["synthetic"] is True
    assert d["summary"]["total_contributed"] == 10_000 + 100 * 60


def test_all_methods_and_compare():
    for m in ["parametric", "bootstrap", "custom"]:
        body = {**P, "method": m, "n_sims": 100}
        if m == "custom":
            body["holdings"] = [{**h, "custom_mu": 0.07, "custom_sigma": 0.15} for h in P["holdings"]]
        assert c.post("/api/simulate", json=body).status_code == 200
    r = c.post("/api/simulate/compare", json={"scenarios": [{**P, "n_sims": 100}, {"holdings": [{"ticker": "SPY", "weight": 1}], "n_sims": 100}]})
    assert r.status_code == 200 and len(r.json()["scenarios"]) == 2


def test_validation_rejects_bad_weights():
    r = c.post("/api/simulate", json={"holdings": [{"ticker": "SPY", "weight": 0.5}]})
    assert r.status_code == 422


def test_other_endpoints():
    assert c.get("/api/universe").status_code == 200
    assert c.get("/api/quality", params={"tickers": "SPY,AAPL"}).status_code == 200
    assert c.get("/api/asset/AAPL").status_code == 200
    assert c.post("/api/optimize", json=P).status_code == 200
    assert c.post("/api/backtest", json=P).status_code == 200
    assert c.post("/api/stress", json=P).status_code == 200
