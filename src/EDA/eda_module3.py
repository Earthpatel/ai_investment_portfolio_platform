# ==========================================
# EDA Module 3: Exploratory Data Analysis
# ==========================================

import os
import re
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

sns.set(style="whitegrid")

# -------------------------------
# 1️⃣ Utility functions
# -------------------------------
def sanitize_filename(name):
    """Sanitize string to make it safe as a filename."""
    return re.sub(r'[^a-zA-Z0-9_-]', '_', name)

def save_plot(fig, filename, output_dir="outputs/eda"):
    """Save a matplotlib figure to a safe path."""
    os.makedirs(output_dir, exist_ok=True)
    safe_name = sanitize_filename(filename)
    file_path = os.path.join(output_dir, f"{safe_name}.png")
    fig.savefig(file_path)
    plt.close(fig)
    print(f"Saved plot: {file_path}")

# -------------------------------
# 2️⃣ Feature groups
# -------------------------------
PRICE_FEATURES = {
    "Returns": ['return_1d','return_5d','return_10d','return_21d'],
    "Moving Averages": ['ma_5','ma_10','ma_21'],
    "Price/MA Ratios": ['price_ma5_ratio','price_ma10_ratio','price_ma21_ratio'],
    "Daily Range": ['daily_range','range_pct'],
    "Momentum": ['momentum_5','momentum_10','momentum_21',
                 'momentum_5_pct','momentum_10_pct','momentum_21_pct'],
    "Other": ['risk_adjusted_return','gap','52w_position']
}

VOLUME_FEATURES = {
    "Volume Avg": ['volume_avg_5','volume_avg_10','volume_avg_21'],
    "Volume Volatility": ['volume_vol_5','volume_vol_10','volume_vol_21'],
    "Volume Momentum": ['volume_momentum_5','volume_momentum_10','volume_momentum_21',
                        'volume_momentum_5_pct','volume_momentum_10_pct','volume_momentum_21_pct'],
    "Volume Ratios": ['volume_price_ratio','volume_ma5_ratio','volume_ma10_ratio','volume_ma21_ratio']
}

TECHNICAL_FEATURES = {
    "EMA": ['ema_5','ema_10','ema_21','ema_12','ema_26'],
    "MACD": ['macd','macd_signal'],
    "RSI": ['rsi_14'],
    "Close-to-EMA Ratios": ['close_ema5_ratio','close_ema10_ratio','close_ema21_ratio']
}

# -------------------------------
# 3️⃣ Plotting functions
# -------------------------------
def plot_feature_group(df, group_name, cols, ticker, output_dir="outputs/eda"):
    """Plot histograms with KDE for a group of features."""
    fig, ax = plt.subplots(figsize=(12,5))
    for col in cols:
        if col in df.columns:
            sns.histplot(df[col], bins=50, kde=True, label=col, stat="density", alpha=0.5, ax=ax)
    ax.set_title(f"{ticker} - {group_name}")
    ax.set_xlabel("Value")
    ax.set_ylabel("Density")
    ax.legend()
    save_plot(fig, f"{ticker}_{group_name}", output_dir)

def plot_macd_scatter(df, ticker, output_dir="outputs/eda"):
    """Scatter plot for MACD vs MACD Signal."""
    if 'macd' in df.columns and 'macd_signal' in df.columns:
        fig, ax = plt.subplots(figsize=(8,5))
        ax.scatter(df['macd'], df['macd_signal'], alpha=0.5)
        ax.set_xlabel("MACD")
        ax.set_ylabel("MACD Signal")
        ax.set_title(f"{ticker} - MACD vs MACD Signal")
        save_plot(fig, f"{ticker}_MACD_scatter", output_dir)

# -------------------------------
# 4️⃣ Main function
# -------------------------------
def main(features_csv="data/processed/features_dataset.csv", tickers_to_plot=None):
    # Load features dataset
    features = pd.read_csv(features_csv, low_memory=False)
    
    # Determine which tickers to plot
    tickers = tickers_to_plot if tickers_to_plot else features['Ticker'].unique()[:3]
    
    for ticker in tickers:
        ticker_df = features[features['Ticker'] == ticker]
        print(f"\n===== Visualizing features for {ticker} =====\n")
        
        # Price-based features
        for group_name, cols in PRICE_FEATURES.items():
            plot_feature_group(ticker_df, f"Price Features: {group_name}", cols, ticker)
        
        # Volume-based features
        for group_name, cols in VOLUME_FEATURES.items():
            plot_feature_group(ticker_df, f"Volume Features: {group_name}", cols, ticker)
        
        # Technical/Other features
        for group_name, cols in TECHNICAL_FEATURES.items():
            if group_name == "MACD":
                plot_macd_scatter(ticker_df, ticker)
            else:
                plot_feature_group(ticker_df, f"Technical Features: {group_name}", cols, ticker)

    print("\nEDA plots complete. Check outputs/eda/ folder.")

# -------------------------------
# Run script
# -------------------------------
if __name__ == "__main__":
    main()