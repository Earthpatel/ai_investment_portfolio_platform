# AI Investment Manager Portfolio Platform

A machine learning pipeline that analyses all 503 S&P 500 companies to generate
data-driven investment signals — built to demonstrate production-grade data
engineering and ML skills for Business Analytics roles.

---

## What it does

1. **Collects** daily price history, company fundamentals, and annual financials
   for every S&P 500 ticker via yfinance
2. **Engineers** technical indicators (returns, volatility, momentum, RSI, MACD)
   and fundamental features (P/E, margins, debt ratios) aligned by fiscal year
3. **Trains** a CatBoost classification model to predict buy / hold / sell signals
4. **Backtests** the strategy against the S&P 500 benchmark
5. **Visualises** portfolio performance, sector allocation, and risk metrics

---

## Project structure

```
investment_platform/
├── notebooks/
│   ├── 01_data_collection.ipynb       # Fetch & validate raw data
│   ├── 02_feature_engineering.ipynb   # Build ML-ready feature set
│   ├── 03_eda.ipynb                   # Exploratory data analysis
│   ├── 04_model_training.ipynb        # CatBoost model training
│   ├── 05_backtesting.ipynb           # Strategy vs benchmark
│   └── 06_dashboard.ipynb            # Interactive visualisations
├── src/
│   ├── __init__.py                    # Package entry point
│   └── data_collection.py            # Reusable pipeline module
├── data/
│   ├── raw/                           # Source CSVs (gitignored)
│   └── processed/                     # Parquet feature store (gitignored)
├── logs/                              # Pipeline run logs (gitignored)
├── requirements.txt
└── README.md
```

---

## Tech stack

| Layer | Tools |
|---|---|
| Data collection | yfinance, pandas, pyarrow |
| Feature engineering | pandas, numpy, scikit-learn |
| ML model | CatBoost, XGBoost, LightGBM |
| Visualisation | plotly, matplotlib |
| Environment | Python 3.13, Jupyter |

---

## Quickstart

**1. Clone and set up environment**
```bash
git clone https://github.com/Earthpatel/ai_investment_portfolio_platform.git
cd ai_investment_portfolio_platform
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**2. Fetch S&P 500 tickers**
```bash
python src/data_collection.py --refresh
```

**3. Run full data collection**
```bash
python src/data_collection.py
```

Or open `notebooks/01_data_collection.ipynb` and run all cells.

**4. Run notebooks in order**

Open Jupyter and run notebooks 01 → 06 in sequence. Each notebook
loads the outputs of the previous one via `src.data_collection.load_all()`.

---

## Key design decisions

**Three separate tables, no premature merge**
Price history, company info, and financials are stored as separate Parquet
files and only joined during feature engineering — avoiding the cartesian
product explosion that occurs when merging daily prices with annual financials
on ticker alone.

**Pinned date range**
`START_DATE = 2020-01-01` and `END_DATE = 2025-01-01` are pinned constants,
not floating windows. This ensures the model trains on identical data across
re-runs, making experiment results reproducible and comparable.

**Batched API fetching**
All 503 tickers are fetched in batches of 50 with 2-second pauses between
batches to respect yfinance rate limits. Failed tickers are logged and skipped
without stopping the pipeline — a ~99% success rate is expected and acceptable.

**Parquet over CSV**
Parquet preserves column types across read/write cycles, supports column
pruning (downstream notebooks load only the columns they need), and is roughly
10x faster and 5x smaller than equivalent CSV files at this scale.

**Versioned snapshots**
Every pipeline run saves a timestamped copy alongside the latest file
(e.g. `all_history_20260612_1429.parquet`), enabling rollback if a future
fetch introduces bad data.

---

## Connecting to downstream scripts

Every notebook and script imports data through a single entry point:

```python
from src.data_collection import load_all

data = load_all()
history    = data['history']     # Daily OHLCV — 498 tickers × ~1,250 rows
info       = data['info']        # Company metadata — 498 rows × 31 cols
financials = data['financials']  # Annual income statements — ~2,000 rows
```

---

## Pipeline order

```
data_collection  →  feature_engineering  →  model_training
      →  backtesting  →  portfolio_optimizer  →  dashboard
```

---

## Notes

- Data files are gitignored — run the collection pipeline locally to
  regenerate them
- A small number of tickers (~5) fail due to recent spinoffs or delistings;
  this is expected and does not affect model quality
- The `all_info` table captures fundamentals as a point-in-time snapshot.
  Time-varying financial ratios are derived from `all_financials` instead,
  which is correctly timestamped by fiscal year end