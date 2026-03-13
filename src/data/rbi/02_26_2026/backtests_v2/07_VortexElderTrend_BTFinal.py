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
_vortex = ta.vortex(data['High'], data['Low'], data['Close'], length=14)
data['vi_plus'] = _vortex.iloc[:, 0]
data['vi_minus'] = _vortex.iloc[:, 1]

# Elder Force Index = close change * volume, smoothed with EMA
data['efi'] = ta.efi(data['Close'], data['Volume'], length=13)
data['atr14'] = ta.atr(data['High'], data['Low'], data['Close'], length=14)
# Rolling highest/lowest close over 14 bars for trailing stop
data['highest_close_14'] = data['Close'].rolling(window=14).max()
data['lowest_close_14'] = data['Close'].rolling(window=14).min()


class VortexElderTrend(Strategy):
    """Vortex crossover + Elder Force Index. Trailing stop via 14-bar high/low - 2x ATR."""
    atr_mult = 2

    def init(self):
        self.vi_plus = self.I(lambda: self.data.df['vi_plus'], name='VI_Plus')
        self.vi_minus = self.I(lambda: self.data.df['vi_minus'], name='VI_Minus')
        self.efi = self.I(lambda: self.data.df['efi'], name='EFI')
        self.atr = self.I(lambda: self.data.df['atr14'], name='ATR14')
        self.hi14 = self.I(lambda: self.data.df['highest_close_14'], name='HiClose14')
        self.lo14 = self.I(lambda: self.data.df['lowest_close_14'], name='LoClose14')

    def next(self):
        if len(self.data) < 20:
            return

        if not self.position:
            # Long: VI+ crosses above VI- and EFI > 0
            if (self.vi_plus[-1] > self.vi_minus[-1]
                    and self.vi_plus[-2] <= self.vi_minus[-2]
                    and self.efi[-1] > 0):
                self.buy()

            # Short: VI- crosses above VI+ and EFI < 0
            elif (self.vi_minus[-1] > self.vi_plus[-1]
                    and self.vi_minus[-2] <= self.vi_plus[-2]
                    and self.efi[-1] < 0):
                self.sell()

        elif self.position.is_long:
            trail = self.hi14[-1] - self.atr_mult * self.atr[-1]
            if self.data.Close[-1] < trail:
                self.position.close()

        elif self.position.is_short:
            trail = self.lo14[-1] + self.atr_mult * self.atr[-1]
            if self.data.Close[-1] > trail:
                self.position.close()


bt = Backtest(data, VortexElderTrend, cash=1_000_000, commission=.002)
stats = bt.run()
print(stats)
print(stats._strategy)
