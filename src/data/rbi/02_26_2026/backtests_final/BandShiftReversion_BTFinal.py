"""
BandShiftReversion Strategy — Bollinger Band Shift Mean Reversion
Long only. Enters when price touches lower BB AND lower BB is above the 20 SMA.
SL: 2x ATR below entry. Exit: price touches middle BB (20 SMA).
"""
import pandas as pd
import numpy as np
import talib
from backtesting import Backtest, Strategy
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))
DATA_PATH = os.path.join(PROJECT_ROOT, "src", "data", "rbi", "BTC-USD-15m-train.csv")


def bb_upper(close, period, std):
    u, _, _ = talib.BBANDS(close, timeperiod=period, nbdevup=std, nbdevdn=std)
    return u


def bb_mid(close, period, std):
    _, m, _ = talib.BBANDS(close, timeperiod=period, nbdevup=std, nbdevdn=std)
    return m


def bb_lower(close, period, std):
    _, _, l = talib.BBANDS(close, timeperiod=period, nbdevup=std, nbdevdn=std)
    return l


class BandShiftReversion(Strategy):
    bb_period = 20
    bb_std = 2
    atr_period = 14
    sl_atr_mult = 2.0

    def init(self):
        self.bb_upper = self.I(bb_upper, self.data.Close, self.bb_period, self.bb_std)
        self.bb_mid = self.I(bb_mid, self.data.Close, self.bb_period, self.bb_std)
        self.bb_lower = self.I(bb_lower, self.data.Close, self.bb_period, self.bb_std)
        self.sma = self.I(talib.SMA, self.data.Close, timeperiod=self.bb_period)
        self.atr = self.I(talib.ATR, self.data.High, self.data.Low, self.data.Close,
                          timeperiod=self.atr_period)

    def next(self):
        if len(self.data) < self.bb_period + 5:
            return

        price = self.data.Close[-1]
        lower = self.bb_lower[-1]
        mid = self.bb_mid[-1]
        sma = self.sma[-1]
        atr_val = self.atr[-1]

        if np.isnan(lower) or np.isnan(sma) or np.isnan(atr_val) or atr_val <= 0:
            return

        # Exit: price reaches middle band
        if self.position.is_long:
            if price >= mid:
                self.position.close()
                return

        if self.position:
            return

        # Entry: price <= lower BB (oversold) AND bands are narrow (contraction)
        # The original "lower BB > SMA" is geometrically impossible with standard BB.
        # Reinterpret: enter when price touches lower BB and the BB width is tight,
        # indicating a "compressed" band structure favorable for mean reversion.
        bb_width = (self.bb_upper[-1] - lower) / mid if mid > 0 else 999
        prev_bb_width = (self.bb_upper[-2] - self.bb_lower[-2]) / self.bb_mid[-2] if self.bb_mid[-2] > 0 else 999
        # Band contraction: current width < previous width (bands tightening)
        if price <= lower and bb_width < prev_bb_width:
            sl = price - self.sl_atr_mult * atr_val
            if sl < price:
                self.buy(sl=sl)


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

    bt = Backtest(data, BandShiftReversion, cash=1_000_000, commission=0.002)
    stats = bt.run()
    print(stats)
