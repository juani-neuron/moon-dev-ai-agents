"""
BandedReversal Strategy — RSI Bollinger Bands Mean Reversion
Enters when RSI crosses back inside its own Bollinger Bands, filtered by EMA trend.
Long: price > EMA50, RSI was below lower BB(RSI), crosses back above.
Short: price < EMA50, RSI was above upper BB(RSI), crosses back below.
Exit: RSI reaches opposite band.
"""
import pandas as pd
import numpy as np
import talib
from backtesting import Backtest, Strategy
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))
DATA_PATH = os.path.join(PROJECT_ROOT, "src", "data", "rbi", "BTC-USD-15m-train.csv")


def rsi_bb_upper(close, rsi_period, bb_period, bb_std):
    rsi = talib.RSI(close, timeperiod=rsi_period)
    upper, _, _ = talib.BBANDS(rsi, timeperiod=bb_period, nbdevup=bb_std, nbdevdn=bb_std)
    return upper


def rsi_bb_lower(close, rsi_period, bb_period, bb_std):
    rsi = talib.RSI(close, timeperiod=rsi_period)
    _, _, lower = talib.BBANDS(rsi, timeperiod=bb_period, nbdevup=bb_std, nbdevdn=bb_std)
    return lower


class BandedReversal(Strategy):
    rsi_period = 14
    bb_period = 20
    bb_std = 2
    ema_period = 50
    atr_period = 14
    sl_atr_mult = 2.0

    def init(self):
        self.rsi = self.I(talib.RSI, self.data.Close, timeperiod=self.rsi_period)
        self.rsi_upper = self.I(rsi_bb_upper, self.data.Close, self.rsi_period, self.bb_period, self.bb_std)
        self.rsi_lower = self.I(rsi_bb_lower, self.data.Close, self.rsi_period, self.bb_period, self.bb_std)
        self.ema = self.I(talib.EMA, self.data.Close, timeperiod=self.ema_period)
        self.atr = self.I(talib.ATR, self.data.High, self.data.Low, self.data.Close, timeperiod=self.atr_period)

    tp_atr_mult = 3.0

    def next(self):
        if len(self.data) < self.ema_period + 5:
            return

        price = self.data.Close[-1]
        rsi_now = self.rsi[-1]
        rsi_prev = self.rsi[-2]
        rsi_upper = self.rsi_upper[-1]
        rsi_lower = self.rsi_lower[-1]
        rsi_upper_prev = self.rsi_upper[-2]
        rsi_lower_prev = self.rsi_lower[-2]
        ema_val = self.ema[-1]
        atr_val = self.atr[-1]

        if np.isnan(rsi_now) or np.isnan(rsi_upper) or np.isnan(ema_val) or np.isnan(atr_val) or atr_val <= 0:
            return

        if self.position:
            return

        # Long: price > EMA, RSI was below lower BB and crosses back above
        if price > ema_val:
            if rsi_prev < rsi_lower_prev and rsi_now > rsi_lower:
                sl = price - self.sl_atr_mult * atr_val
                tp = price + self.tp_atr_mult * atr_val
                if sl < price:
                    self.buy(sl=sl, tp=tp)

        # Short: price < EMA, RSI was above upper BB and crosses back below
        elif price < ema_val:
            if rsi_prev > rsi_upper_prev and rsi_now < rsi_upper:
                sl = price + self.sl_atr_mult * atr_val
                tp = price - self.tp_atr_mult * atr_val
                if sl > price:
                    self.sell(sl=sl, tp=tp)


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

    bt = Backtest(data, BandedReversal, cash=1_000_000, commission=0.002)
    stats = bt.run()
    print(stats)
