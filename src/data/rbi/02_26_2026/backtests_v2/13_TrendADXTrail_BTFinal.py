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
data['ema20'] = ta.ema(data['Close'], length=20)
data['ema50'] = ta.ema(data['Close'], length=50)
_adx = ta.adx(data['High'], data['Low'], data['Close'], length=14)
data['adx'] = _adx.iloc[:, 0]
data['di_plus'] = _adx.iloc[:, 1]
data['di_minus'] = _adx.iloc[:, 2]
data['atr14'] = ta.atr(data['High'], data['Low'], data['Close'], length=14)


class TrendADXTrail(Strategy):
    """
    Edge: Only trade when ADX confirms a genuine trend (>25). Use EMA crossover
    for direction, DI+/DI- for directional strength. Wide trailing stop lets
    winners run in trending markets.

    Entry: EMA20 > EMA50 + ADX > 25 + DI+ > DI- (long) / inverse (short)
    Exit: Trailing stop at 3x ATR below highest high (wide to capture trend moves)
    """
    trail_mult = 3.0

    def init(self):
        self.ema20 = self.I(lambda: self.data.df['ema20'], name='EMA20')
        self.ema50 = self.I(lambda: self.data.df['ema50'], name='EMA50')
        self.adx = self.I(lambda: self.data.df['adx'], name='ADX')
        self.di_plus = self.I(lambda: self.data.df['di_plus'], name='DI_Plus')
        self.di_minus = self.I(lambda: self.data.df['di_minus'], name='DI_Minus')
        self.atr = self.I(lambda: self.data.df['atr14'], name='ATR14')
        self._highest = 0
        self._lowest = float('inf')

    def next(self):
        if len(self.data) < 55:
            return

        if not self.position:
            self._highest = 0
            self._lowest = float('inf')
            trending = self.adx[-1] > 25

            if not trending:
                return

            # Long: EMA20 crosses above EMA50, DI+ > DI-
            if (self.ema20[-1] > self.ema50[-1]
                    and self.ema20[-2] <= self.ema50[-2]
                    and self.di_plus[-1] > self.di_minus[-1]):
                self._highest = self.data.High[-1]
                self.buy()

            # Short: EMA20 crosses below EMA50, DI- > DI+
            elif (self.ema20[-1] < self.ema50[-1]
                    and self.ema20[-2] >= self.ema50[-2]
                    and self.di_minus[-1] > self.di_plus[-1]):
                self._lowest = self.data.Low[-1]
                self.sell()

        elif self.position.is_long:
            self._highest = max(self._highest, self.data.High[-1])
            trail = self._highest - self.trail_mult * self.atr[-1]
            if self.data.Close[-1] < trail:
                self.position.close()

        elif self.position.is_short:
            self._lowest = min(self._lowest, self.data.Low[-1])
            trail = self._lowest + self.trail_mult * self.atr[-1]
            if self.data.Close[-1] > trail:
                self.position.close()


bt = Backtest(data, TrendADXTrail, cash=1_000_000, commission=.002)
stats = bt.run()
print(stats)
print(stats._strategy)
