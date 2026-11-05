"""Paths and runtime settings.

Everything is relative to the project root so the app runs from any working directory.
"""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("MC_DATA_DIR", PROJECT_ROOT / "data"))

# Outputs of the original pipeline (module 01) — reused as a local data source.
LOCAL_HISTORY = DATA_DIR / "processed" / "all_history.parquet"
LOCAL_INFO = DATA_DIR / "processed" / "all_info.parquet"
TICKERS_CSV = DATA_DIR / "raw" / "sp500_tickers.csv"

# Per-ticker price cache written by the new data layer.
CACHE_DIR = DATA_DIR / "cache"
ML_DIR = DATA_DIR / "ml"

# How long a cached download is considered fresh before we try to refresh it.
CACHE_TTL_HOURS = float(os.environ.get("MC_CACHE_TTL_HOURS", "24"))

# DEV MODE: synthetic prices for offline development. Never on by default and
# always surfaced in API responses and the UI as "synthetic — not market data".
DEV_SYNTHETIC = os.environ.get("MC_DEV_SYNTHETIC", "0") == "1"

# Allow / disallow network fetches (yfinance). Useful for tests.
ALLOW_NETWORK = os.environ.get("MC_ALLOW_NETWORK", "1") == "1" and not DEV_SYNTHETIC

# Safety limits for the simulator.
MAX_SIMS = 20_000
MAX_YEARS = 50
MAX_ASSETS = 25
