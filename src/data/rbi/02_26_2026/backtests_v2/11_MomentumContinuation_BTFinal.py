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
data['atr14'] = ta.atr(data['High'], data['Low'], data['Close'], length=14)
data['vol_sma20'] = ta.sma(data['Volume'], length=20)
data['ema50'] = ta.ema(data['Close'], length=50)
data['body_size'] = abs(data['Close'] - data['Open'])


class MomentumContinuation(Strategy):
    """
    Edge: After an abnormally large candle with high volume, price tends to continue
    in that direction for a few bars (momentum). Enter in the direction of the big candle.

    Entry: candle body > 2x ATR AND volume > 2x average AND price aligned with EMA50 trend
    Exit: 1.5x ATR TP, 1x ATR SL (favorable R:R because momentum gives >50% WR)
    """
    atr_body_mult = 2.0
    vol_mult = 2.0
    sl_atr = 1.0
    tp_atr = 1.5

    def init(self):
        self.atr = self.I(lambda: self.data.df['atr14'], name='ATR14')
        self.vol_sma = self.I(lambda: self.data.df['vol_sma20'], name='Vol_SMA20')
        self.ema50 = self.I(lambda: self.data.df['ema50'], name='EMA50')
        self.body = self.I(lambda: self.data.df['body_size'], name='Body')

    def next(self):
        if len(self.data) < 55:
            return

        if self.position:
            return

        atr_val = self.atr[-1]
        if atr_val <= 0:
            return

        big_candle = self.body[-1] > self.atr_body_mult * atr_val
        high_vol = self.data.Volume[-1] > self.vol_mult * self.vol_sma[-1]

        if not (big_candle and high_vol):
            return

        bullish = self.data.Close[-1] > self.data.Open[-1]
        bearish = self.data.Close[-1] < self.data.Open[-1]

        # Only trade in EMA trend direction
        if bullish and self.data.Close[-1] > self.ema50[-1]:
            sl = self.data.Close[-1] - self.sl_atr * atr_val
            tp = self.data.Close[-1] + self.tp_atr * atr_val
            self.buy(sl=sl, tp=tp)

        elif bearish and self.data.Close[-1] < self.ema50[-1]:
            sl = self.data.Close[-1] + self.sl_atr * atr_val
            tp = self.data.Close[-1] - self.tp_atr * atr_val
            self.sell(sl=sl, tp=tp)


bt = Backtest(data, MomentumContinuation, cash=1_000_000, commission=.002)
stats = bt.run()
print(stats)
print(stats._strategy)
