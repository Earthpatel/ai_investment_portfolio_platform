import numpy as np
import pandas as pd
import pytest

from app.engine import backtest as bt, optimize as opt, ml


def _prices(n=900, k=3, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2018-01-01", periods=n)
    r = rng.normal(0.0004, 0.01, (n, k))
    return pd.DataFrame(100 * np.exp(np.cumsum(r, 0)), index=idx, columns=list("ABC")[:k])


def test_optimizer_respects_constraints():
    mu = np.array([0.10, 0.08, 0.05])
    cov = np.diag([0.04, 0.02, 0.01])
    res = opt.optimize(mu, cov, rf=0.02, max_w=0.5, sectors=["T", "T", "H"], sector_cap=0.6)
    for k, p in res["portfolios"].items():
        if k == "equal_weight":
            continue  # reference portfolio, intentionally unconstrained
        w = np.array(p["weights"])
        assert w.sum() == pytest.approx(1, abs=1e-5)
        assert (w >= -1e-9).all() and (w <= 0.5 + 1e-6).all()
        assert w[0] + w[1] <= 0.6 + 1e-6


def test_min_variance_diagonal_is_inverse_variance():
    cov = np.diag([0.04, 0.01])
    w = np.array(opt.optimize(np.array([0.1, 0.1]), cov)["portfolios"]["min_variance"]["weights"])
    assert w == pytest.approx([0.2, 0.8], abs=1e-4)


def test_risk_parity_equal_risk_contributions():
    cov = np.array([[0.04, 0.006], [0.006, 0.01]])
    w = np.array(opt.optimize(np.array([0.1, 0.1]), cov)["portfolios"]["risk_parity"]["weights"])
    rc = w * (cov @ w)
    assert rc[0] == pytest.approx(rc[1], rel=1e-3)


def test_backtest_buy_and_hold_matches_manual_and_costs_apply():
    px = _prices()
    w = np.array([0.5, 0.3, 0.2])
    res = bt.backtest(px, w, None, "quarterly", 10_000, cost_bps=0)
    manual = 10_000 * (px.iloc[-1] / px.iloc[0] @ w)
    assert res["strategies"]["buy_and_hold"]["series"][-1][1] == pytest.approx(manual, rel=1e-6)
    res_c = bt.backtest(px, w, None, "quarterly", 10_000, cost_bps=50)
    assert res_c["strategies"]["rebalanced"]["trading"]["costs_paid"] > 0
    assert res_c["strategies"]["rebalanced"]["series"][-1][1] < res["strategies"]["rebalanced"]["series"][-1][1]


def test_backtest_minvar_uses_only_past_data():
    px = _prices()
    seen = []
    orig = bt._min_var_weights

    def spy(rets, max_w):
        seen.append(rets.index.max())
        return orig(rets, max_w)
    bt._min_var_weights = spy
    try:
        v, _ = bt.run_strategy(px, lambda i: bt._min_var_weights(px.pct_change().iloc[max(1, i - 100): i + 1], 1.0) if i > 0 else np.full(3, 1 / 3),
                               "quarterly", 10_000, 0)
    finally:
        bt._min_var_weights = orig
    reb = sorted(bt._rebalance_dates(px.index, "quarterly"))
    assert all(s <= r for s, r in zip(seen, reb))


def test_ml_walk_forward_has_embargo_and_no_overlap():
    dates = list(pd.date_range("2018-01-31", periods=60, freq="ME"))
    for train, test in ml.walk_forward_folds(dates):
        assert max(train) < min(test)
        gap = dates.index(min(test)) - dates.index(max(train))
        assert gap == ml.EMBARGO_MONTHS + 1


def test_ml_features_are_backward_looking():
    px = _prices(n=600, k=3)
    panel = ml.build_dataset(px, None)
    # changing FUTURE prices must not change features on an earlier date
    px2 = px.copy()
    px2.iloc[-40:] *= 1.5
    panel2 = ml.build_dataset(px2, None)
    cutoff = px.index[-70]
    a = panel[panel["date"] < cutoff].set_index(["date", "ticker"])[ml.FEATURES]
    b = panel2[panel2["date"] < cutoff].set_index(["date", "ticker"])[ml.FEATURES]
    pd.testing.assert_frame_equal(a, b.loc[a.index])
