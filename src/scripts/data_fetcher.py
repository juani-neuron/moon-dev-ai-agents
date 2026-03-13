"""
OHLCV Data Fetcher — CCXT + Binance
Fetches multi-year historical crypto data for backtesting.
Outputs CSV files compatible with backtesting.py and the batch_backtest_runner.

Usage:
    # Fetch all default pairs (BTC, ETH, SOL) at all timeframes
    ./venv/bin/python3 src/scripts/data_fetcher.py

    # Fetch specific pair and timeframe
    ./venv/bin/python3 src/scripts/data_fetcher.py --symbol BTC/USDT --timeframe 15m

    # Fetch with custom date range
    ./venv/bin/python3 src/scripts/data_fetcher.py --symbol BTC/USDT --timeframe 1h --since 2022-01-01

    # List available symbols
    ./venv/bin/python3 src/scripts/data_fetcher.py --list-symbols

    # Fetch and replace the stale RBI backtest data
    ./venv/bin/python3 src/scripts/data_fetcher.py --update-rbi
"""

import ccxt
import pandas as pd
import time
import argparse
import sys
from pathlib import Path
from datetime import datetime, timezone

# Paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "src" / "data"
RBI_DIR = DATA_DIR / "rbi"

# Binance returns max 1000 candles per request
BATCH_SIZE = 1000

# Default symbols and timeframes for backtesting
DEFAULT_PAIRS = {
    "BTC/USDT": "BTC-USD",
    "ETH/USDT": "ETH-USD",
    "SOL/USDT": "SOL-USD",
}

DEFAULT_TIMEFRAMES = ["15m", "1h", "4h"]

# Rate limit: be polite to Binance (ms between requests)
RATE_LIMIT_MS = 100


def create_exchange():
    """Create a Binance exchange instance (no API key needed for public data)."""
    exchange = ccxt.binance({
        "enableRateLimit": True,
        "rateLimit": RATE_LIMIT_MS,
    })
    return exchange


def fetch_ohlcv(exchange, symbol, timeframe, since_ts, until_ts=None):
    """
    Fetch OHLCV data with pagination.
    Binance returns max 1000 candles per request, so we paginate forward.

    Args:
        exchange: ccxt exchange instance
        symbol: e.g. "BTC/USDT"
        timeframe: e.g. "15m", "1h", "4h"
        since_ts: start timestamp in milliseconds
        until_ts: end timestamp in ms (default: now)

    Returns:
        pd.DataFrame with columns: datetime, Open, High, Low, Close, Volume
    """
    if until_ts is None:
        until_ts = int(datetime.now(timezone.utc).timestamp() * 1000)

    tf_ms = exchange.parse_timeframe(timeframe) * 1000
    all_candles = []
    current_since = since_ts
    total_fetched = 0

    print(f"Fetching {symbol} {timeframe} from {datetime.fromtimestamp(since_ts/1000, tz=timezone.utc).strftime('%Y-%m-%d')} ...")

    while current_since < until_ts:
        try:
            candles = exchange.fetch_ohlcv(
                symbol, timeframe, since=current_since, limit=BATCH_SIZE
            )
        except ccxt.RateLimitExceeded:
            print("  Rate limited, waiting 10s...")
            time.sleep(10)
            continue
        except ccxt.NetworkError as e:
            print(f"  Network error: {e}, retrying in 5s...")
            time.sleep(5)
            continue
        except ccxt.ExchangeError as e:
            print(f"  Exchange error: {e}")
            break

        if not candles:
            break

        # Filter candles that are within our range
        candles = [c for c in candles if c[0] < until_ts]
        if not candles:
            break

        all_candles.extend(candles)
        total_fetched += len(candles)

        # Move forward past the last candle
        last_ts = candles[-1][0]
        current_since = last_ts + tf_ms

        # Progress indicator every 10K candles
        if total_fetched % 10000 < BATCH_SIZE:
            last_date = datetime.fromtimestamp(last_ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
            print(f"  {total_fetched:,} candles fetched (up to {last_date})")

        # If we got fewer than BATCH_SIZE, we've reached the end
        if len(candles) < BATCH_SIZE:
            break

    if not all_candles:
        print(f"  No data returned for {symbol} {timeframe}")
        return pd.DataFrame()

    # Build DataFrame
    df = pd.DataFrame(all_candles, columns=["timestamp", "Open", "High", "Low", "Close", "Volume"])
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.drop(columns=["timestamp"])
    df = df[["datetime", "Open", "High", "Low", "Close", "Volume"]]
    df = df.drop_duplicates(subset=["datetime"]).sort_values("datetime").reset_index(drop=True)

    first = df["datetime"].iloc[0].strftime("%Y-%m-%d")
    last = df["datetime"].iloc[-1].strftime("%Y-%m-%d")
    print(f"  Done: {len(df):,} candles from {first} to {last}")

    return df


def save_csv(df, symbol_name, timeframe, output_dir=None):
    """
    Save DataFrame to CSV in backtesting.py-compatible format.

    The CSV uses lowercase columns (datetime, open, high, low, close, volume)
    to match the existing BTC-USD-15m.csv format used by the batch backtest runner.
    """
    if output_dir is None:
        output_dir = DATA_DIR

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{symbol_name}-{timeframe}.csv"
    filepath = output_dir / filename

    # Match existing format: lowercase columns, no index
    out = df.copy()
    out.columns = ["datetime", "open", "high", "low", "close", "volume"]
    # Remove timezone info to match existing format
    out["datetime"] = out["datetime"].dt.tz_localize(None)
    out.to_csv(filepath, index=False)

    print(f"  Saved: {filepath} ({len(df):,} rows)")
    return filepath


def since_to_ms(since_str):
    """Convert a date string like '2023-01-01' to timestamp in ms."""
    dt = datetime.strptime(since_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def list_symbols(exchange):
    """List popular crypto trading pairs available on Binance."""
    exchange.load_markets()
    usdt_pairs = sorted([s for s in exchange.symbols if s.endswith("/USDT") and ":" not in s])
    print(f"\nAvailable USDT spot pairs on Binance: {len(usdt_pairs)}")
    # Show top ones
    top = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
           "DOGE/USDT", "ADA/USDT", "AVAX/USDT", "DOT/USDT", "LINK/USDT",
           "MATIC/USDT", "NEAR/USDT", "ARB/USDT", "OP/USDT", "SUI/USDT"]
    print("\nPopular pairs:")
    for s in top:
        if s in usdt_pairs:
            print(f"  {s}")
    print(f"\n... and {len(usdt_pairs) - len(top)}+ more. Use --symbol to fetch any pair.")


def update_rbi_data(exchange, since_str="2023-01-01"):
    """
    Fetch fresh BTC 15m data and save it to the RBI directory,
    replacing the stale BTC-USD-15m.csv used by backtests.
    Also fetches ETH and SOL for diversified backtesting.
    """
    since_ms = since_to_ms(since_str)

    print(f"\n=== Updating RBI backtest data (since {since_str}) ===\n")

    for ccxt_symbol, csv_name in DEFAULT_PAIRS.items():
        df = fetch_ohlcv(exchange, ccxt_symbol, "15m", since_ms)
        if not df.empty:
            save_csv(df, csv_name, "15m", output_dir=RBI_DIR)
        print()

    print("RBI data updated. Backtests will now use fresh data.")


def main():
    parser = argparse.ArgumentParser(description="Fetch historical OHLCV data from Binance via CCXT")
    parser.add_argument("--symbol", type=str, help="Trading pair (e.g. BTC/USDT)")
    parser.add_argument("--timeframe", type=str, help="Candle timeframe (e.g. 15m, 1h, 4h, 1d)")
    parser.add_argument("--since", type=str, default="2023-01-01", help="Start date YYYY-MM-DD (default: 2023-01-01)")
    parser.add_argument("--until", type=str, default=None, help="End date YYYY-MM-DD (default: now)")
    parser.add_argument("--output-dir", type=str, default=None, help="Output directory (default: src/data/)")
    parser.add_argument("--output-name", type=str, default=None, help="Output filename prefix (default: derived from symbol)")
    parser.add_argument("--list-symbols", action="store_true", help="List available trading pairs")
    parser.add_argument("--update-rbi", action="store_true", help="Update RBI backtest data (BTC/ETH/SOL 15m)")
    parser.add_argument("--all", action="store_true", help="Fetch all default pairs at all default timeframes")

    args = parser.parse_args()

    exchange = create_exchange()

    if args.list_symbols:
        list_symbols(exchange)
        return

    if args.update_rbi:
        update_rbi_data(exchange, args.since)
        return

    if args.all:
        since_ms = since_to_ms(args.since)
        until_ms = since_to_ms(args.until) if args.until else None

        print(f"\n=== Fetching all default pairs and timeframes (since {args.since}) ===\n")
        for ccxt_symbol, csv_name in DEFAULT_PAIRS.items():
            for tf in DEFAULT_TIMEFRAMES:
                df = fetch_ohlcv(exchange, ccxt_symbol, tf, since_ms, until_ms)
                if not df.empty:
                    save_csv(df, csv_name, tf, output_dir=args.output_dir)
                print()
        return

    # Single symbol + timeframe fetch
    if not args.symbol:
        parser.print_help()
        print("\nExamples:")
        print("  ./venv/bin/python3 src/scripts/data_fetcher.py --update-rbi")
        print("  ./venv/bin/python3 src/scripts/data_fetcher.py --all --since 2022-01-01")
        print("  ./venv/bin/python3 src/scripts/data_fetcher.py --symbol BTC/USDT --timeframe 15m")
        return

    if not args.timeframe:
        print("Error: --timeframe required when using --symbol")
        sys.exit(1)

    since_ms = since_to_ms(args.since)
    until_ms = since_to_ms(args.until) if args.until else None

    df = fetch_ohlcv(exchange, args.symbol, args.timeframe, since_ms, until_ms)
    if df.empty:
        print("No data fetched.")
        sys.exit(1)

    # Determine output name
    if args.output_name:
        name = args.output_name
    else:
        name = args.symbol.replace("/", "-")

    save_csv(df, name, args.timeframe, output_dir=args.output_dir or DATA_DIR)


if __name__ == "__main__":
    main()
