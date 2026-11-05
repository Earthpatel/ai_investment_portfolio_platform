# Monte Carlo Investment Lab

**If I invest a certain amount in specific stocks, ETFs or sectors, what might it be worth in the future, and what risks should I understand?**

An interactive investment research platform: build a portfolio from real tickers, then watch thousands of simulated futures unfold. Explore the distribution of outcomes, drawdowns and goal probabilities, and compare scenarios. Also includes portfolio optimization, honest walk-forward machine learning, historical backtests, crisis stress tests, and a Monty Hall lab that teaches the Monte Carlo idea.

> Simulations show possibilities under stated assumptions. They are not forecasts, guarantees, or investment advice.

| Layer | Stack |
|---|---|
| Frontend | React 19 + TypeScript, Vite, Tailwind CSS v4, Recharts, custom canvas fan chart |
| Backend | Python 3.11+, FastAPI, NumPy, pandas, SciPy, scikit-learn (+ LightGBM / CatBoost if installed) |
| Data | yfinance (adjusted daily prices), per-ticker Parquet cache, S&P 500 constituents with GICS sectors |
| Education | `frontend/public/monty-hall.html`: a self-contained single-page HTML/JS Monte Carlo (the original brief) |

---

## Quick start (macOS / Linux)

```bash
# 1. Backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
python scripts/update_data.py          # first time: S&P 500 list + prices (~5–10 min)
cd backend && uvicorn app.main:app --port 8000 &   # API on http://127.0.0.1:8000
cd ..

# 2. Frontend (Node 20+)
cd frontend && npm install && npm run dev            # http://localhost:5173
```

Or run both with `./run.sh`.

**Tests**

```bash
cd backend && pytest -q                 # 30 math/engine/API tests (synthetic data, offline)
python scripts/validate_real_data.py    # end-to-end checks on REAL prices (needs internet)
cd frontend && npm run build            # type-check + production build
```

**Offline development:** `MC_DEV_SYNTHETIC=1 uvicorn app.main:app` serves deterministic synthetic prices. Every response is flagged `synthetic: true` and the UI shows a warning banner. Synthetic data is never used unless you set this variable.

---

## What's inside

| Section | What it does |
|---|---|
| **Overview** | Workflow, presets (labeled as educational, not recommendations), data status |
| **Portfolio Builder** | Ticker search with GICS sector filters, weights (must total 100%), equal-weight button, concentration and ETF-overlap warnings, contributions (weekly/monthly/annual), horizon, method, calibration window, rebalancing, fees, inflation, dividend reinvestment, seed. Includes a data quality panel. |
| **Monte Carlo Simulator** | Animated fan chart (start/pause/resume/reset, speed slider, slow-motion, max speed), live-building histogram and convergence chart, results dashboard, goal explorer, year-by-year table, drawdown distribution, assumptions panel; CSV / PNG / report export |
| **Stock & Sector Explorer** | Price + SMA50/200, return distribution vs. normal curve, drawdown, RSI, MACD, rolling volatility, correlation and beta vs. SPY, sector-ETF comparison, sector scoreboard |
| **AI & Machine Learning** | Walk-forward evaluation of Ridge / Random Forest / gradient boosting (+ LightGBM, CatBoost) vs. baselines; IC, MAE/RMSE, cost-adjusted top-quintile strategy, leakage checks, shuffled-label sanity check. Gives an honest verdict. |
| **Portfolio Optimization** | Min-variance, max-Sharpe, risk parity, target volatility with per-asset and per-sector caps; efficient frontier, correlation heatmap, and bootstrap weight-stability analysis |
| **Backtesting** | Buy & hold vs. rebalanced vs. equal weight vs. walk-forward min-variance, with transaction costs and an SPY benchmark; survivorship-bias disclosure |
| **Risk Analytics** | One-variable what-if analysis, scenario comparison with common random numbers, historical crisis replays (2000, 2008, 2011, 2020, 2022) |
| **Learn Monte Carlo** | Monty Hall (manual play + live simulation), random walks, percentiles, correlation, simple/advanced explanations |

---

## Mathematical assumptions

**Return convention.** Asset returns are simulated as **monthly log returns** *r*. Each holding grows by `exp(r)`, so values can never go negative. Holdings drift between rebalances.

**Methods**

1. **Parametric.** Uses the mean vector and covariance of historical monthly log returns. The covariance gets Ledoit–Wolf shrinkage and a PSD repair (eigenvalue clipping), then is sampled with a Cholesky factor.
2. **Historical bootstrap.** Circular block bootstrap of *joint* monthly return vectors (default 6-month blocks). This preserves fat tails, cross-asset correlation and some autocorrelation, but it cannot produce events missing from the sample.
3. **Custom.** User-supplied annual *arithmetic* mean `m` and volatility `s`, combined with historical correlations. They are converted with the lognormal identities `b² = ln(1 + s²/(1+m)²)` and `a = ln(1+m) − b²/2`. Labeled as assumptions, not forecasts.

**Contributions.** Monthly steps: weekly contributions are applied as 52/12 per month, and annual contributions in the first (or last) month of each year. "Start" timing invests before that month's return; "end" timing invests after it.

**Prices** are adjusted closes (dividends and splits folded in), i.e. a total-return proxy. With dividend reinvestment off, a trailing dividend yield is paid out monthly as non-compounding cash.

**Fees** are deducted monthly at `(1 − fee)^(1/12)`. **Inflation-adjusted** values divide by `(1 + inflation)^(t/12)`.

**Metrics**
- Percentiles are taken across simulations at each month. The median ending value is the median of terminal wealth, *not* wealth compounded at a "median return".
- P(loss) = #(terminal < total contributed) / N.
- The annualized return is **time-weighted**, so it is independent of contribution timing.
- Drawdown is measured on the time-weighted index, so contributions don't hide losses.
- CVaR 5% = mean of the worst 5% of terminal values.

**Reproducibility.** Same seed + same inputs = identical results. Scenario comparisons reuse the seed (common random numbers).

## Known limitations

- History-calibrated simulations inherit the calibration window. A strong decade can overstate future returns, and a short window is noisy. Mean returns carry large estimation error.
- Correlations jump in crises. Neither parametric nor bootstrap simulation fully captures regime shifts.
- Taxes, bid/ask spreads and behavioral factors are ignored.
- Backtests use today's tickers (survivorship bias). The ML universe is today's S&P 500.
- The ML target is short-horizon relative return. Weak but positive ICs are normal, and the app disables ML-tilted assumptions unless out-of-sample skill is statistically meaningful.
- yfinance is an unofficial, free Yahoo Finance wrapper. For production, a licensed provider (Polygon, Tiingo, EOD Historical Data) can replace `app/data.py::_download` without touching the engines.

## Project layout

```
backend/app/
  main.py          FastAPI routes + request validation
  data.py          Data layer: cache → yfinance → local parquet; provenance on every series
  engine/          Pure numerical code (no web): simulate, optimize, backtest, analytics, ml
backend/tests/     Mathematical, financial and API tests
frontend/src/      React app (pages/, components/, lib/)
frontend/public/monty-hall.html   Standalone single-page Monty Hall simulation
scripts/           update_data.py (data refresh), validate_real_data.py (real-data QA)
legacy/            The original notebooks and modules (v1), kept for reference
```

## What changed from v1 (`legacy/`)

v1 pipeline (data collection → feature engineering → ML notebooks) was reviewed and:
- **Kept:** yfinance + Parquet storage, S&P 500 universe with GICS sectors, technical features (RSI, MACD, SMA distance, volatility, momentum), and the walk-forward ML idea.
- **Fixed:**
  - The master-dataset merge joined fundamentals on `Ticker` alone, duplicating every daily row once per fiscal year.
  - The ML walk-forward had no embargo between train and test.
  - A "regime" feature was computed from *future* returns (look-ahead leakage).
- **Added:** everything interactive (simulation, optimization, backtesting, stress tests, UI) plus tests.
