"""
FibonacciDivergence Strategy - Moon Dev
Using pandas_ta instead of talib
"""
import pandas as pd
import numpy as np
import pandas_ta as ta
import os
from backtesting import Backtest, Strategy

# Load and clean data
DATA_PATH = os.path.join(os.path.dirname(__file__), 'BTC-USD-15m.csv')
data = pd.read_csv(DATA_PATH)
data.columns = data.columns.str.strip().str.lower()
data = data.drop(columns=[col for col in data.columns if 'unnamed' in col.lower()])
data = data.rename(columns={
    'open': 'Open',
    'high': 'High',
    'low': 'Low',
    'close': 'Close',
    'volume': 'Volume'
})
data = data.set_index(pd.to_datetime(data['datetime']))
data = data[['Open', 'High', 'Low', 'Close', 'Volume']]


def calc_ema(close, period):
    """Calculate EMA using pandas_ta"""
    return ta.ema(pd.Series(close), length=period)


def calc_macd(close):
    """Calculate MACD using pandas_ta, returns (macd, signal, hist)"""
    macd_df = ta.macd(pd.Series(close), fast=12, slow=26, signal=9)
    if macd_df is not None:
        macd_line = macd_df.iloc[:, 0].values  # MACD line
        signal_line = macd_df.iloc[:, 2].values  # Signal line
        hist = macd_df.iloc[:, 1].values  # Histogram
        return macd_line, signal_line, hist
    return None, None, None


class FibonacciDivergence(Strategy):
    piv_length = 5
    risk_per_trade = 0.01
    fib_ratios = [0.382, 0.5, 0.618]
    fib_786 = 0.786
    tolerance_pct = 0.02
    lookback_div = 20
    prev_lookback = 40

    last_swing_high = 0.0
    last_swing_low = float('inf')
    last_swing_high_bar = -1
    last_swing_low_bar = -1
    fib_long_levels = []
    fib_short_levels = []

    def init(self):
        self.ema200 = self.I(calc_ema, self.data.Close, 200)
        macd_line, signal_line, hist = calc_macd(self.data.Close)
        self.macd_line = self.I(lambda: macd_line)
        self.signal_line = self.I(lambda: signal_line)
        self.hist = self.I(lambda: hist)
        print("Moon Dev: Initializing FibonacciDivergence Strategy")

    def calculate_fib_retracement_long(self, swing_low, swing_high):
        diff = swing_high - swing_low
        return [swing_low + diff * r for r in self.fib_ratios]

    def calculate_fib_retracement_short(self, swing_high, swing_low):
        diff = swing_high - swing_low
        return [swing_high - diff * r for r in self.fib_ratios]

    def is_near_fib(self, levels, price):
        tolerance = price * self.tolerance_pct
        return any(abs(price - level) <= tolerance for level in levels)

    def is_bullish_divergence(self):
        i = len(self.data) - 1
        if i < self.prev_lookback:
            return False
        start_prev = max(0, i + 1 - self.prev_lookback)
        end_prev = max(0, i + 1 - self.lookback_div)
        start_recent = end_prev
        end_recent = i + 1
        recent_lows = self.data.Low[start_recent:end_recent]
        recent_hist = self.hist[start_recent:end_recent]
        if len(recent_lows) == 0:
            return False
        recent_low_idx = np.argmin(recent_lows)
        recent_price_low = recent_lows[recent_low_idx]
        recent_hist_low = recent_hist[recent_low_idx]

        prev_lows = self.data.Low[start_prev:end_prev]
        prev_hist = self.hist[start_prev:end_prev]
        if len(prev_lows) == 0:
            return False
        prev_low_idx = np.argmin(prev_lows)
        prev_price_low = prev_lows[prev_low_idx]
        prev_hist_low = prev_hist[prev_low_idx]

        return (recent_price_low < prev_price_low) and (recent_hist_low > prev_hist_low)

    def is_bearish_divergence(self):
        i = len(self.data) - 1
        if i < self.prev_lookback:
            return False
        start_prev = max(0, i + 1 - self.prev_lookback)
        end_prev = max(0, i + 1 - self.lookback_div)
        start_recent = end_prev
        end_recent = i + 1
        recent_highs = self.data.High[start_recent:end_recent]
        recent_hist = self.hist[start_recent:end_recent]
        if len(recent_highs) == 0:
            return False
        recent_high_idx = np.argmax(recent_highs)
        recent_price_high = recent_highs[recent_high_idx]
        recent_hist_high = recent_hist[recent_high_idx]

        prev_highs = self.data.High[start_prev:end_prev]
        prev_hist = self.hist[start_prev:end_prev]
        if len(prev_highs) == 0:
            return False
        prev_high_idx = np.argmax(prev_highs)
        prev_price_high = prev_highs[prev_high_idx]
        prev_hist_high = prev_hist[prev_high_idx]

        return (recent_price_high > prev_price_high) and (recent_hist_high < prev_hist_high)

    def next(self):
        i = len(self.data) - 1
        if i < 200 + self.piv_length * 2:
            return

        current_bar = i
        close = self.data.Close[i]
        high = self.data.High[i]
        low = self.data.Low[i]

        uptrend = close > self.ema200[i]
        downtrend = close < self.ema200[i]

        # Check for confirmed pivot high
        pivot_high_bar = current_bar - self.piv_length
        if pivot_high_bar >= self.piv_length:
            left_start = pivot_high_bar - self.piv_length
            left_highs = self.data.High[left_start:pivot_high_bar]
            right_highs = self.data.High[pivot_high_bar + 1:current_bar + 1]
            if len(right_highs) >= self.piv_length:
                pivot_high_price = self.data.High[pivot_high_bar]
                is_pivot_high = (
                    pivot_high_price >= left_highs.max() and
                    pivot_high_price >= right_highs.max()
                )
                if is_pivot_high and pivot_high_bar > self.last_swing_high_bar:
                    self.last_swing_high = pivot_high_price
                    self.last_swing_high_bar = pivot_high_bar
                    if self.last_swing_low_bar != -1 and self.last_swing_low < self.last_swing_high:
                        self.fib_long_levels = self.calculate_fib_retracement_long(
                            self.last_swing_low, self.last_swing_high
                        )

        # Check for confirmed pivot low
        pivot_low_bar = current_bar - self.piv_length
        if pivot_low_bar >= self.piv_length:
            left_start = pivot_low_bar - self.piv_length
            left_lows = self.data.Low[left_start:pivot_low_bar]
            right_lows = self.data.Low[pivot_low_bar + 1:current_bar + 1]
            if len(right_lows) >= self.piv_length:
                pivot_low_price = self.data.Low[pivot_low_bar]
                is_pivot_low = (
                    pivot_low_price <= left_lows.min() and
                    pivot_low_price <= right_lows.min()
                )
                if is_pivot_low and pivot_low_bar > self.last_swing_low_bar:
                    self.last_swing_low = pivot_low_price
                    self.last_swing_low_bar = pivot_low_bar
                    if self.last_swing_high_bar != -1 and self.last_swing_high > self.last_swing_low:
                        self.fib_short_levels = self.calculate_fib_retracement_short(
                            self.last_swing_high, self.last_swing_low
                        )

        # Long Entry Logic
        if (not self.position and uptrend and len(self.fib_long_levels) > 0 and
            self.last_swing_high_bar > self.last_swing_low_bar):
            diff_long = self.last_swing_high - self.last_swing_low
            fib_786_long = self.last_swing_low + diff_long * self.fib_786
            if close > fib_786_long:
                return
            if self.is_near_fib(self.fib_long_levels, close) and self.is_bullish_divergence():
                sl_long = min(fib_786_long, self.last_swing_low) * (1 - 0.01)
                price_risk_long = close - sl_long
                if price_risk_long > 0:
                    balance = self.equity
                    dollar_risk = balance * self.risk_per_trade
                    size_long = dollar_risk / price_risk_long
                    size_long = int(round(size_long))
                    if size_long > 0:
                        tp_long = close + 2 * price_risk_long
                        self.buy(size=size_long, sl=sl_long, tp=tp_long)
                        print(f"LONG ENTRY at {close:.2f}, Size: {size_long}, SL: {sl_long:.2f}, TP: {tp_long:.2f}")

        # Short Entry Logic
        if (not self.position and downtrend and len(self.fib_short_levels) > 0 and
            self.last_swing_low_bar > self.last_swing_high_bar):
            diff_short = self.last_swing_high - self.last_swing_low
            fib_786_short = self.last_swing_high - diff_short * self.fib_786
            if close < fib_786_short:
                return
            if self.is_near_fib(self.fib_short_levels, close) and self.is_bearish_divergence():
                sl_short = max(fib_786_short, self.last_swing_high) * (1 + 0.01)
                price_risk_short = sl_short - close
                if price_risk_short > 0:
                    balance = self.equity
                    dollar_risk = balance * self.risk_per_trade
                    size_short = dollar_risk / price_risk_short
                    size_short = int(round(size_short))
                    if size_short > 0:
                        tp_short = close - 2 * price_risk_short
                        self.sell(size=size_short, sl=sl_short, tp=tp_short)
                        print(f"SHORT ENTRY at {close:.2f}, Size: {size_short}, SL: {sl_short:.2f}, TP: {tp_short:.2f}")


# Run backtest
if __name__ == "__main__":
    print("\n" + "="*60)
    print("  FibonacciDivergence Backtest - Moon Dev")
    print("="*60 + "\n")

    bt = Backtest(data, FibonacciDivergence, cash=1000000, commission=0.001, exclusive_orders=True)
    stats = bt.run()

    print("\n" + "="*60)
    print("  RESULTS")
    print("="*60)
    print(f"  Return:           {stats['Return [%]']:.2f}%")
    print(f"  Buy & Hold:       {stats['Buy & Hold Return [%]']:.2f}%")
    print(f"  Max Drawdown:     {stats['Max. Drawdown [%]']:.2f}%")
    print(f"  Sharpe Ratio:     {stats['Sharpe Ratio']:.2f}" if stats['Sharpe Ratio'] else "  Sharpe Ratio:     N/A")
    print(f"  Win Rate:         {stats['Win Rate [%]']:.2f}%")
    print(f"  # Trades:         {stats['# Trades']}")
    print(f"  Avg Trade:        {stats['Avg. Trade [%]']:.2f}%")
    print(f"  Profit Factor:    {stats['Profit Factor']:.2f}" if stats['Profit Factor'] else "  Profit Factor:    N/A")
    print(f"  Final Equity:     ${stats['Equity Final [$]']:,.2f}")
    print("="*60 + "\n")

    # Uncomment to see full stats
    # print(stats)

    # Uncomment to plot
    # bt.plot()
