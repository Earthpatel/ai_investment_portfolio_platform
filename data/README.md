# data/

Created locally by `python scripts/update_data.py` and by the API cache:

- `raw/sp500_tickers.csv`: S&P 500 constituents with GICS sectors
- `processed/all_history.parquet`: daily adjusted prices for the S&P 500
- `cache/<TICKER>.parquet`: per-ticker yfinance downloads (refreshed every 24h)
- `ml/results.json`: last ML training run

Nothing here is committed to git.
