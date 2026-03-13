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
_bb = ta.bbands(data['Close'], length=20, std=2)
data['bb_lower'] = _bb.iloc[:, 0]
data['bb_mid'] = _bb.iloc[:, 1]
data['bb_upper'] = _bb.iloc[:, 2]
data['bb_width'] = data['bb_upper'] - data['bb_lower']
data['bb_width_min20'] = data['bb_width'].rolling(window=20).min().shift(1)  # min over last 20, excluding current
data['atr14'] = ta.atr(data['High'], data['Low'], data['Close'], length=14)


class VolSqueezeBreakout(Strategy):
    """Enter when BB squeeze (narrowest 20 bars), price breaks upper/lower band. ATR SL/TP."""

    def init(self):
        self.bb_upper = self.I(lambda: self.data.df['bb_upper'], name='BB_Upper')
        self.bb_lower = self.I(lambda: self.data.df['bb_lower'], name='BB_Lower')
        self.bb_width = self.I(lambda: self.data.df['bb_width'], name='BB_Width')
        self.bb_width_min = self.I(lambda: self.data.df['bb_width_min20'], name='BB_Width_Min20')
        self.atr = self.I(lambda: self.data.df['atr14'], name='ATR14')

    def next(self):
        if len(self.data) < 30:
            return

        if not self.position:
            squeeze = self.bb_width[-1] <= self.bb_width_min[-1] * 1.05
            atr_val = self.atr[-1]
            if atr_val <= 0:
                return

            if squeeze and self.data.Close[-1] > self.bb_upper[-1]:
                sl = self.data.Close[-1] - 2 * atr_val
                tp = self.data.Close[-1] + 4 * atr_val
                self.buy(sl=sl, tp=tp)

            elif squeeze and self.data.Close[-1] < self.bb_lower[-1]:
                sl = self.data.Close[-1] + 2 * atr_val
                tp = self.data.Close[-1] - 4 * atr_val
                self.sell(sl=sl, tp=tp)


bt = Backtest(data, VolSqueezeBreakout, cash=1_000_000, commission=.002)
stats = bt.run()
print(stats)
print(stats._strategy)
