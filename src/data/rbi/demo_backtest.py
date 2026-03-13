"""
Moon Dev's Demo Backtest Script
Simple SMA Crossover Strategy for testing
"""

from backtesting import Backtest, Strategy
import pandas as pd
import pandas_ta as ta
import os

# Data path
DATA_PATH = os.path.join(os.path.dirname(__file__), 'BTC-USD-15m.csv')

class SMACrossover(Strategy):
    """Simple Moving Average Crossover Strategy"""

    # Parameters (can be optimized)
    fast_period = 10
    slow_period = 30

    def init(self):
        # Calculate SMAs using pandas_ta
        close = pd.Series(self.data.Close)
        self.fast_sma = self.I(lambda: ta.sma(close, self.fast_period))
        self.slow_sma = self.I(lambda: ta.sma(close, self.slow_period))

    def next(self):
        # Skip if not enough data
        if self.fast_sma[-1] is None or self.slow_sma[-1] is None:
            return

        # Buy signal: fast SMA crosses above slow SMA
        if self.fast_sma[-1] > self.slow_sma[-1] and self.fast_sma[-2] <= self.slow_sma[-2]:
            if not self.position:
                self.buy()

        # Sell signal: fast SMA crosses below slow SMA
        elif self.fast_sma[-1] < self.slow_sma[-1] and self.fast_sma[-2] >= self.slow_sma[-2]:
            if self.position:
                self.sell()


class RSIStrategy(Strategy):
    """RSI Overbought/Oversold Strategy"""

    rsi_period = 14
    oversold = 30
    overbought = 70

    def init(self):
        close = pd.Series(self.data.Close)
        self.rsi = self.I(lambda: ta.rsi(close, self.rsi_period))

    def next(self):
        if self.rsi[-1] is None:
            return

        # Buy when RSI is oversold
        if self.rsi[-1] < self.oversold:
            if not self.position:
                self.buy()

        # Sell when RSI is overbought
        elif self.rsi[-1] > self.overbought:
            if self.position:
                self.sell()


def load_data():
    """Load and prepare BTC data"""
    print(f"Loading data from: {DATA_PATH}")

    df = pd.read_csv(DATA_PATH)

    # Clean column names (remove spaces)
    df.columns = df.columns.str.strip()

    # Rename columns to match backtesting.py requirements
    df = df.rename(columns={
        'datetime': 'Date',
        'open': 'Open',
        'high': 'High',
        'low': 'Low',
        'close': 'Close',
        'volume': 'Volume'
    })

    # Set datetime index
    df['Date'] = pd.to_datetime(df['Date'])
    df = df.set_index('Date')

    print(f"Loaded {len(df)} candles from {df.index[0]} to {df.index[-1]}")
    return df


def run_backtest(strategy_class, cash=10000, commission=0.001):
    """Run backtest and display results"""

    df = load_data()

    print(f"\n{'='*60}")
    print(f"Running: {strategy_class.__name__}")
    print(f"{'='*60}")

    bt = Backtest(
        df,
        strategy_class,
        cash=cash,
        commission=commission,
        exclusive_orders=True
    )

    stats = bt.run()

    # Print key metrics
    print(f"\n Key Metrics:")
    print(f"  Return:        {stats['Return [%]']:.2f}%")
    print(f"  Max Drawdown:  {stats['Max. Drawdown [%]']:.2f}%")
    print(f"  Sharpe Ratio:  {stats['Sharpe Ratio']:.2f}" if stats['Sharpe Ratio'] else "  Sharpe Ratio:  N/A")
    print(f"  Win Rate:      {stats['Win Rate [%]']:.2f}%")
    print(f"  # Trades:      {stats['# Trades']}")
    print(f"  Profit Factor: {stats['Profit Factor']:.2f}" if stats['Profit Factor'] else "  Profit Factor: N/A")

    return bt, stats


def optimize_strategy(strategy_class, param_ranges):
    """Optimize strategy parameters"""

    df = load_data()

    print(f"\n{'='*60}")
    print(f"Optimizing: {strategy_class.__name__}")
    print(f"{'='*60}")

    bt = Backtest(
        df,
        strategy_class,
        cash=10000,
        commission=0.001,
        exclusive_orders=True
    )

    stats = bt.optimize(**param_ranges, maximize='Return [%]')

    print(f"\n Best Parameters:")
    for key, value in param_ranges.items():
        print(f"  {key}: {getattr(stats._strategy, key)}")

    print(f"\n Optimized Metrics:")
    print(f"  Return:        {stats['Return [%]']:.2f}%")
    print(f"  Max Drawdown:  {stats['Max. Drawdown [%]']:.2f}%")
    print(f"  # Trades:      {stats['# Trades']}")

    return bt, stats


if __name__ == "__main__":
    print("\n" + "="*60)
    print(" Moon Dev's Demo Backtest")
    print("="*60)

    # Run SMA Crossover
    bt1, stats1 = run_backtest(SMACrossover)

    # Run RSI Strategy
    bt2, stats2 = run_backtest(RSIStrategy)

    # Optimize SMA (optional - uncomment to run)
    # print("\n Optimizing SMA Strategy...")
    # bt_opt, stats_opt = optimize_strategy(
    #     SMACrossover,
    #     {
    #         'fast_period': range(5, 20, 5),
    #         'slow_period': range(20, 50, 10)
    #     }
    # )

    print("\n" + "="*60)
    print(" To view charts, uncomment bt.plot() below")
    print("="*60)

    # Uncomment to see interactive chart
    # bt1.plot()
    # bt2.plot()
