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
# Donchian channel: 80-period high/low (20 days on 15m = 20*96 but spec says 80)
data['donch_high'] = data['High'].rolling(window=80).max().shift(1)  # previous 80 bars
data['donch_low'] = data['Low'].rolling(window=80).min().shift(1)
_adx = ta.adx(data['High'], data['Low'], data['Close'], length=14)
data['adx'] = _adx.iloc[:, 0]  # ADX line
data['vol_sma40'] = ta.sma(data['Volume'], length=40)
data['atr14'] = ta.atr(data['High'], data['Low'], data['Close'], length=14)


class ADXVolumeBreakout(Strategy):
    """Donchian breakout + ADX>25 + volume above average. ATR-based SL, 3:1 RR."""

    def init(self):
        self.donch_high = self.I(lambda: self.data.df['donch_high'], name='Donch_High')
        self.donch_low = self.I(lambda: self.data.df['donch_low'], name='Donch_Low')
        self.adx = self.I(lambda: self.data.df['adx'], name='ADX')
        self.vol_sma = self.I(lambda: self.data.df['vol_sma40'], name='Vol_SMA40')
        self.atr = self.I(lambda: self.data.df['atr14'], name='ATR14')

    def next(self):
        if len(self.data) < 90:
            return

        if not self.position:
            adx_ok = self.adx[-1] > 25
            vol_ok = self.data.Volume[-1] > self.vol_sma[-1]
            atr_val = self.atr[-1]

            if atr_val <= 0:
                return

            # Long breakout
            if self.data.Close[-1] > self.donch_high[-1] and adx_ok and vol_ok:
                sl = self.data.Close[-1] - 1.5 * atr_val
                tp = self.data.Close[-1] + 4.5 * atr_val
                self.buy(sl=sl, tp=tp)

            # Short breakout
            elif self.data.Close[-1] < self.donch_low[-1] and adx_ok and vol_ok:
                sl = self.data.Close[-1] + 1.5 * atr_val
                tp = self.data.Close[-1] - 4.5 * atr_val
                self.sell(sl=sl, tp=tp)


bt = Backtest(data, ADXVolumeBreakout, cash=1_000_000, commission=.002)
stats = bt.run()
print(stats)
print(stats._strategy)
