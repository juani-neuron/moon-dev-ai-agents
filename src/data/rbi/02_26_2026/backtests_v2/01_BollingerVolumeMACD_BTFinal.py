import os
import pandas as pd
import pandas_ta as ta
from backtesting import Backtest, Strategy

# Data path — 6 levels up from this file to project root
data_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'src', 'data', 'rbi', 'BTC-USD-15m-train.csv')
data_path = os.path.normpath(data_path)
data = pd.read_csv(data_path)

data.columns = data.columns.str.strip().str.lower()
data = data.drop(columns=[col for col in data.columns if 'unnamed' in col.lower()])
data.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, inplace=True)
data['datetime'] = pd.to_datetime(data['datetime'])
data.set_index('datetime', inplace=True)

# Pre-compute indicators on the full dataframe
_bb = ta.bbands(data['Close'], length=20, std=2)
data['bb_lower'] = _bb.iloc[:, 0]
data['bb_mid'] = _bb.iloc[:, 1]
data['bb_upper'] = _bb.iloc[:, 2]

_macd = ta.macd(data['Close'], fast=12, slow=26, signal=9)
data['macd_hist'] = _macd.iloc[:, 1]  # MACD histogram

data['vol_sma20'] = ta.sma(data['Volume'], length=20)


class BollingerVolumeMACD(Strategy):
    """Mean reversion: long near lower BB when MACD histogram turns bullish + volume. Exit at mid BB."""

    def init(self):
        self.bb_lower = self.I(lambda: self.data.df['bb_lower'], name='BB_Lower')
        self.bb_mid = self.I(lambda: self.data.df['bb_mid'], name='BB_Mid')
        self.macd_hist = self.I(lambda: self.data.df['macd_hist'], name='MACD_Hist')
        self.vol_sma = self.I(lambda: self.data.df['vol_sma20'], name='Vol_SMA20')
        self._touched_lower = 0

    def next(self):
        if len(self.data) < 30:
            return

        # Track if price touched lower BB in last 5 bars
        if self.data.Close[-1] <= self.bb_lower[-1]:
            self._touched_lower = 5

        if self._touched_lower > 0:
            self._touched_lower -= 1

        if not self.position:
            # Entry: price touched lower BB recently, volume spike, and MACD hist improving
            if (self._touched_lower > 0
                    and self.data.Volume[-1] > 1.5 * self.vol_sma[-1]
                    and self.macd_hist[-1] > self.macd_hist[-2]):
                self.buy()

        elif self.position.is_long:
            # Exit at middle BB
            if self.data.Close[-1] >= self.bb_mid[-1]:
                self.position.close()


bt = Backtest(data, BollingerVolumeMACD, cash=1_000_000, commission=.002)
stats = bt.run()
print(stats)
print(stats._strategy)
