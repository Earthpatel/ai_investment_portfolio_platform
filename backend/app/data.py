"""Market data layer.

Think of this as the pantry: it stocks prices once, labels every jar with where it
came from and when, and never invents food when a shelf is empty.

Source priority for a ticker's daily history:
  1. Fresh per-ticker cache (data/cache/<T>.parquet), written by earlier downloads
  2. yfinance download (period="max", auto-adjusted for splits + dividends)
  3. Stale cache (if the download failed)
  4. The original pipeline's all_history.parquet (S&P 500, ~5 years)
  5. DEV MODE ONLY: synthetic prices, always labeled as such

Prices are *adjusted closes* (dividends + splits folded in), i.e. a total-return proxy.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache

import numpy as np
import pandas as pd

from . import config

log = logging.getLogger("mc.data")

# ---------------------------------------------------------------------------
# Static metadata
# ---------------------------------------------------------------------------
ETF_META: dict[str, dict] = {
    "SPY": {"name": "SPDR S&P 500 ETF", "category": "Broad Market", "expense": 0.000945},
    "VOO": {"name": "Vanguard S&P 500 ETF", "category": "Broad Market", "expense": 0.0003},
    "IVV": {"name": "iShares Core S&P 500 ETF", "category": "Broad Market", "expense": 0.0003},
    "VTI": {"name": "Vanguard Total Stock Market ETF", "category": "Broad Market", "expense": 0.0003},
    "QQQ": {"name": "Invesco QQQ (Nasdaq-100)", "category": "Growth / Tech", "expense": 0.002},
    "DIA": {"name": "SPDR Dow Jones Industrial Avg ETF", "category": "Broad Market", "expense": 0.0016},
    "IWM": {"name": "iShares Russell 2000 ETF", "category": "Small Cap", "expense": 0.0019},
    "VXUS": {"name": "Vanguard Total International Stock ETF", "category": "International", "expense": 0.0005},
    "EFA": {"name": "iShares MSCI EAFE ETF", "category": "International", "expense": 0.0033},
    "VWO": {"name": "Vanguard FTSE Emerging Markets ETF", "category": "International", "expense": 0.0008},
    "BND": {"name": "Vanguard Total Bond Market ETF", "category": "Bonds", "expense": 0.0003},
    "AGG": {"name": "iShares Core US Aggregate Bond ETF", "category": "Bonds", "expense": 0.0003},
    "TLT": {"name": "iShares 20+ Year Treasury Bond ETF", "category": "Bonds", "expense": 0.0015},
    "GLD": {"name": "SPDR Gold Shares", "category": "Commodities", "expense": 0.004},
    "VNQ": {"name": "Vanguard Real Estate ETF", "category": "Real Estate", "expense": 0.0013},
    "SCHD": {"name": "Schwab US Dividend Equity ETF", "category": "Dividend", "expense": 0.0006},
    "XLK": {"name": "Technology Select Sector SPDR", "category": "Sector", "sector": "Information Technology", "expense": 0.0008},
    "XLV": {"name": "Health Care Select Sector SPDR", "category": "Sector", "sector": "Health Care", "expense": 0.0008},
    "XLF": {"name": "Financial Select Sector SPDR", "category": "Sector", "sector": "Financials", "expense": 0.0008},
    "XLE": {"name": "Energy Select Sector SPDR", "category": "Sector", "sector": "Energy", "expense": 0.0008},
    "XLY": {"name": "Consumer Discretionary Select Sector SPDR", "category": "Sector", "sector": "Consumer Discretionary", "expense": 0.0008},
    "XLP": {"name": "Consumer Staples Select Sector SPDR", "category": "Sector", "sector": "Consumer Staples", "expense": 0.0008},
    "XLI": {"name": "Industrial Select Sector SPDR", "category": "Sector", "sector": "Industrials", "expense": 0.0008},
    "XLU": {"name": "Utilities Select Sector SPDR", "category": "Sector", "sector": "Utilities", "expense": 0.0008},
    "XLRE": {"name": "Real Estate Select Sector SPDR", "category": "Sector", "sector": "Real Estate", "expense": 0.0008},
    "XLC": {"name": "Communication Services Select Sector SPDR", "category": "Sector", "sector": "Communication Services", "expense": 0.0008},
    "XLB": {"name": "Materials Select Sector SPDR", "category": "Sector", "sector": "Materials", "expense": 0.0008},
}

# Representative fund for each GICS sector (used by the explorer for comparisons).
SECTOR_ETF = {v["sector"]: k for k, v in ETF_META.items() if "sector" in v}

# APPROXIMATE largest holdings, used only to warn about overlap. Holdings change;
# the UI labels this as approximate.
ETF_TOP_HOLDINGS = {
    "SPY": ["NVDA", "MSFT", "AAPL", "AMZN", "META", "AVGO", "GOOGL", "GOOG", "TSLA", "BRK-B"],
    "VOO": ["NVDA", "MSFT", "AAPL", "AMZN", "META", "AVGO", "GOOGL", "GOOG", "TSLA", "BRK-B"],
    "IVV": ["NVDA", "MSFT", "AAPL", "AMZN", "META", "AVGO", "GOOGL", "GOOG", "TSLA", "BRK-B"],
    "VTI": ["NVDA", "MSFT", "AAPL", "AMZN", "META", "AVGO", "GOOGL", "GOOG", "TSLA", "BRK-B"],
    "QQQ": ["NVDA", "MSFT", "AAPL", "AMZN", "AVGO", "META", "GOOGL", "GOOG", "TSLA", "NFLX", "COST"],
    "XLK": ["NVDA", "MSFT", "AAPL", "AVGO", "ORCL", "PLTR", "AMD", "CSCO", "IBM", "CRM"],
    "XLF": ["BRK-B", "JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "AXP", "SPGI"],
    "XLV": ["LLY", "JNJ", "ABBV", "UNH", "ABT", "MRK", "TMO", "ISRG", "AMGN", "BSX"],
    "XLE": ["XOM", "CVX", "COP", "WMB", "EOG", "KMI", "SLB", "PSX", "MPC", "OKE"],
    "XLC": ["META", "GOOGL", "GOOG", "NFLX", "TMUS", "DIS", "T", "VZ", "EA", "CHTR"],
    "XLY": ["AMZN", "TSLA", "HD", "MCD", "BKNG", "TJX", "LOW", "SBUX", "ORLY", "NKE"],
}

BENCHMARK = "SPY"


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------
@dataclass
class SeriesInfo:
    ticker: str
    source: str  # "yfinance", "cache", "cache-stale", "local-parquet", "synthetic-dev", "unavailable"
    last_updated: str | None
    first_date: str | None = None
    last_date: str | None = None
    observations: int = 0
    note: str | None = None
    is_synthetic: bool = False


@dataclass
class PriceBundle:
    """Daily adjusted closes (columns = tickers) plus dividends and provenance."""
    close: pd.DataFrame
    dividends: pd.DataFrame
    volume: pd.DataFrame
    info: dict[str, SeriesInfo] = field(default_factory=dict)

    @property
    def synthetic(self) -> bool:
        return any(i.is_synthetic for i in self.info.values())


# ---------------------------------------------------------------------------
# Universe
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def universe() -> list[dict]:
    """Tickers the UI can search, with names and GICS sectors.

    Sector classification comes from the S&P 500 constituents table (GICS) that the
    original pipeline downloads from Wikipedia — the most reliable free source here.
    """
    out: list[dict] = []
    if config.TICKERS_CSV.exists():
        df = pd.read_csv(config.TICKERS_CSV)
        sym = "Symbol" if "Symbol" in df.columns else "Ticker"
        for _, r in df.iterrows():
            out.append({
                "ticker": str(r[sym]).replace(".", "-"),
                "name": str(r.get("Security", r[sym])),
                "sector": str(r.get("GICS Sector", "Unknown")),
                "industry": str(r.get("GICS Sub-Industry", "")),
                "type": "Stock",
            })
    else:
        # Minimal fallback so the app still works on a fresh clone.
        for t, n, s in [
            ("AAPL", "Apple Inc.", "Information Technology"), ("MSFT", "Microsoft", "Information Technology"),
            ("NVDA", "Nvidia", "Information Technology"), ("AMZN", "Amazon", "Consumer Discretionary"),
            ("GOOGL", "Alphabet Inc. (Class A)", "Communication Services"), ("META", "Meta Platforms", "Communication Services"),
            ("JPM", "JPMorgan Chase", "Financials"), ("JNJ", "Johnson & Johnson", "Health Care"),
            ("XOM", "ExxonMobil", "Energy"), ("TSLA", "Tesla, Inc.", "Consumer Discretionary"),
            ("KO", "Coca-Cola Company (The)", "Consumer Staples"), ("NEE", "NextEra Energy", "Utilities"),
        ]:
            out.append({"ticker": t, "name": n, "sector": s, "industry": "", "type": "Stock"})
    for t, m in ETF_META.items():
        out.append({"ticker": t, "name": m["name"], "sector": m.get("sector", m["category"]),
                    "industry": m["category"], "type": "ETF", "expense": m["expense"]})
    return out


def meta(ticker: str) -> dict:
    for row in universe():
        if row["ticker"] == ticker:
            return row
    return {"ticker": ticker, "name": ticker, "sector": "Unknown", "industry": "", "type": "Unknown"}


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
_lock = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Tidy a raw daily frame: tz-naive DatetimeIndex, sorted, de-duplicated, sane prices."""
    df = df.copy()
    if "Date" in df.columns:
        df = df.set_index("Date")
    idx = pd.to_datetime(df.index, utc=True, errors="coerce")
    df.index = idx.tz_convert(None).normalize()
    df = df[~df.index.isna()]
    df = df[~df.index.duplicated(keep="last")].sort_index()
    for col in ("Close", "Dividends", "Volume"):
        if col not in df.columns:
            df[col] = 0.0 if col != "Close" else np.nan
    # Validation: non-positive or missing closes are dropped (never filled with made-up prices)
    df = df[df["Close"] > 0]
    return df[["Close", "Dividends", "Volume"]].astype(float)


@lru_cache(maxsize=1)
def _local_history() -> pd.DataFrame | None:
    if not config.LOCAL_HISTORY.exists():
        return None
    try:
        df = pd.read_parquet(config.LOCAL_HISTORY)
        if "Ticker" not in df.columns:
            return None
        return df
    except Exception as exc:  # pragma: no cover - depends on local files
        log.warning("Could not read local history: %s", exc)
        return None


def _from_local(ticker: str) -> pd.DataFrame | None:
    df = _local_history()
    if df is None:
        return None
    sub = df[df["Ticker"] == ticker]
    if sub.empty:
        return None
    return _normalize(sub.drop(columns=["Ticker"]))


def _cache_path(ticker: str):
    return config.CACHE_DIR / f"{ticker}.parquet"


def _read_cache(ticker: str) -> tuple[pd.DataFrame | None, float | None]:
    p = _cache_path(ticker)
    if not p.exists():
        return None, None
    try:
        return pd.read_parquet(p), p.stat().st_mtime
    except Exception:
        return None, None


def _download(ticker: str) -> pd.DataFrame | None:
    if not config.ALLOW_NETWORK:
        return None
    try:
        import certifi, os  # noqa: E401  (macOS Python SSL fix from the original project)
        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
        import yfinance as yf
        raw = yf.Ticker(ticker).history(period="max", auto_adjust=True)
        if raw is None or raw.empty:
            return None
        df = _normalize(raw)
        config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        df.to_parquet(_cache_path(ticker))
        return df
    except Exception as exc:
        log.warning("yfinance download failed for %s: %s", ticker, exc)
        return None


def _synthetic(ticker: str) -> pd.DataFrame:
    """DEV MODE ONLY. Deterministic geometric Brownian motion with a shared market factor.

    These numbers are not market data. Every API response that touches them carries
    `synthetic: true`, and the UI shows a warning banner.
    """
    seed = int(hashlib.sha256(ticker.encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2004-01-02", "2026-10-30")
    n = len(dates)
    mkt = np.random.default_rng(42).normal(0.07 / 252, 0.17 / np.sqrt(252), n)
    beta = 0.6 + rng.random() * 0.9
    idio_vol = 0.08 + rng.random() * 0.25
    alpha = (rng.random() - 0.5) * 0.06 / 252
    r = alpha + beta * mkt + rng.normal(0, idio_vol / np.sqrt(252), n)
    price = 50 * np.exp(np.cumsum(r))
    div_yield = rng.random() * 0.03
    divs = np.where(np.arange(n) % 63 == 0, price * div_yield / 4, 0.0)
    return pd.DataFrame({"Close": price, "Dividends": divs,
                         "Volume": rng.integers(1_000_000, 50_000_000, n).astype(float)}, index=dates)


def load_series(ticker: str) -> tuple[pd.DataFrame | None, SeriesInfo]:
    ticker = ticker.upper().replace(".", "-")
    if config.DEV_SYNTHETIC:
        df = _synthetic(ticker)
        return df, SeriesInfo(ticker, "synthetic-dev", _now_iso(), is_synthetic=True,
                              note="DEV MODE: synthetic prices, not market data")
    with _lock:
        cached, mtime = _read_cache(ticker)
        fresh = mtime is not None and (time.time() - mtime) < config.CACHE_TTL_HOURS * 3600
        if cached is not None and fresh:
            return cached, SeriesInfo(ticker, "cache (yfinance)", datetime.fromtimestamp(mtime, timezone.utc).isoformat(timespec="seconds"))
        dl = _download(ticker)
        if dl is not None:
            return dl, SeriesInfo(ticker, "yfinance", _now_iso())
        if cached is not None:
            return cached, SeriesInfo(ticker, "cache-stale (yfinance)",
                                      datetime.fromtimestamp(mtime, timezone.utc).isoformat(timespec="seconds"),
                                      note="Download failed; using older cached data")
        local = _from_local(ticker)
        if local is not None:
            mt = datetime.fromtimestamp(config.LOCAL_HISTORY.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
            return local, SeriesInfo(ticker, "local-parquet (original pipeline)", mt,
                                     note="From data/processed/all_history.parquet")
    return None, SeriesInfo(ticker, "unavailable", None, note="No data source returned prices for this ticker")


def load_prices(tickers: list[str]) -> PriceBundle:
    closes, divs, vols, info = {}, {}, {}, {}
    for t in dict.fromkeys(tickers):
        df, si = load_series(t)
        if df is not None and not df.empty:
            closes[si.ticker] = df["Close"]
            divs[si.ticker] = df["Dividends"]
            vols[si.ticker] = df["Volume"]
            si.first_date = str(df.index.min().date())
            si.last_date = str(df.index.max().date())
            si.observations = int(len(df))
        info[si.ticker] = si
    # Outer join keeps each ticker's own inception date; alignment happens per use case.
    close = pd.DataFrame(closes).sort_index()
    return PriceBundle(close, pd.DataFrame(divs).reindex(close.index).fillna(0.0),
                       pd.DataFrame(vols).reindex(close.index), info)


# ---------------------------------------------------------------------------
# Transformations used by the engines
# ---------------------------------------------------------------------------
WINDOWS = {"1y": 1, "3y": 3, "5y": 5, "10y": 10, "15y": 15, "20y": 20, "max": None}


def window_start(end: pd.Timestamp, window: str) -> pd.Timestamp | None:
    years = WINDOWS.get(window, 10)
    return None if years is None else end - pd.DateOffset(years=years)


def monthly_log_returns(bundle: PriceBundle, tickers: list[str], window: str = "10y") -> tuple[pd.DataFrame, list[str]]:
    """Month-end log returns, aligned so every row has every asset (no gap filling).

    Returns (returns, warnings). If one asset has a shorter history than the window,
    the common period shrinks to that asset's history and a warning says so.
    """
    warnings: list[str] = []
    missing = [t for t in tickers if t not in bundle.close.columns]
    if missing:
        raise ValueError(f"No price data for: {', '.join(missing)}")
    px = bundle.close[tickers]
    end = px.dropna(how="all").index.max()
    start = window_start(end, window)
    if start is not None:
        px = px[px.index >= start]
    monthly = px.resample("ME").last()
    # Drop the trailing partial month so every return covers a full month
    if len(monthly) and monthly.index[-1] > end:
        monthly = monthly.iloc[:-1]
    rets = np.log(monthly / monthly.shift(1))
    first_valid = {t: rets[t].first_valid_index() for t in tickers}
    common = rets.dropna()
    if start is not None and len(common):
        req_months = WINDOWS[window] * 12
        if len(common) < req_months - 2:
            late = max(first_valid, key=lambda t: first_valid[t] or pd.Timestamp.min)
            warnings.append(f"Requested {window} window, but {late} only has data from "
                            f"{first_valid[late].date() if first_valid[late] is not None else 'n/a'}; "
                            f"using the common period of {len(common)} months.")
    if len(common) < 24:
        warnings.append(f"Only {len(common)} monthly observations — estimates are very noisy.")
    if len(common) < 12:
        raise ValueError("Fewer than 12 common monthly observations; choose different tickers or a longer window.")
    return common, warnings


def dividend_yields(bundle: PriceBundle, tickers: list[str], years: int = 3) -> np.ndarray:
    """Trailing annual dividend yield per asset (dividends paid / average price)."""
    out = []
    for t in tickers:
        c = bundle.close[t].dropna()
        d = bundle.dividends[t].reindex(c.index).fillna(0.0)
        cut = c.index.max() - pd.DateOffset(years=years)
        c, d = c[c.index >= cut], d[d.index >= cut]
        span = max((c.index.max() - c.index.min()).days / 365.25, 1e-9)
        out.append(float(d.sum() / c.mean() / span) if len(c) else 0.0)
    return np.clip(np.array(out), 0, 0.2)


def quality_report(bundle: PriceBundle, tickers: list[str], window: str) -> dict:
    rows = []
    for t in tickers:
        si = bundle.info.get(t)
        row = {"ticker": t, "source": si.source if si else "unavailable",
               "last_updated": si.last_updated if si else None, "note": si.note if si else None,
               "synthetic": bool(si and si.is_synthetic), "warnings": []}
        if t in bundle.close.columns:
            s = bundle.close[t]
            first, last = s.first_valid_index(), s.last_valid_index()
            span = s.loc[first:last]
            bdays = pd.bdate_range(first, last)
            missing_pct = max(0.0, 1 - len(span.dropna()) / max(len(bdays), 1))
            # US market holidays (~9/yr) explain ~3.5% of business days
            row.update({"first_date": str(first.date()), "last_date": str(last.date()),
                        "observations": int(span.notna().sum()),
                        "missing_business_days_pct": round(missing_pct * 100, 2)})
            years = (last - first).days / 365.25
            req = WINDOWS.get(window)
            if req and years < req:
                row["warnings"].append(f"Only {years:.1f} years of history (window asks for {req}).")
            if years < 3:
                row["warnings"].append("Short history: fewer than 3 years.")
            if missing_pct > 0.06:
                row["warnings"].append("Gaps beyond normal market holidays.")
            stale_days = (pd.Timestamp.now().normalize() - last).days
            if stale_days > 7:
                row["warnings"].append(f"Latest price is {stale_days} days old.")
        else:
            row["warnings"].append("No data available.")
        rows.append(row)
    return {"window": window, "assets": rows}


def info_dict(bundle: PriceBundle) -> list[dict]:
    return [json.loads(json.dumps(v.__dict__)) for v in bundle.info.values()]
