"""Mathematical correctness tests for the Monte Carlo engine."""
import numpy as np
import pandas as pd
import pytest

from app.engine import simulate as sim


def cal_from(mu_a, sig_a, corr=None):
    mu_a, sig_a = np.atleast_1d(mu_a).astype(float), np.atleast_1d(sig_a).astype(float)
    corr = np.eye(len(mu_a)) if corr is None else np.asarray(corr)
    mu, cov = sim._custom_params(mu_a, sig_a, corr)
    return sim.Calibration(mu=mu, cov=cov, hist=None)


def cfg(**kw):
    base = dict(weights=np.array([1.0]), initial=10_000, contribution=0, years=10, n_sims=500,
                inflation=0.0, rebalance="never", sample_paths=5)
    base.update(kw)
    return sim.SimConfig(**base)


def test_zero_return_grows_only_by_contributions():
    out = sim.run(cfg(contribution=100, contribution_freq="monthly"), cal_from(0.0, 0.0))
    total = 10_000 + 100 * 120
    assert np.allclose(out["terminal"], total)
    assert out["summary"]["total_contributed"] == pytest.approx(total)
    assert out["summary"]["prob_below_contributions"] == 0.0


def test_zero_volatility_is_deterministic_and_compounds():
    out = sim.run(cfg(), cal_from(0.07, 0.0))
    t = np.array(out["terminal"])
    assert t.std() < 1e-6
    assert t[0] == pytest.approx(10_000 * 1.07 ** 10, rel=1e-6)


def test_contributions_compound_correctly_start_vs_end():
    c = cal_from(0.12, 0.0)
    start = sim.run(cfg(initial=0, contribution=100, contribution_freq="monthly", contribution_timing="start", years=1), c)
    end = sim.run(cfg(initial=0, contribution=100, contribution_freq="monthly", contribution_timing="end", years=1), c)
    g = 1.12 ** (1 / 12)
    exp_start = sum(100 * g ** (12 - k) for k in range(12))
    exp_end = sum(100 * g ** (11 - k) for k in range(12))
    assert start["terminal"][0] == pytest.approx(exp_start, rel=1e-9)
    assert end["terminal"][0] == pytest.approx(exp_end, rel=1e-9)


def test_weekly_and_annual_contributions():
    c = cal_from(0.0, 0.0)
    wk = sim.run(cfg(initial=0, contribution=10, contribution_freq="weekly", years=2), c)
    yr = sim.run(cfg(initial=0, contribution=1000, contribution_freq="annual", years=3), c)
    assert wk["terminal"][0] == pytest.approx(10 * 52 * 2)
    assert yr["terminal"][0] == pytest.approx(3000)


def test_zero_initial_investment_works():
    out = sim.run(cfg(initial=0, contribution=50), cal_from(0.07, 0.15))
    assert np.all(np.isfinite(out["terminal"]))
    assert out["summary"]["median_end"] > 0


def test_fixed_seed_reproduces_results():
    a = sim.run(cfg(seed=7), cal_from(0.08, 0.2))
    b = sim.run(cfg(seed=7), cal_from(0.08, 0.2))
    c = sim.run(cfg(seed=8), cal_from(0.08, 0.2))
    assert a["terminal"] == b["terminal"]
    assert a["terminal"] != c["terminal"]


def test_values_never_negative_even_with_extreme_volatility():
    out = sim.run(cfg(n_sims=2000), cal_from(0.0, 1.5))
    assert min(out["terminal"]) > 0


def test_lognormal_parameters_match_requested_mean_and_vol():
    rng_cfg = cfg(years=1, n_sims=200_000, seed=1)
    out = sim.run(rng_cfg, cal_from(0.10, 0.20))
    g = np.array(out["terminal"]) / 10_000
    assert g.mean() == pytest.approx(1.10, abs=0.003)
    assert g.std() == pytest.approx(0.20, abs=0.003)


def test_percentiles_and_loss_probability_denominator():
    out = sim.run(cfg(n_sims=1000), cal_from(0.05, 0.3))
    t = np.array(out["terminal"])
    s = out["summary"]
    assert s["median_end"] == pytest.approx(np.median(t))
    assert s["p10_end"] == pytest.approx(np.percentile(t, 10))
    assert s["prob_below_contributions"] == pytest.approx((t < 10_000).sum() / len(t))
    p = out["percentiles"]
    assert all(p["10"][i] <= p["50"][i] <= p["90"][i] for i in range(len(p["50"])))


def test_inflation_adjustment_consistent():
    out = sim.run(cfg(inflation=0.03), cal_from(0.07, 0.15))
    real = np.array(out["terminal_real"])
    assert np.allclose(real, np.array(out["terminal"]) / 1.03 ** 10, rtol=1e-6)


def test_rebalancing_restores_target_weights():
    # Two assets with very different deterministic growth: annual rebalancing must
    # equal compounding the weighted arithmetic return each year.
    c = cal_from([0.20, 0.0], [0.0, 0.0])
    w = np.array([0.5, 0.5])
    reb = sim.run(cfg(weights=w, rebalance="annual", years=5), c)
    never = sim.run(cfg(weights=w, rebalance="never", years=5), c)
    assert reb["terminal"][0] == pytest.approx(10_000 * 1.10 ** 5, rel=1e-9)
    assert never["terminal"][0] == pytest.approx(5_000 * 1.2 ** 5 + 5_000, rel=1e-9)


def test_weights_validation():
    with pytest.raises(ValueError):
        sim.run(cfg(weights=np.array([0.6, 0.6])), cal_from([0.05, 0.05], [0.1, 0.1]))


def test_fees_reduce_value_exactly():
    out = sim.run(cfg(fee_annual=0.01), cal_from(0.0, 0.0))
    assert out["terminal"][0] == pytest.approx(10_000 * 0.99 ** 10, rel=1e-9)


def test_dividends_not_reinvested_are_kept_as_cash():
    c = cal_from(0.0, 0.0)
    drip = sim.run(cfg(drip=True), c, np.array([0.03]))
    nodrip = sim.run(cfg(drip=False), c, np.array([0.03]))
    # total-return 0%: with DRIP off, wealth = shrinking holdings + cash; total stays the same
    assert drip["terminal"][0] == pytest.approx(10_000)
    assert nodrip["terminal"][0] == pytest.approx(10_000, rel=1e-9)


def test_correlated_assets_preserve_correlation():
    corr = np.array([[1, 0.8], [0.8, 1]])
    c = cal_from([0.08, 0.08], [0.2, 0.2], corr)
    rng = np.random.default_rng(0)
    conf = cfg(weights=np.array([0.5, 0.5]), n_sims=50_000, years=1)
    draws = next(sim._random_returns(conf, c, rng, 1))
    assert np.corrcoef(draws.T)[0, 1] == pytest.approx(0.8, abs=0.01)


def test_bootstrap_only_uses_historical_values():
    hist = np.array([[0.01, 0.02], [-0.03, 0.00], [0.02, -0.01], [0.00, 0.03]])
    c = sim.Calibration(mu=hist.mean(0), cov=np.cov(hist.T), hist=hist)
    conf = cfg(weights=np.array([0.5, 0.5]), method="bootstrap", block_months=2, n_sims=100, years=1)
    rows = {tuple(r) for r in hist}
    for r in sim._random_returns(conf, c, np.random.default_rng(1), 12):
        assert all(tuple(x) in rows for x in r)  # joint rows kept together


def test_nearest_psd_fixes_indefinite_matrix():
    bad = np.array([[1, 0.99, 0.0], [0.99, 1, 0.99], [0.0, 0.99, 1]])
    fixed = sim.nearest_psd(bad)
    np.linalg.cholesky(fixed)


def test_drawdown_calculation():
    idx = np.array([[1, 1.2, 0.9, 1.3, 0.65]])
    assert sim.max_drawdowns(idx)[0] == pytest.approx(0.5)


def test_parametric_matches_analytic_median():
    # median of lognormal terminal = exp(n * mu_m) with no contributions
    c = cal_from(0.08, 0.18)
    out = sim.run(cfg(n_sims=40_000, years=10, seed=3), c)
    analytic = 10_000 * np.exp(c.mu[0] * 120)
    assert out["summary"]["median_end"] == pytest.approx(analytic, rel=0.02)
