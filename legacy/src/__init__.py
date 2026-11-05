"""
src/
====
AI Investment Manager Platform — source package.

Public API
----------
Every script in this project should import from here rather than
reaching into submodules directly. This keeps imports stable even
if internal file names change.

Usage
-----
    # Data collection
    from src import collect, load_all, refresh_tickers

    # Feature engineering
    from src import build_features, load_features, FEATURE_COLS, CAT_COLS

    # Shared utilities
    from src import get_logger, START_DATE, END_DATE, PROCESSED_DIR

Pipeline order
--------------
    data_collection      → feature_engineering → model_training
    → backtesting → portfolio_optimizer → dashboard
"""

# ── Data collection ────────────────────────────────────────────────────────────
from src.data_collection import (
    # Pipeline runners
    collect,
    refresh_tickers,

    # Loaders
    load_all,
    load_history,
    load_info,
    load_financials,

    # Shared utilities
    get_logger,
    load_tickers,

    # Constants
    START_DATE,
    END_DATE,
    PROJECT_ROOT,
    PROCESSED_DIR,
    RAW_DIR,
    LOGS_DIR,
    HISTORY_FILE,
    INFO_FILE,
    FINANCIALS_FILE,
    INFO_COLS,
    MIN_TRADING_DAYS,
    MAX_NULL_RATE,
)

# ── Feature engineering ────────────────────────────────────────────────────────
from src.feature_engineering import (
    # Pipeline runner
    build_features,

    # Loader
    load_features,

    # Constants — used by model_training.py
    FEATURES_FILE,
    FEATURE_COLS,
    CAT_COLS,
    TARGET_COL,
    FORWARD_DAYS,
    NON_FEATURE_COLS,
)

__all__ = [
    # ── data_collection ──────────────────────────────────────────────────────
    "collect",
    "refresh_tickers",
    "load_all",
    "load_history",
    "load_info",
    "load_financials",
    "get_logger",
    "load_tickers",
    "START_DATE",
    "END_DATE",
    "PROJECT_ROOT",
    "PROCESSED_DIR",
    "RAW_DIR",
    "LOGS_DIR",
    "HISTORY_FILE",
    "INFO_FILE",
    "FINANCIALS_FILE",
    "INFO_COLS",
    "MIN_TRADING_DAYS",
    "MAX_NULL_RATE",
    # ── feature_engineering ──────────────────────────────────────────────────
    "build_features",
    "load_features",
    "FEATURES_FILE",
    "FEATURE_COLS",
    "CAT_COLS",
    "TARGET_COL",
    "FORWARD_DAYS",
    "NON_FEATURE_COLS",
]
