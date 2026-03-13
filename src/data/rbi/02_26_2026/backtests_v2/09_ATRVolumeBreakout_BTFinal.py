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

# Pre-compute indicators
data['atr20'] = ta.atr(data['High'], data['Low'], data['Close'], length=20)
# 90-day max of ATR on 15m = 90*24*4 = 8640 bars. Use shift(1) to avoid lookahead.
data['atr20_max_90d'] = data['atr20'].rolling(window=8640, min_periods=360).max().shift(1)
data['vol_sma30'] = ta.sma(data['Volume'], length=30)


class ATRVolumeBreakout(Strategy):
    """Enter when ATR > 90-day ATR max + volume spike. Bullish/bearish by candle color. 2:1 RR."""
    risk_mult = 2
    reward_mult = 4

    def init(self):
        self.atr = self.I(lambda: self.data.df['atr20'], name='ATR20')
        self.atr_max = self.I(lambda: self.data.df['atr20_max_90d'], name='ATR20_Max90d')
        self.vol_sma = self.I(lambda: self.data.df['vol_sma30'], name='Vol_SMA30')

    def next(self):
        if len(self.data) < 8700:
            return

        if not self.position:
            atr_breakout = self.atr[-1] > self.atr_max[-1]
            vol_ok = self.data.Volume[-1] > self.vol_sma[-1]

            if not (atr_breakout and vol_ok):
                return

            atr_val = self.atr[-1]

            # Bullish candle → long
            if self.data.Close[-1] > self.data.Open[-1]:
                sl = self.data.Close[-1] - self.risk_mult * atr_val
                tp = self.data.Close[-1] + self.reward_mult * atr_val
                self.buy(sl=sl, tp=tp)

            # Bearish candle → short
            elif self.data.Close[-1] < self.data.Open[-1]:
                sl = self.data.Close[-1] + self.risk_mult * atr_val
                tp = self.data.Close[-1] - self.reward_mult * atr_val
                self.sell(sl=sl, tp=tp)


bt = Backtest(data, ATRVolumeBreakout, cash=1_000_000, commission=.002)
stats = bt.run()
print(stats)
print(stats._strategy)
