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
    # In any notebook or script:
    from src import collect, load_all, load_history, load_info, load_financials
    from src import get_logger, START_DATE, END_DATE, PROCESSED_DIR

Pipeline order
--------------
    data_collection      → feature_engineering → model_training
    → backtesting → portfolio_optimizer → dashboard
"""

from src.data_collection import (
    # Pipeline runner
    collect,

    # Ticker refresh (run before collect when you want up-to-date tickers)
    refresh_tickers,

    # Loaders (used by every downstream script)
    load_all,
    load_history,
    load_info,
    load_financials,

    # Shared utilities
    get_logger,
    load_tickers,

    # Constants (imported by feature_engineering, model_training etc.)
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

__all__ = [
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
]
