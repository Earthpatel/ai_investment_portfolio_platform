"""
src/feature_engineering.py
==========================
AI Investment Manager Platform — Feature Engineering Pipeline

Transforms raw Parquet tables from data_collection.py into a single
ML-ready feature store saved as data/processed/features.parquet.

HOW OTHER SCRIPTS CONNECT TO THIS FILE
---------------------------------------
Every downstream script imports from this module like so:

    from src.feature_engineering import (
        load_features,          # most scripts use this
        build_features,         # call to rebuild from scratch
        FEATURES_FILE,
        FEATURE_COLS,
        TARGET_COL,
        CAT_COLS,
    )

Pipeline order:
    data_collection.py          (produces history / info / financials parquet)
        down
    feature_engineering.py      YOU ARE HERE
        down
    model_training.py           (imports load_features)
        down
    backtesting.py              (imports load_features + model)
        down
    portfolio_optimizer.py      (imports backtest results)
        down
    dashboard.py                (imports everything)

WHAT THIS MODULE BUILDS
------------------------
| Category       | Features                                               |
|----------------|--------------------------------------------------------|
| Returns        | daily, 5d, 21d, 63d, 126d rolling returns              |
| Volatility     | 21d, 63d annualised rolling std of daily returns       |
| Momentum       | RSI-14, MACD line, MACD signal, MACD histogram         |
| Price struct   | Bollinger band position/width, 52-week position,       |
|                | price vs SMA50, price vs SMA200                        |
| Volume         | volume ratio vs 20d average                            |
| Fundamentals   | revenue growth, net income growth, gross margin,       |
|                | operating margin (fiscal-year aligned via merge_asof)  |
| Categorical    | sector, industry                                       |
| Target         | forward 21d return bucketed into buy/hold/sell         |

NO DATA LEAKAGE GUARANTEE
--------------------------
- All rolling features use only past data (rolling() looks backward).
- Financials joined with merge_asof(..., direction='backward') so each
  price row only sees reports already published on that date.
- Target uses future prices intentionally -- features never do.
"""

import sys
import warnings
import logging
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Optional

# Project root on path -- fixes ModuleNotFoundError when running directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data_collection import (
    load_all,
    get_logger,
    PROCESSED_DIR,
    LOGS_DIR,
)

warnings.filterwarnings("ignore")


# ==============================================================================
# CONSTANTS -- imported by downstream scripts
# ==============================================================================

# Output file -- loaded by model_training.py, backtesting.py, dashboard.py
FEATURES_FILE = PROCESSED_DIR / "features.parquet"

# Target definition
FORWARD_DAYS = 21    # predict 1-month ahead return
N_QUANTILES  = 3     # labels: -1 (sell), 0 (hold), 1 (buy)
TARGET_COL   = "target"

# Rolling window sizes -- change here to affect all features globally
VOL_SHORT     = 21
VOL_LONG      = 63
RSI_PERIOD    = 14
MACD_FAST     = 12
MACD_SLOW     = 26
MACD_SIGNAL   = 9
BB_WINDOW     = 20
BB_STD        = 2
VOLUME_WINDOW = 20

# Categorical columns -- passed to CatBoost as cat_features in model_training.py
CAT_COLS = ["sector", "industry"]

# Populated after build_features() runs -- imported by model_training.py
FEATURE_COLS: list[str] = []

# Raw financial columns to pull from all_financials.parquet
DESIRED_FIN_COLS = [
    "Ticker", "FiscalYearEnd",
    "Total Revenue", "Net Income", "Gross Profit",
    "Operating Income", "EBITDA",
]

# Columns that are metadata, not ML features
NON_FEATURE_COLS = {
    "Ticker", "Date", "Open", "High", "Low", "Close", "Volume",
    "forward_return", "FiscalYearEnd", "target",
    "Total Revenue", "Net Income", "Gross Profit",
    "Operating Income", "EBITDA",
}


# ==============================================================================
# LOGGING
# ==============================================================================

logger = get_logger(__name__)


# ==============================================================================
# FEATURE FUNCTIONS -- private, one per feature category
# Each accepts a single-ticker DataFrame sorted by Date.
# Rolling operations look backward only -- no leakage.
# ==============================================================================

def _add_return_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add rolling return features.
    pct_change() always looks backward -- no leakage.

    Features added
    --------------
    daily_return, return_5d, return_21d, return_63d, return_126d
    """
    df = df.copy()
    df["daily_return"] = df["Close"].pct_change()
    for window in [5, 21, 63, 126]:
        df[f"return_{window}d"] = df["Close"].pct_change(window)
    return df


def _add_volatility_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add annualised rolling volatility.
    Annualised by multiplying by sqrt(252) -- trading days per year.

    Features added
    --------------
    volatility_21d, volatility_63d
    """
    df = df.copy()
    for window in [VOL_SHORT, VOL_LONG]:
        df[f"volatility_{window}d"] = (
            df["daily_return"]
            .rolling(window, min_periods=window)
            .std() * np.sqrt(252)
        )
    return df


def _add_rsi(df: pd.DataFrame, period: int = RSI_PERIOD) -> pd.DataFrame:
    """
    Add RSI using Wilder's EMA smoothing.
    Output always 0-100. Over 70 = overbought, under 30 = oversold.

    Features added
    --------------
    rsi_14
    """
    df       = df.copy()
    delta    = df["Close"].diff()
    gain     = delta.clip(lower=0)
    loss     = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs       = avg_gain / avg_loss.replace(0, np.nan)
    df["rsi_14"] = 100 - (100 / (1 + rs))
    return df


def _add_macd(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add MACD line, signal line, and histogram.
    MACD      = EMA(12) - EMA(26)
    Signal    = EMA(9) of MACD
    Histogram = MACD - Signal (positive = bullish momentum building)

    Features added
    --------------
    macd, macd_signal, macd_hist
    """
    df                = df.copy()
    ema_fast          = df["Close"].ewm(span=MACD_FAST,   adjust=False).mean()
    ema_slow          = df["Close"].ewm(span=MACD_SLOW,   adjust=False).mean()
    df["macd"]        = ema_fast - ema_slow
    df["macd_signal"] = df["macd"].ewm(span=MACD_SIGNAL, adjust=False).mean()
    df["macd_hist"]   = df["macd"] - df["macd_signal"]
    return df


def _add_price_structure(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add Bollinger Band features, 52-week position, price vs SMAs.

    Features added
    --------------
    bb_position     -- where price sits within bands (0=lower band, 1=upper)
    bb_width        -- band width normalised by SMA (volatility regime proxy)
    week52_position -- price position within yearly high/low range
    price_vs_sma50  -- percent deviation from 50-day SMA
    price_vs_sma200 -- percent deviation from 200-day SMA
    """
    df         = df.copy()
    sma_bb     = df["Close"].rolling(BB_WINDOW).mean()
    std_bb     = df["Close"].rolling(BB_WINDOW).std()
    upper_bb   = sma_bb + BB_STD * std_bb
    lower_bb   = sma_bb - BB_STD * std_bb
    band_width = upper_bb - lower_bb

    df["bb_position"] = (df["Close"] - lower_bb) / band_width.replace(0, np.nan)
    df["bb_width"]    = band_width / sma_bb.replace(0, np.nan)

    rolling_high          = df["Close"].rolling(252, min_periods=126).max()
    rolling_low           = df["Close"].rolling(252, min_periods=126).min()
    price_range           = (rolling_high - rolling_low).replace(0, np.nan)
    df["week52_position"] = (df["Close"] - rolling_low) / price_range

    df["price_vs_sma50"]  = df["Close"] / df["Close"].rolling(50).mean()  - 1
    df["price_vs_sma200"] = df["Close"] / df["Close"].rolling(200).mean() - 1

    return df


def _add_volume_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add volume ratio vs rolling average.
    volume_ratio > 2 means trading at double the normal pace.

    Features added
    --------------
    volume_ratio
    """
    df      = df.copy()
    avg_vol = df["Volume"].rolling(VOLUME_WINDOW, min_periods=VOLUME_WINDOW).mean()
    df["volume_ratio"] = df["Volume"] / avg_vol.replace(0, np.nan)
    return df


def _add_target(df: pd.DataFrame, forward_days: int = FORWARD_DAYS) -> pd.DataFrame:
    """
    Add forward return column.
    Uses future prices intentionally -- this is the target, not a feature.
    Last forward_days rows will have NaN (no future data available).

    Column added
    ------------
    forward_return
    """
    df = df.copy()
    df["forward_return"] = df["Close"].shift(-forward_days) / df["Close"] - 1
    return df


def _build_ticker_features(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """
    Apply all feature functions to a single-ticker DataFrame.
    Uses a plain loop rather than groupby.apply() to avoid pandas
    version-specific column exclusion behaviour.

    Parameters
    ----------
    df     : single-ticker price history, any row order
    ticker : ticker string, re-attached as a column after processing
    """
    df = df.sort_values("Date").copy()
    df = _add_return_features(df)
    df = _add_volatility_features(df)
    df = _add_rsi(df)
    df = _add_macd(df)
    df = _add_price_structure(df)
    df = _add_volume_features(df)
    df = _add_target(df)
    df["Ticker"] = ticker
    return df


# ==============================================================================
# LABEL ASSIGNMENT -- cross-sectional, runs on full dataset after ticker loop
# ==============================================================================

def _add_labels(df: pd.DataFrame) -> pd.DataFrame:
    """
    Assign buy / hold / sell labels cross-sectionally per date.
    Labels based on relative performance across all tickers on the same date
    so the model learns relative outperformance, not absolute return.

    Labels
    ------
     1 = buy  (top third of forward returns on that date)
     0 = hold (middle third)
    -1 = sell (bottom third)

    Dates with fewer than 3 valid tickers get NaN labels and are
    dropped in the cleanup step.
    """
    df = df.copy()

    def _label_group(x):
        # Skip dates with too few valid values to form 3 quantiles
        valid = x.dropna()
        if len(valid) < N_QUANTILES:
            return pd.Series(np.nan, index=x.index)
        try:
            return pd.qcut(
                x.rank(method="first"),
                q=N_QUANTILES,
                labels=[-1, 0, 1],
                duplicates="drop",
            ).astype(float)
        except ValueError:
            return pd.Series(np.nan, index=x.index)

    df[TARGET_COL] = (
        df.groupby("Date")["forward_return"]
        .transform(_label_group)
    )
    return df


# ==============================================================================
# FUNDAMENTALS JOIN -- fiscal-year aligned, no data leakage
# ==============================================================================

def _join_fundamentals(
    features: pd.DataFrame,
    financials: pd.DataFrame,
) -> pd.DataFrame:
    available = [c for c in DESIRED_FIN_COLS if c in financials.columns]
    fin       = financials[available].copy()

    if "Total Revenue" in fin.columns:
        fin["revenue_growth"] = (
            fin.groupby("Ticker")["Total Revenue"].pct_change()
        )
    if "Net Income" in fin.columns:
        fin["net_income_growth"] = (
            fin.groupby("Ticker")["Net Income"].pct_change()
        )
    if "Gross Profit" in fin.columns and "Total Revenue" in fin.columns:
        fin["gross_margin"] = (
            fin["Gross Profit"] / fin["Total Revenue"].replace(0, np.nan)
        )
    if "Operating Income" in fin.columns and "Total Revenue" in fin.columns:
        fin["operating_margin"] = (
            fin["Operating Income"] / fin["Total Revenue"].replace(0, np.nan)
        )

    # Force clean datetime with no timezone on both key columns
    features["Date"]          = pd.to_datetime(features["Date"]).dt.tz_localize(None)
    fin["FiscalYearEnd"]      = pd.to_datetime(fin["FiscalYearEnd"]).dt.tz_localize(None)

    # CORRECT — merge_asof needs global Date sort; by="Ticker" handles grouping
    features = features.sort_values("Date").reset_index(drop=True)
    fin      = fin.sort_values("FiscalYearEnd").reset_index(drop=True)

    features = pd.merge_asof(
        features,
        fin,
        left_on="Date",
        right_on="FiscalYearEnd",
        by="Ticker",
        direction="backward",
    )

    logger.info(f"Financials joined -- shape: {features.shape}")
    return features


def _join_info(
    features: pd.DataFrame,
    info: pd.DataFrame,
) -> pd.DataFrame:
    """
    Join static categorical fields from company info table.
    Only sector and industry -- numerical ratios from info are
    point-in-time snapshots that would cause leakage for historical rows.
    Numerical fundamentals come from financials (correctly time-stamped).

    Used by
    -------
    build_features() internally
    model_training.py uses CAT_COLS to pass these to CatBoost
    """
    info_cats = info[["Ticker", "sector", "industry"]].copy()
    features  = features.merge(info_cats, on="Ticker", how="left")
    logger.info(f"Info categoricals joined -- shape: {features.shape}")
    return features


# ==============================================================================
# VALIDATION
# ==============================================================================

def _validate(df: pd.DataFrame) -> None:
    """
    Run quality assertions on the feature store before saving.
    Raises AssertionError with a clear message on failure.

    Used by
    -------
    build_features() internally
    tests/test_feature_engineering.py
    """
    assert not df.empty,                              "Feature store is empty"
    assert "Ticker"   in df.columns,                  "Missing Ticker column"
    assert "Date"     in df.columns,                  "Missing Date column"
    assert TARGET_COL in df.columns,                  f"Missing {TARGET_COL} column"
    assert "rsi_14"   in df.columns,                  "Missing rsi_14 column"
    assert "sector"   in df.columns,                  "Missing sector column"
    assert df.duplicated(["Ticker", "Date"]).sum() == 0, "Duplicate Ticker+Date rows"
    assert df[TARGET_COL].isna().sum() == 0,          "Null targets found"

    null_rates = df.isnull().mean()
    bad_cols   = null_rates[null_rates > 0.10].index.tolist()
    if bad_cols:
        logger.warning(f"High null rate columns (>10%): {bad_cols}")

    logger.info(
        f"Feature store validated -- shape: {df.shape} | "
        f"tickers: {df['Ticker'].nunique()} | "
        f"null max: {null_rates.max():.2%}"
    )


# ==============================================================================
# SAVE / LOAD -- public interface used by all downstream scripts
# ==============================================================================

def _save(df: pd.DataFrame) -> None:
    """
    Save feature store to Parquet with snappy compression.
    Writes both a latest file and a timestamped versioned snapshot.
    """
    FEATURES_FILE.parent.mkdir(parents=True, exist_ok=True)

    df.to_parquet(FEATURES_FILE, index=False, compression="snappy")

    ts        = datetime.now().strftime("%Y%m%d_%H%M")
    versioned = FEATURES_FILE.parent / f"features_{ts}.parquet"
    df.to_parquet(versioned, index=False, compression="snappy")

    size_mb = FEATURES_FILE.stat().st_size / 1_048_576
    logger.info(
        f"Saved features.parquet -- "
        f"{len(df):,} rows x {len(df.columns)} cols -- {size_mb:.2f} MB"
    )


def load_features(columns: Optional[list[str]] = None) -> pd.DataFrame:
    """
    Load the feature store from Parquet.
    Optionally specify columns to load only what you need (faster I/O).

    Parameters
    ----------
    columns : list[str] or None
        If provided, only these columns are loaded from disk.
        Useful in model_training.py to skip raw OHLCV columns.

    Returns
    -------
    pd.DataFrame -- feature store with all ML features and target

    Used by
    -------
    model_training.py, backtesting.py, dashboard.py

    Usage
    -----
        from src.feature_engineering import load_features, FEATURE_COLS, CAT_COLS

        # Load everything
        df = load_features()

        # Load only what the model needs (faster)
        df = load_features(columns=FEATURE_COLS + CAT_COLS + ["Ticker", "Date", "target"])
    """
    if not FEATURES_FILE.exists():
        raise FileNotFoundError(
            f"{FEATURES_FILE} not found. Run build_features() first:\n"
            "  from src.feature_engineering import build_features\n"
            "  build_features()"
        )
    df = pd.read_parquet(FEATURES_FILE, columns=columns)
    logger.info(f"Loaded features -- {df.shape}")
    return df


# ==============================================================================
# MAIN PIPELINE ENTRY POINT
# ==============================================================================

def build_features(
    history:      Optional[pd.DataFrame] = None,
    info:         Optional[pd.DataFrame] = None,
    financials:   Optional[pd.DataFrame] = None,
    forward_days: int = FORWARD_DAYS,
) -> pd.DataFrame:
    """
    Run the full feature engineering pipeline end to end.

    Parameters
    ----------
    history : pd.DataFrame or None
        Raw price history from data_collection.
        If None, loaded automatically from all_history.parquet.
    info : pd.DataFrame or None
        Company info from data_collection.
        If None, loaded automatically from all_info.parquet.
    financials : pd.DataFrame or None
        Annual financials from data_collection.
        If None, loaded automatically from all_financials.parquet.
    forward_days : int
        Trading days ahead to compute target return.
        Default 21 (~1 month). Use 63 for quarterly prediction.

    Returns
    -------
    pd.DataFrame -- complete feature store, also saved to FEATURES_FILE

    Usage
    -----
    # Standard run -- loads parquets automatically:
        from src.feature_engineering import build_features
        features = build_features()

    # Pass data directly from a notebook:
        from src.data_collection import load_all
        from src.feature_engineering import build_features
        data     = load_all()
        features = build_features(**data)

    # Change prediction horizon to 1 quarter:
        features = build_features(forward_days=63)
    """
    global FEATURE_COLS

    logger.info("=" * 60)
    logger.info("FEATURE ENGINEERING PIPELINE STARTED")
    logger.info(f"  Forward days : {forward_days}")
    logger.info("=" * 60)

    # -- 1. Load raw tables if not passed in -----------------------------------
    if history is None or info is None or financials is None:
        logger.info("Loading raw tables from Parquet...")
        data       = load_all()
        history    = history    or data["history"]
        info       = info       or data["info"]
        financials = financials or data["financials"]

    history["Date"]             = pd.to_datetime(history["Date"])
    financials["FiscalYearEnd"] = pd.to_datetime(financials["FiscalYearEnd"])

    logger.info(
        f"Inputs -- history: {history.shape} | "
        f"info: {info.shape} | "
        f"financials: {financials.shape}"
    )

    # -- 2. Technical features -- plain loop, one ticker at a time ------------
    # Plain loop avoids pandas groupby column-exclusion issues across versions.
    # Each ticker processed independently so rolling windows never bleed.
    tickers   = history["Ticker"].unique()
    n_tickers = len(tickers)
    logger.info(f"Building technical features for {n_tickers} tickers...")

    frames = []
    for idx, ticker in enumerate(tickers, start=1):
        group  = history[history["Ticker"] == ticker].copy()
        result = _build_ticker_features(group, ticker)
        frames.append(result)
        if idx % 100 == 0 or idx == n_tickers:
            logger.info(f"  Processed {idx}/{n_tickers} tickers")

    features = pd.concat(frames, ignore_index=True)
    logger.info(f"Technical features done -- shape: {features.shape}")

    # -- 3. Join fundamentals (fiscal-year aligned, no leakage) ---------------
    logger.info("Joining fundamentals via merge_asof (no data leakage)...")
    features = _join_fundamentals(features, financials)

    # -- 4. Join sector/industry categoricals ---------------------------------
    logger.info("Joining sector/industry categoricals from info...")
    features = _join_info(features, info)

    # -- 5. Cross-sectional buy/hold/sell labels -------------------------------
    logger.info("Assigning cross-sectional labels...")
    features = _add_labels(features)

    # -- 6. Drop burn-in rows and null targets ---------------------------------
    required_cols = [
        "daily_return", "return_21d", "volatility_21d",
        "rsi_14", "macd", "bb_position",
        "volume_ratio", "forward_return", TARGET_COL,
    ]
    rows_before = len(features)
    features    = features.dropna(subset=required_cols)
    rows_after  = len(features)
    pct_dropped = (rows_before - rows_after) / rows_before * 100
    logger.info(
        f"Dropped {rows_before - rows_after:,} burn-in/null rows "
        f"({pct_dropped:.1f}%) -- {rows_after:,} rows remain"
    )

    # -- 7. Derive FEATURE_COLS (exported for model_training.py) --------------
    FEATURE_COLS = [c for c in features.columns if c not in NON_FEATURE_COLS]

    # -- 8. Validate -----------------------------------------------------------
    _validate(features)

    # -- 9. Save ---------------------------------------------------------------
    _save(features)

    # -- 10. Summary -----------------------------------------------------------
    logger.info("=" * 60)
    logger.info("FEATURE ENGINEERING COMPLETE")
    logger.info(f"  Rows        : {len(features):,}")
    logger.info(f"  Columns     : {len(features.columns)}")
    logger.info(f"  Tickers     : {features['Ticker'].nunique()}")
    logger.info(f"  ML features : {len(FEATURE_COLS)}")
    logger.info(f"  Features    : {FEATURE_COLS}")
    logger.info("=" * 60)

    return features


# ==============================================================================
# CLI -- run directly: python src/feature_engineering.py
# ==============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build ML feature store")
    parser.add_argument(
        "--forward-days",
        type=int,
        default=FORWARD_DAYS,
        help=f"Forward return horizon in trading days (default: {FORWARD_DAYS})",
    )
    args = parser.parse_args()

    build_features(forward_days=args.forward_days)


