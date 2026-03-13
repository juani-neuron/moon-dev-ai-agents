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
data['sma50'] = ta.sma(data['Close'], length=50)
data['sma200'] = ta.sma(data['Close'], length=200)
data['vol_sma20'] = ta.sma(data['Volume'], length=20)
data['atr14'] = ta.atr(data['High'], data['Low'], data['Close'], length=14)


class GoldenCrossVolume(Strategy):
    """Long on golden cross + volume spike. Short on death cross. ATR stop + trailing stop."""
    trailing_pct = 0.05
    atr_mult = 2

    def init(self):
        self.sma50 = self.I(lambda: self.data.df['sma50'], name='SMA50')
        self.sma200 = self.I(lambda: self.data.df['sma200'], name='SMA200')
        self.vol_sma = self.I(lambda: self.data.df['vol_sma20'], name='Vol_SMA20')
        self.atr = self.I(lambda: self.data.df['atr14'], name='ATR14')
        self._highest = 0
        self._lowest = float('inf')

    def next(self):
        if len(self.data) < 210:
            return

        if not self.position:
            self._highest = 0
            self._lowest = float('inf')
            vol_ok = self.data.Volume[-1] > 1.5 * self.vol_sma[-1]

            # Golden cross
            if (self.sma50[-1] > self.sma200[-1]
                    and self.sma50[-2] <= self.sma200[-2]
                    and vol_ok):
                sl = self.data.Close[-1] - self.atr_mult * self.atr[-1]
                self.buy(sl=sl)

            # Death cross
            elif (self.sma50[-1] < self.sma200[-1]
                    and self.sma50[-2] >= self.sma200[-2]
                    and vol_ok):
                sl = self.data.Close[-1] + self.atr_mult * self.atr[-1]
                self.sell(sl=sl)

        elif self.position.is_long:
            self._highest = max(self._highest, self.data.Close[-1])
            if self.data.Close[-1] < self._highest * (1 - self.trailing_pct):
                self.position.close()

        elif self.position.is_short:
            self._lowest = min(self._lowest, self.data.Close[-1])
            if self.data.Close[-1] > self._lowest * (1 + self.trailing_pct):
                self.position.close()


bt = Backtest(data, GoldenCrossVolume, cash=1_000_000, commission=.002)
stats = bt.run()
print(stats)
print(stats._strategy)
