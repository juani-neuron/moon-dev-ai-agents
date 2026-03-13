"""
FibroVolContraction Strategy — Fibonacci Retracement + ATR Contraction
Long only (trend following). Detects swing high/low, waits for pullback to
38.2%-61.8% fib zone while ATR is declining, enters on bounce.
Trend filter: price > SMA 50.
"""
import pandas as pd
import numpy as np
import talib
from backtesting import Backtest, Strategy
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))
DATA_PATH = os.path.join(PROJECT_ROOT, "src", "data", "rbi", "BTC-USD-15m-train.csv")


class FibroVolContraction(Strategy):
    sma_period = 50
    atr_period = 14
    swing_period = 40
    atr_decline_lookback = 10
    sl_atr_mult = 1.5
    tp_rr = 2.0

    def init(self):
        self.sma = self.I(talib.SMA, self.data.Close, timeperiod=self.sma_period)
        self.atr = self.I(talib.ATR, self.data.High, self.data.Low, self.data.Close,
                          timeperiod=self.atr_period)
        self.sw_high = self.I(talib.MAX, self.data.High, timeperiod=self.swing_period)
        self.sw_low = self.I(talib.MIN, self.data.Low, timeperiod=self.swing_period)

    def next(self):
        idx = len(self.data)
        if idx < self.sma_period + self.swing_period + 5:
            return

        price = self.data.Close[-1]
        sma_val = self.sma[-1]
        atr_val = self.atr[-1]
        sw_high = self.sw_high[-2]  # previous bar to avoid lookahead
        sw_low = self.sw_low[-2]

        if np.isnan(sma_val) or np.isnan(atr_val) or np.isnan(sw_high) or np.isnan(sw_low):
            return
        if atr_val <= 0 or sw_high <= sw_low:
            return

        if self.position:
            return

        # Trend filter: price above SMA
        if price <= sma_val:
            return

        # Fibonacci zone: 38.2% to 61.8% retracement from swing low to swing high
        fib_618 = sw_high - 0.618 * (sw_high - sw_low)  # deeper retracement
        fib_382 = sw_high - 0.382 * (sw_high - sw_low)  # shallower retracement

        # Price must be in the fib zone (between 38.2% and 61.8% retracement)
        if not (fib_618 <= price <= fib_382):
            return

        # ATR contraction: current ATR < average ATR over lookback
        lb = self.atr_decline_lookback
        atr_values = [self.atr[-i] for i in range(1, lb + 1)]
        if any(np.isnan(v) for v in atr_values):
            return
        atr_avg = np.mean(atr_values)
        if atr_val >= atr_avg:
            return

        # Bullish bounce: current close > previous close
        if self.data.Close[-1] > self.data.Close[-2]:
            sl = price - self.sl_atr_mult * atr_val
            tp = price + self.tp_rr * self.sl_atr_mult * atr_val
            if sl < price:
                self.buy(sl=sl, tp=tp)


if __name__ == "__main__":
    data = pd.read_csv(DATA_PATH)
    data.columns = data.columns.str.strip()
    data = data.rename(columns={
        'datetime': 'Date', 'open': 'Open', 'high': 'High',
        'low': 'Low', 'close': 'Close', 'volume': 'Volume'
    })
    data['Date'] = pd.to_datetime(data['Date'])
    data = data.set_index('Date')
    data = data.drop(columns=[c for c in data.columns if 'unnamed' in c.lower()], errors='ignore')

    bt = Backtest(data, FibroVolContraction, cash=1_000_000, commission=0.002)
    stats = bt.run()
    print(stats)
