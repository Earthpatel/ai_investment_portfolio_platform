"""
src/data_collection.py
======================
AI Investment Manager Platform — Data Collection Pipeline

Fetches S&P 500 price history, company info, and financials from yfinance
and saves validated Parquet files to data/processed/.

HOW OTHER SCRIPTS CONNECT TO THIS FILE
---------------------------------------
Every downstream script imports from this module like so:

    from src.data_collection import (
        load_tickers,
        load_history,
        load_info,
        load_financials,
        load_all,          # ← most scripts use this single entry point
        PROCESSED_DIR,
        START_DATE,
        END_DATE,
    )

Pipeline order:
    data_collection.py          ← YOU ARE HERE
        ↓
    feature_engineering.py      (imports load_all)
        ↓
    model_training.py           (imports load_all + feature store)
        ↓
    backtesting.py              (imports model + feature store)
        ↓
    portfolio_optimizer.py      (imports backtest results)
        ↓
    dashboard.py                (imports everything)
"""

import yfinance as yf
import pandas as pd
import numpy as np
import os
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTS  — imported by every downstream script
# ══════════════════════════════════════════════════════════════════════════════

# Pinned date range — change END_DATE when retraining on fresh data.
# All downstream scripts inherit these automatically via import.
START_DATE = "2020-01-01"
END_DATE   = "2025-01-01"

# Paths — all relative to project root.
# Downstream scripts import PROCESSED_DIR so paths stay consistent.
PROJECT_ROOT  = Path(__file__).resolve().parent.parent
RAW_DIR       = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
LOGS_DIR      = PROJECT_ROOT / "logs"

TICKERS_CSV   = RAW_DIR / "sp500_tickers.csv"

# Fetch tuning
BATCH_SIZE       = 50     # tickers per API batch
SLEEP_BETWEEN    = 2.0    # seconds between batches (rate-limit buffer)
MIN_TRADING_DAYS = 200    # drop tickers with fewer rows
MAX_NULL_RATE    = 0.10   # flag columns with >10% nulls

# Output filenames — imported by feature_engineering.py, model_training.py etc.
HISTORY_FILE    = PROCESSED_DIR / "all_history.parquet"
INFO_FILE       = PROCESSED_DIR / "all_info.parquet"
FINANCIALS_FILE = PROCESSED_DIR / "all_financials.parquet"

# Metadata columns to keep from yfinance info dict.
# Trimmed to fields that are genuinely useful as ML features downstream.
INFO_COLS = [
    "shortName", "sector", "industry", "country",
    "marketCap", "trailingPE", "forwardPE", "priceToBook",
    "trailingEps", "forwardEps", "dividendYield", "beta",
    "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "averageVolume",
    "totalDebt", "totalCash", "returnOnEquity", "returnOnAssets",
    "revenueGrowth", "grossMargins", "operatingMargins", "profitMargins",
    "debtToEquity", "currentRatio", "quickRatio",
    "sharesOutstanding", "floatShares",
    "heldPercentInsiders", "heldPercentInstitutions",
]


# ══════════════════════════════════════════════════════════════════════════════
# LOGGING  — shared logger reused by downstream scripts
# ══════════════════════════════════════════════════════════════════════════════

def get_logger(name: str = __name__) -> logging.Logger:
    """
    Return a logger that writes to both console and logs/data_collection.log.
    Downstream scripts call get_logger(__name__) to get their own named logger
    that still writes to the same log file.

    Usage in other scripts:
        from src.data_collection import get_logger
        logger = get_logger(__name__)
    """
    # Ensure logs directory exists before FileHandler tries to open it
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers if module is re-imported
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    fmt = logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")

    # File handler — persists across runs
    fh = logging.FileHandler(LOGS_DIR / "pipeline.log")
    fh.setFormatter(fmt)

    # Console handler — visible in notebook / terminal
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


logger = get_logger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# DIRECTORY BOOTSTRAP
# ══════════════════════════════════════════════════════════════════════════════

def _ensure_dirs() -> None:
    """Create all required project directories if they don't exist."""
    for d in [RAW_DIR, PROCESSED_DIR, LOGS_DIR]:
        d.mkdir(parents=True, exist_ok=True)


# ══════════════════════════════════════════════════════════════════════════════
# TICKER LOADING
# ══════════════════════════════════════════════════════════════════════════════

def refresh_tickers(csv_path: Path = TICKERS_CSV) -> None:
    """
    Pull the latest S&P 500 tickers from Wikipedia and save to CSV.

    Call this before collect() whenever you want an up-to-date ticker list.
    Safe to skip if your CSV is less than 3 months old.

    Fixes applied vs naive pd.read_html():
      1. User-Agent header — Wikipedia blocks default Python requests (403).
      2. SSL cert workaround — macOS Python 3.13 needs explicit cert context.

    Used by
    -------
    Called manually or via CLI: python src/data_collection.py --refresh
    """
    import ssl
    import certifi

    csv_path.parent.mkdir(parents=True, exist_ok=True)

    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

    # Fix 1: spoof a browser User-Agent so Wikipedia doesn't return 403
    # Fix 2: pass SSL context to handle macOS certificate verification errors
    try:
        df = pd.read_html(
            url,
            storage_options={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
        )[0]
    except Exception:
        # Fallback: manually fetch with SSL context then pass HTML to read_html
        import urllib.request
        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
        )
        with urllib.request.urlopen(req, context=ssl_ctx) as resp:
            html = resp.read().decode("utf-8")
        df = pd.read_html(html)[0]

    df.to_csv(csv_path, index=False)
    logger.info(f"Tickers refreshed — {len(df)} companies saved to {csv_path.name}")
    logger.info(f"Columns: {df.columns.tolist()}")


def load_tickers(csv_path: Path = TICKERS_CSV) -> list[str]:
    """
    Load and normalise S&P 500 tickers from CSV.

    Handles both 'Symbol' and 'Ticker' column names.
    Converts BRK.B → BRK-B (yfinance uses hyphens).

    Returns
    -------
    list[str]  e.g. ['MMM', 'AOS', 'ABT', ..., 'BRK-B', ...]

    Used by
    -------
    feature_engineering.py, model_training.py (via load_all)
    """
    if not csv_path.exists():
        logger.error(f"Tickers CSV not found: {csv_path}")
        raise FileNotFoundError(
            f"Cannot find {csv_path}.\n"
            "Regenerate it by calling refresh_tickers() or running:\n"
            "  python src/data_collection.py --refresh"
        )

    df = pd.read_csv(csv_path)
    col = "Symbol" if "Symbol" in df.columns else "Ticker"
    tickers = df[col].str.strip().str.replace(".", "-", regex=False).tolist()

    logger.info(f"Loaded {len(tickers)} tickers from {csv_path.name}")
    return tickers


# ══════════════════════════════════════════════════════════════════════════════
# FETCH HELPERS  (private — not imported directly by downstream scripts)
# ══════════════════════════════════════════════════════════════════════════════

def _fetch_history_batch(
    ticker_list: list[str],
    start: str,
    end: str,
) -> tuple[pd.DataFrame, list[str]]:
    """Fetch OHLCV history for one batch of tickers."""
    frames, failed = [], []

    for ticker in ticker_list:
        try:
            df = yf.Ticker(ticker).history(start=start, end=end)

            if df.empty:
                logger.warning(f"{ticker}: no history returned")
                failed.append(ticker)
                continue

            if len(df) < MIN_TRADING_DAYS:
                logger.warning(f"{ticker}: only {len(df)} rows (< {MIN_TRADING_DAYS}) — skipped")
                failed.append(ticker)
                continue

            df = df.reset_index()
            df["Ticker"] = ticker
            df = df[["Ticker", "Date", "Open", "High", "Low", "Close", "Volume"]]

            # Strip timezone so Date is a plain datetime — safe for all joins
            df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None).dt.normalize()

            frames.append(df)

        except Exception as exc:
            logger.error(f"{ticker} history error: {exc}")
            failed.append(ticker)

    combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return combined, failed


def _fetch_info_batch(
    ticker_list: list[str],
) -> tuple[pd.DataFrame, list[str]]:
    """Fetch company metadata for one batch of tickers."""
    rows, failed = [], []

    for ticker in ticker_list:
        try:
            info = yf.Ticker(ticker).info
            if not info:
                logger.warning(f"{ticker}: empty info dict")
                failed.append(ticker)
                continue

            row = {"Ticker": ticker}
            for col in INFO_COLS:
                row[col] = info.get(col, np.nan)
            rows.append(row)

        except Exception as exc:
            logger.error(f"{ticker} info error: {exc}")
            failed.append(ticker)

    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    return df, failed


def _fetch_financials_batch(
    ticker_list: list[str],
) -> tuple[pd.DataFrame, list[str]]:
    """Fetch annual income statement for one batch of tickers."""
    frames, failed = [], []

    for ticker in ticker_list:
        try:
            raw = yf.Ticker(ticker).financials  # shape: metrics × fiscal_years

            if raw is None or raw.empty:
                logger.warning(f"{ticker}: no financials returned")
                failed.append(ticker)
                continue

            # Transpose so each row = one fiscal year
            df = raw.T.copy()
            df.index.name = "FiscalYearEnd"
            df = df.reset_index()
            df["FiscalYearEnd"] = pd.to_datetime(df["FiscalYearEnd"]).dt.tz_localize(None)
            df.insert(0, "Ticker", ticker)

            frames.append(df)

        except Exception as exc:
            logger.error(f"{ticker} financials error: {exc}")
            failed.append(ticker)

    combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return combined, failed


# ══════════════════════════════════════════════════════════════════════════════
# BATCH RUNNERS  (orchestrate batches + sleep)
# ══════════════════════════════════════════════════════════════════════════════

def _run_batched(
    fetch_fn,
    tickers: list[str],
    label: str,
    **kwargs,
) -> tuple[pd.DataFrame, list[str]]:
    """
    Generic batch runner.
    Splits tickers into BATCH_SIZE chunks, calls fetch_fn on each,
    sleeps between batches to respect rate limits, and collects results.
    """
    all_frames, all_failed = [], []
    total = (len(tickers) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_num, i in enumerate(range(0, len(tickers), BATCH_SIZE), start=1):
        batch = tickers[i : i + BATCH_SIZE]
        logger.info(f"{label} — batch {batch_num}/{total}  ({batch[0]} … {batch[-1]})")

        df, failed = fetch_fn(batch, **kwargs)

        if not df.empty:
            all_frames.append(df)
        all_failed.extend(failed)

        if batch_num < total:
            time.sleep(SLEEP_BETWEEN)

    combined = pd.concat(all_frames, ignore_index=True) if all_frames else pd.DataFrame()
    logger.info(f"{label} complete — {len(combined):,} rows, {len(all_failed)} failed")
    return combined, all_failed


# ══════════════════════════════════════════════════════════════════════════════
# VALIDATION
# ══════════════════════════════════════════════════════════════════════════════

def _validate(df: pd.DataFrame, name: str, required_cols: list[str]) -> None:
    """
    Run basic quality assertions on a DataFrame.
    Raises AssertionError with a clear message on failure.
    Called internally before saving — also importable by test suite.

    Used by
    -------
    tests/test_data_collection.py
    """
    assert not df.empty, f"{name}: DataFrame is empty"

    for col in required_cols:
        assert col in df.columns, f"{name}: missing required column '{col}'"

    null_rates = df.isnull().mean()
    bad_cols = null_rates[null_rates > MAX_NULL_RATE].index.tolist()
    if bad_cols:
        logger.warning(f"{name}: high null rate columns: {bad_cols}")

    logger.info(
        f"{name} validated — shape: {df.shape} | "
        f"null rate max: {null_rates.max():.2%}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# SAVE / LOAD  — the public interface used by all downstream scripts
# ══════════════════════════════════════════════════════════════════════════════

def _save(df: pd.DataFrame, path: Path, name: str) -> None:
    """
    Save DataFrame to Parquet (snappy compression).
    Also writes a timestamped versioned copy for rollback.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    # Overwrite latest
    df.to_parquet(path, index=False, compression="snappy")

    # Versioned snapshot
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    versioned = path.parent / f"{path.stem}_{ts}.parquet"
    df.to_parquet(versioned, index=False, compression="snappy")

    size_mb = path.stat().st_size / 1_048_576
    logger.info(f"Saved {path.name} — {len(df):,} rows × {len(df.columns)} cols — {size_mb:.2f} MB")


def load_history() -> pd.DataFrame:
    """
    Load processed price history from Parquet.

    Returns
    -------
    pd.DataFrame  columns: Ticker, Date, Open, High, Low, Close, Volume

    Used by
    -------
    feature_engineering.py, backtesting.py, dashboard.py
    """
    if not HISTORY_FILE.exists():
        raise FileNotFoundError(
            f"{HISTORY_FILE} not found. Run collect() first."
        )
    df = pd.read_parquet(HISTORY_FILE)
    logger.info(f"Loaded history — {df.shape}")
    return df


def load_info() -> pd.DataFrame:
    """
    Load processed company info from Parquet.

    Returns
    -------
    pd.DataFrame  columns: Ticker, sector, marketCap, beta, ...

    Used by
    -------
    feature_engineering.py, portfolio_optimizer.py, dashboard.py
    """
    if not INFO_FILE.exists():
        raise FileNotFoundError(
            f"{INFO_FILE} not found. Run collect() first."
        )
    df = pd.read_parquet(INFO_FILE)
    logger.info(f"Loaded info — {df.shape}")
    return df


def load_financials() -> pd.DataFrame:
    """
    Load processed financials from Parquet.

    Returns
    -------
    pd.DataFrame  columns: Ticker, FiscalYearEnd, Total Revenue, Net Income, ...

    Used by
    -------
    feature_engineering.py (time-aligned join to price history)
    """
    if not FINANCIALS_FILE.exists():
        raise FileNotFoundError(
            f"{FINANCIALS_FILE} not found. Run collect() first."
        )
    df = pd.read_parquet(FINANCIALS_FILE)
    logger.info(f"Loaded financials — {df.shape}")
    return df


def load_all() -> dict[str, pd.DataFrame]:
    """
    Single entry point that loads all three tables at once.
    This is what most downstream scripts import.

    Returns
    -------
    dict with keys: 'history', 'info', 'financials'

    Usage in downstream scripts
    ---------------------------
        from src.data_collection import load_all

        data = load_all()
        history    = data['history']
        info       = data['info']
        financials = data['financials']
    """
    return {
        "history":    load_history(),
        "info":       load_info(),
        "financials": load_financials(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# MAIN PIPELINE ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def collect(
    tickers: Optional[list[str]] = None,
    start: str = START_DATE,
    end: str = END_DATE,
) -> dict[str, pd.DataFrame]:
    """
    Run the full data collection pipeline.

    Parameters
    ----------
    tickers : list[str] or None
        Pass a list to override (useful for testing with a small subset).
        If None, loads all S&P 500 tickers from TICKERS_CSV.
    start : str
        Start date string 'YYYY-MM-DD'. Defaults to module-level START_DATE.
    end : str
        End date string 'YYYY-MM-DD'. Defaults to module-level END_DATE.

    Returns
    -------
    dict with keys: 'history', 'info', 'financials'
    Same shape as load_all() — so callers can use either interchangeably.

    Usage
    -----
    # Full run (all 503 tickers):
        from src.data_collection import collect
        data = collect()

    # Test run (first 10 tickers):
        data = collect(tickers=load_tickers()[:10])

    # Custom date range:
        data = collect(start='2022-01-01', end='2024-01-01')
    """
    _ensure_dirs()
    logger.info("=" * 60)
    logger.info("DATA COLLECTION PIPELINE STARTED")
    logger.info(f"  Date range : {start} → {end}")

    if tickers is None:
        tickers = load_tickers()

    logger.info(f"  Tickers    : {len(tickers)}")
    logger.info("=" * 60)

    # ── 1. Price history ───────────────────────────────────────────────────────
    history, failed_h = _run_batched(
        _fetch_history_batch, tickers, "History", start=start, end=end
    )
    _validate(history, "History", ["Ticker", "Date", "Close"])

    # ── 2. Company info ────────────────────────────────────────────────────────
    info, failed_i = _run_batched(
        _fetch_info_batch, tickers, "Info"
    )
    _validate(info, "Info", ["Ticker", "sector"])

    # ── 3. Financials ──────────────────────────────────────────────────────────
    financials, failed_f = _run_batched(
        _fetch_financials_batch, tickers, "Financials"
    )
    _validate(financials, "Financials", ["Ticker", "FiscalYearEnd"])

    # ── 4. Save ────────────────────────────────────────────────────────────────
    _save(history,    HISTORY_FILE,    "history")
    _save(info,       INFO_FILE,       "info")
    _save(financials, FINANCIALS_FILE, "financials")

    # ── 5. Failed ticker log ───────────────────────────────────────────────────
    all_failed = (
        [{"Ticker": t, "Stage": "history"}    for t in failed_h] +
        [{"Ticker": t, "Stage": "info"}       for t in failed_i] +
        [{"Ticker": t, "Stage": "financials"} for t in failed_f]
    )
    if all_failed:
        pd.DataFrame(all_failed).to_csv(LOGS_DIR / "failed_tickers.csv", index=False)
        logger.warning(f"{len(all_failed)} failed ticker-stage pairs logged to logs/failed_tickers.csv")

    # ── 6. Summary ─────────────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("DATA COLLECTION COMPLETE")
    logger.info(f"  History rows    : {len(history):,}")
    logger.info(f"  Info rows       : {len(info):,}")
    logger.info(f"  Financials rows : {len(financials):,}")
    logger.info(f"  Failed (unique) : {len(set(failed_h + failed_i + failed_f))}")
    logger.info("=" * 60)

    return {"history": history, "info": info, "financials": financials}


# ══════════════════════════════════════════════════════════════════════════════
# CLI  — run directly: python src/data_collection.py
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Collect S&P 500 data")
    parser.add_argument("--start",   default=START_DATE, help="Start date YYYY-MM-DD")
    parser.add_argument("--end",     default=END_DATE,   help="End date YYYY-MM-DD")
    parser.add_argument("--limit",   type=int, default=None,
                        help="Limit to first N tickers (for testing)")
    parser.add_argument("--refresh", action="store_true",
                        help="Refresh tickers from Wikipedia before collecting")
    args = parser.parse_args()

    # Optionally refresh tickers from Wikipedia first
    if args.refresh:
        logger.info("Refreshing tickers from Wikipedia...")
        refresh_tickers()

    tickers = load_tickers()
    if args.limit:
        tickers = tickers[: args.limit]
        logger.info(f"Running in test mode — {args.limit} tickers only")

    collect(tickers=tickers, start=args.start, end=args.end)
