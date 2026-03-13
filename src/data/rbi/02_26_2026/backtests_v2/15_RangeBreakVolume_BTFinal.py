import os
import pandas as pd
import pandas_ta as ta
from backtesting import Backtest, Strategy

data_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'src', 'data', 'rbi', 'BTC-USD-15m-train.csv')
data_path = os.path.normpath(data_path)
data = pd.read_csv(data_path)

data.columns = data.columns.str.strip().str.lower()
data = data.drop(columns=[col for col in data.columns if 'unnamed' in col.lower()])
data.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, inplace=True)
data['datetime'] = pd.to_datetime(data['datetime'])
data.set_index('datetime', inplace=True)

# Pre-compute
# 96-bar high/low = 1 day range on 15m
data['range_high'] = data['High'].rolling(window=96).max().shift(1)
data['range_low'] = data['Low'].rolling(window=96).min().shift(1)
data['vol_sma96'] = ta.sma(data['Volume'], length=96)
data['atr14'] = ta.atr(data['High'], data['Low'], data['Close'], length=14)
data['ema200'] = ta.ema(data['Close'], length=200)


class RangeBreakVolume(Strategy):
    """
    Edge: After consolidation (1-day range), breakout with high volume tends to follow through.
    Only take breakouts in the direction of the longer trend (EMA200).

    Entry: Close breaks 1-day high/low + volume > 2x daily average + EMA200 trend filter
    Exit: 1.5x ATR SL, 3x ATR TP (2:1 RR, needs >35% WR)
    """
    vol_mult = 2.0
    sl_atr = 1.5
    tp_atr = 3.0

    def init(self):
        self.range_high = self.I(lambda: self.data.df['range_high'], name='Range_High')
        self.range_low = self.I(lambda: self.data.df['range_low'], name='Range_Low')
        self.vol_sma = self.I(lambda: self.data.df['vol_sma96'], name='Vol_SMA96')
        self.atr = self.I(lambda: self.data.df['atr14'], name='ATR14')
        self.ema200 = self.I(lambda: self.data.df['ema200'], name='EMA200')

    def next(self):
        if len(self.data) < 210:
            return

        if self.position:
            return

        atr_val = self.atr[-1]
        if atr_val <= 0:
            return

        high_vol = self.data.Volume[-1] > self.vol_mult * self.vol_sma[-1]
        if not high_vol:
            return

        # Long breakout: close > 1-day high, uptrend
        if (self.data.Close[-1] > self.range_high[-1]
                and self.data.Close[-1] > self.ema200[-1]):
            sl = self.data.Close[-1] - self.sl_atr * atr_val
            tp = self.data.Close[-1] + self.tp_atr * atr_val
            self.buy(sl=sl, tp=tp)

        # Short breakout: close < 1-day low, downtrend
        elif (self.data.Close[-1] < self.range_low[-1]
                and self.data.Close[-1] < self.ema200[-1]):
            sl = self.data.Close[-1] + self.sl_atr * atr_val
            tp = self.data.Close[-1] - self.tp_atr * atr_val
            self.sell(sl=sl, tp=tp)


bt = Backtest(data, RangeBreakVolume, cash=1_000_000, commission=.002)
stats = bt.run()
print(stats)
print(stats._strategy)
