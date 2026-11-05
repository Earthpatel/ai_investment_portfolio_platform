"""Machine-learning lab: can price-based features predict NEXT-MONTH RELATIVE returns?

Target (clearly defined):
    y = 21-trading-day forward log return of a stock MINUS the cross-sectional average
        on the same date ("did it beat the average stock over the next month?").

Design choices that prevent fooling ourselves:
  * Features use only trailing windows (no centered/forward windows).
  * One sample per stock per month-end -> forward windows don't overlap.
  * Walk-forward evaluation: expanding training window, 6-month test blocks, and a
    1-month EMBARGO gap so no training label overlaps the test period.
  * Baselines: zero prediction (for MAE/RMSE) and 12-1 momentum (a classic factor).
  * A shuffled-label sanity check should score ~0 IC; if it doesn't, something leaks.
  * Strategy evaluation charges transaction costs on turnover.
Original project issues fixed here: the old walk-forward split had no embargo and the
regime feature used FUTURE returns (look-ahead).
"""
from __future__ import annotations

import json
import threading
import time
import traceback
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from .. import config

FEATURES = ["ret_21", "ret_63", "ret_126", "mom_12_1", "vol_21", "vol_63", "rsi_14",
            "macd_hist", "dist_sma50", "dist_sma200", "drawdown_252", "volume_ratio"]
FWD = 21
EMBARGO_MONTHS = 1
TEST_BLOCK = 6
MIN_TRAIN_MONTHS = 24


def _rsi_frame(close: pd.DataFrame, period=14) -> pd.DataFrame:
    d = close.diff()
    gain = d.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    return 100 - 100 / (1 + gain / loss.replace(0, np.nan))


def build_dataset(close: pd.DataFrame, volume: pd.DataFrame | None) -> pd.DataFrame:
    """Long panel: one row per (month-end, ticker) with trailing features + forward target."""
    close = close.sort_index()
    logp = np.log(close)
    dr = logp.diff()
    f = {
        "ret_21": logp - logp.shift(21),
        "ret_63": logp - logp.shift(63),
        "ret_126": logp - logp.shift(126),
        "mom_12_1": logp.shift(21) - logp.shift(252),
        "vol_21": dr.rolling(21).std() * np.sqrt(252),
        "vol_63": dr.rolling(63).std() * np.sqrt(252),
        "rsi_14": _rsi_frame(close),
        "dist_sma50": close / close.rolling(50).mean() - 1,
        "dist_sma200": close / close.rolling(200).mean() - 1,
        "drawdown_252": close / close.rolling(252).max() - 1,
    }
    m = close.ewm(span=12, adjust=False, min_periods=26).mean() - close.ewm(span=26, adjust=False, min_periods=26).mean()
    f["macd_hist"] = (m - m.ewm(span=9, adjust=False, min_periods=9).mean()) / close
    if volume is not None and not volume.empty:
        vol = volume.reindex_like(close)
        f["volume_ratio"] = vol.rolling(5).mean() / vol.rolling(63).mean()
    else:
        f["volume_ratio"] = close * np.nan
    target = logp.shift(-FWD) - logp  # FUTURE return: label only, never a feature

    # month-end sampling: last trading day of each calendar month
    s = pd.Series(close.index, index=close.index)
    month_ends = pd.DatetimeIndex(s.groupby(pd.Grouper(freq="ME")).last().dropna())
    frames = []
    for name, df in f.items():
        frames.append(df.loc[month_ends].stack().rename(name))
    panel = pd.concat(frames, axis=1)
    panel["target_raw"] = target.loc[month_ends].stack()
    panel.index.names = ["date", "ticker"]
    panel = panel.reset_index()
    panel["volume_ratio"] = panel["volume_ratio"].fillna(1.0)
    panel = panel.dropna(subset=[c for c in FEATURES if c != "volume_ratio"])
    # Relative target: subtract the same-date cross-sectional mean
    panel["target"] = panel["target_raw"] - panel.groupby("date")["target_raw"].transform("mean")
    # Rank-transform features per date (robust to scale changes across regimes)
    for c in FEATURES:
        panel[c] = panel.groupby("date")[c].rank(pct=True)
    return panel


def _models():
    from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
    from sklearn.linear_model import Ridge
    m = {
        "ridge": ("Ridge regression", lambda: Ridge(alpha=10.0)),
        "random_forest": ("Random forest", lambda: RandomForestRegressor(n_estimators=150, max_depth=5, min_samples_leaf=100, n_jobs=-1, random_state=0)),
        "hist_gbm": ("Gradient boosting (sklearn HistGB)", lambda: HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=200, random_state=0)),
    }
    try:
        from catboost import CatBoostRegressor
        m["catboost"] = ("CatBoost", lambda: CatBoostRegressor(iterations=300, depth=4, learning_rate=0.05, verbose=0, random_seed=0))
    except Exception:
        pass
    try:
        from lightgbm import LGBMRegressor
        m["lightgbm"] = ("LightGBM", lambda: LGBMRegressor(n_estimators=250, max_depth=4, learning_rate=0.03, min_child_samples=200, verbose=-1, random_state=0))
    except Exception:
        pass
    return m


def walk_forward_folds(dates: list) -> list[tuple[list, list]]:
    folds = []
    i = MIN_TRAIN_MONTHS + EMBARGO_MONTHS
    while i < len(dates):
        train = dates[: i - EMBARGO_MONTHS]  # embargo: skip the month right before the test block
        test = dates[i: i + TEST_BLOCK]
        folds.append((train, test))
        i += TEST_BLOCK
    return folds


def _ic_by_date(df: pd.DataFrame, col: str) -> pd.Series:
    out = {}
    for d, g in df.groupby("date"):
        if len(g) >= 10 and g[col].nunique() > 1:
            out[d] = spearmanr(g[col], g["target"]).statistic
    return pd.Series(out, dtype=float)


def _strategy(df: pd.DataFrame, col: str, cost_bps: float) -> dict:
    """Each month buy the top 20% by prediction (equal weight); compare to the average stock."""
    excess, held_prev, turns = [], set(), []
    for d, g in df.sort_values("date").groupby("date"):
        k = max(1, int(len(g) * 0.2))
        top = g.nlargest(k, col)
        held = set(top["ticker"])
        turnover = 1.0 if not held_prev else len(held - held_prev) / k
        turns.append(turnover)
        gross = float(np.expm1(top["target_raw"]).mean() - np.expm1(g["target_raw"]).mean())
        excess.append(gross - turnover * 2 * cost_bps / 10_000)  # sell old + buy new
        held_prev = held
    e = np.array(excess)
    return {"months": len(e), "ann_excess_return": float(e.mean() * 12) if len(e) else None,
            "ann_excess_sharpe": float(e.mean() / e.std() * np.sqrt(12)) if len(e) > 2 and e.std() > 0 else None,
            "avg_turnover": float(np.mean(turns)) if turns else None,
            "cumulative": np.cumprod(1 + e).round(4).tolist()}


def train_and_evaluate(panel: pd.DataFrame, cost_bps: float = 10.0, progress=lambda p, m: None) -> dict:
    labeled = panel.dropna(subset=["target"])
    dates = sorted(labeled["date"].unique())
    folds = walk_forward_folds(dates)
    if not folds:
        raise ValueError(f"Need at least {MIN_TRAIN_MONTHS + EMBARGO_MONTHS + 1} months of labeled data; have {len(dates)}.")
    models = _models()
    oos = []
    leakage_ok = True
    fold_info = []
    total = len(folds) * (len(models) + 1)
    done = 0
    for fi, (tr_d, te_d) in enumerate(folds):
        tr = labeled[labeled["date"].isin(tr_d)]
        te = labeled[labeled["date"].isin(te_d)].copy()
        # leakage check: every training label must END before the test period starts
        last_train_label_end = pd.Timestamp(max(tr_d)) + pd.offsets.BDay(FWD)
        ok = last_train_label_end <= pd.Timestamp(min(te_d)) + pd.Timedelta(days=3)
        leakage_ok &= bool(ok)
        fold_info.append({"fold": fi + 1, "train_start": str(pd.Timestamp(min(tr_d)).date()),
                          "train_end": str(pd.Timestamp(max(tr_d)).date()),
                          "test_start": str(pd.Timestamp(min(te_d)).date()), "test_end": str(pd.Timestamp(max(te_d)).date()),
                          "train_rows": int(len(tr)), "test_rows": int(len(te)), "embargo_ok": bool(ok)})
        X, y = tr[FEATURES].to_numpy(), tr["target"].to_numpy()
        for key, (_, make) in models.items():
            model = make().fit(X, y)
            te[key] = model.predict(te[FEATURES].to_numpy())
            done += 1
            progress(done / total, f"Fold {fi + 1}/{len(folds)}: {key}")
        # sanity: shuffled labels should carry no signal
        rng = np.random.default_rng(fi)
        from sklearn.linear_model import Ridge
        te["shuffled_ridge"] = Ridge(alpha=10.0).fit(X, rng.permutation(y)).predict(te[FEATURES].to_numpy())
        te["momentum_baseline"] = te["mom_12_1"]
        te["zero_baseline"] = 0.0
        done += 1
        oos.append(te)
    oos_df = pd.concat(oos)

    results = {}
    labels = {**{k: v[0] for k, v in models.items()}, "momentum_baseline": "Baseline: 12-1 momentum rank",
              "zero_baseline": "Baseline: predict zero", "shuffled_ridge": "Sanity check: ridge on shuffled labels"}
    for key, label in labels.items():
        err = oos_df[key] - oos_df["target"]
        ic = _ic_by_date(oos_df, key) if key != "zero_baseline" else pd.Series(dtype=float)
        is_score_only = key == "momentum_baseline"  # a rank score, not a return forecast
        results[key] = {
            "label": label,
            "mae": None if is_score_only else float(err.abs().mean()),
            "rmse": None if is_score_only else float(np.sqrt((err ** 2).mean())),
            "ic_mean": float(ic.mean()) if len(ic) else None,
            "ic_std": float(ic.std()) if len(ic) > 1 else None,
            "ic_tstat": float(ic.mean() / ic.std() * np.sqrt(len(ic))) if len(ic) > 1 and ic.std() > 0 else None,
            "ic_series": [[str(pd.Timestamp(d).date()), round(float(v), 4)] for d, v in ic.items()],
            "hit_rate": None if key == "zero_baseline" or is_score_only else float(np.mean(np.sign(oos_df[key]) == np.sign(oos_df["target"]))),
            "strategy": None if key == "zero_baseline" else _strategy(oos_df, key, cost_bps),
        }

    candidates = [k for k in models]
    best = max(candidates, key=lambda k: results[k]["ic_mean"] or -9)
    b = results[best]
    mom = results["momentum_baseline"]["ic_mean"] or 0
    usable = bool((b["ic_tstat"] or 0) > 2 and (b["ic_mean"] or 0) > mom and (b["strategy"]["ann_excess_return"] or 0) > 0)
    verdict = (f"{b['label']} shows a statistically meaningful out-of-sample signal (IC {b['ic_mean']:.3f}, t={b['ic_tstat']:.1f}) "
               f"that beats momentum after costs. Still: treat it as one experimental input, not a forecast."
               if usable else
               f"Best model ({b['label']}) does NOT show reliable out-of-sample skill "
               f"(IC {b['ic_mean'] or 0:.3f}, t={b['ic_tstat'] or 0:.1f}; momentum baseline IC {mom:.3f}). "
               f"Its predictions should not drive investment decisions; ML scenario assumptions are disabled.")

    # Feature importance from a model fit on all labeled data
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.linear_model import Ridge
    Xall, yall = labeled[FEATURES].to_numpy(), labeled["target"].to_numpy()
    rf = RandomForestRegressor(n_estimators=150, max_depth=5, min_samples_leaf=100, n_jobs=-1, random_state=0).fit(Xall, yall)
    ridge = Ridge(alpha=10.0).fit(Xall, yall)

    # Latest predictions (features known today, target not yet known)
    best_model = models[best][1]().fit(Xall, yall)
    latest_date = panel["date"].max()
    latest = panel[panel["date"] == latest_date]
    preds = best_model.predict(latest[FEATURES].to_numpy()) if len(latest) else []
    latest_preds = {t: float(p) for t, p in zip(latest["ticker"], preds)}

    return {
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "target": "21-trading-day forward log return minus the cross-sectional mean (relative performance)",
        "universe_size": int(panel["ticker"].nunique()),
        "months": len(dates), "rows": int(len(labeled)),
        "features": FEATURES, "folds": fold_info, "leakage_checks_passed": bool(leakage_ok),
        "embargo_months": EMBARGO_MONTHS, "cost_bps": cost_bps,
        "models": results, "best_model": best, "usable": usable, "verdict": verdict,
        "feature_importance": {"random_forest": dict(zip(FEATURES, rf.feature_importances_.round(4).tolist())),
                               "ridge_coef": dict(zip(FEATURES, ridge.coef_.round(5).tolist()))},
        "latest_date": str(pd.Timestamp(latest_date).date()),
        "latest_predictions": latest_preds,
    }


# ---------------------------------------------------------------------------
# Background job (training must never block simulation requests)
# ---------------------------------------------------------------------------
class MLJob:
    def __init__(self):
        self.state = "idle"
        self.progress = 0.0
        self.message = ""
        self.started = None
        self._lock = threading.Lock()

    @property
    def results_path(self):
        return config.ML_DIR / "results.json"

    def results(self) -> dict | None:
        p = self.results_path
        if p.exists():
            return json.loads(p.read_text())
        return None

    def status(self) -> dict:
        return {"state": self.state, "progress": self.progress, "message": self.message, "started": self.started,
                "has_results": self.results_path.exists()}

    def start(self, loader, cost_bps: float) -> bool:
        with self._lock:
            if self.state == "running":
                return False
            self.state, self.progress, self.message = "running", 0.0, "Loading prices"
            self.started = time.time()
        threading.Thread(target=self._run, args=(loader, cost_bps), daemon=True).start()
        return True

    def _run(self, loader, cost_bps):
        try:
            close, volume, synthetic = loader()
            self.message = f"Building features for {close.shape[1]} tickers"
            panel = build_dataset(close, volume)

            def prog(p, m):
                self.progress, self.message = 0.05 + 0.9 * p, m
            res = train_and_evaluate(panel, cost_bps, prog)
            res["synthetic"] = synthetic
            config.ML_DIR.mkdir(parents=True, exist_ok=True)
            self.results_path.write_text(json.dumps(res))
            self.state, self.progress, self.message = "done", 1.0, "Finished"
        except Exception as exc:
            traceback.print_exc()
            self.state, self.message = "error", f"{type(exc).__name__}: {exc}"


JOB = MLJob()
