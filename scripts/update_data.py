"""Refresh the local market-data store (the "pantry").

Downloads the current S&P 500 constituent list (with GICS sectors) from Wikipedia and
5+ years of adjusted daily prices for every constituent via yfinance, then writes
data/raw/sp500_tickers.csv and data/processed/all_history.parquet.
It also warms the per-ticker cache for common ETFs used as benchmarks/sector proxies.

This replaces the original module 01 (notebooks/01_data_collection.ipynb), keeping its
fixes: certifi for macOS SSL, a browser User-Agent for Wikipedia, batched downloads,
and validation. Unlike the old version it never merges fundamentals onto daily rows
(that join on Ticker alone duplicated every price row once per fiscal year).

Usage (from the project root):
    python scripts/update_data.py            # full refresh (~5-10 minutes)
    python scripts/update_data.py --years 10 # longer history
"""
from __future__ import annotations

import argparse
import io
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import certifi  # noqa: E402

os.environ.setdefault("SSL_CERT_FILE", certifi.where())

import pandas as pd  # noqa: E402
import requests  # noqa: E402
import yfinance as yf  # noqa: E402

from app import config, data  # noqa: E402

WIKI = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


def refresh_tickers() -> pd.DataFrame:
    html = requests.get(WIKI, headers={"User-Agent": "Mozilla/5.0 (Macintosh) research-script"}, timeout=30).text
    df = pd.read_html(io.StringIO(html))[0]
    config.TICKERS_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(config.TICKERS_CSV, index=False)
    print(f"Saved {len(df)} constituents -> {config.TICKERS_CSV}")
    return df


def download_history(tickers: list[str], years: int, batch: int = 50) -> pd.DataFrame:
    frames, failed = [], []
    for i in range(0, len(tickers), batch):
        chunk = tickers[i:i + batch]
        raw = yf.download(chunk, period=f"{years}y", auto_adjust=True, group_by="ticker", threads=True, progress=False)
        for t in chunk:
            try:
                sub = raw[t] if isinstance(raw.columns, pd.MultiIndex) else raw
                sub = sub.dropna(subset=["Close"])
                if len(sub) < 200:
                    failed.append(t)
                    continue
                sub = sub.reset_index().rename(columns={"index": "Date"})
                sub["Ticker"] = t
                frames.append(sub[["Date", "Open", "High", "Low", "Close", "Volume", "Ticker"]])
            except Exception:
                failed.append(t)
        print(f"  {min(i + batch, len(tickers))}/{len(tickers)} tickers")
        time.sleep(1)
    hist = pd.concat(frames, ignore_index=True)
    hist = hist.drop_duplicates(["Ticker", "Date"]).sort_values(["Date", "Ticker"])
    # Dividends: yfinance.download doesn't return them; adjusted Close already includes them.
    hist["Dividends"] = 0.0
    if failed:
        print(f"Skipped (no/short data): {', '.join(failed)}")
    return hist


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=6)
    ap.add_argument("--skip-sp500", action="store_true", help="Only refresh the ETF cache")
    args = ap.parse_args()
    if not args.skip_sp500:
        df = refresh_tickers()
        tickers = df["Symbol"].astype(str).str.replace(".", "-", regex=False).tolist()
        hist = download_history(tickers, args.years)
        config.LOCAL_HISTORY.parent.mkdir(parents=True, exist_ok=True)
        hist.to_parquet(config.LOCAL_HISTORY, index=False)
        print(f"Saved {hist['Ticker'].nunique()} tickers, {len(hist):,} rows -> {config.LOCAL_HISTORY}")
    print("Warming ETF cache (full history)…")
    for t in data.ETF_META:
        df, info = data.load_series(t)
        print(f"  {t:5s} {info.source:28s} {info.first_date if df is None else df.index.min().date()} → "
              f"{'n/a' if df is None else df.index.max().date()}")


if __name__ == "__main__":
    main()
