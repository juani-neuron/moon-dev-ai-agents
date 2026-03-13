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
# Fisher Transform
_fisher = ta.fisher(data['High'], data['Low'], length=10)
data['fisher'] = _fisher.iloc[:, 0]

# Vortex
_vortex = ta.vortex(data['High'], data['Low'], data['Close'], length=14)
data['vi_plus'] = _vortex.iloc[:, 0]
data['vi_minus'] = _vortex.iloc[:, 1]

# ADX
_adx = ta.adx(data['High'], data['Low'], data['Close'], length=14)
data['adx'] = _adx.iloc[:, 0]

# Volume SMA
data['vol_sma20'] = ta.sma(data['Volume'], length=20)
data['atr14'] = ta.atr(data['High'], data['Low'], data['Close'], length=14)


class FisherVortexDivergence(Strategy):
    """Fisher reversal against Vortex trend + volume. Exit when ADX drops < 25."""
    atr_mult = 2

    def init(self):
        self.fisher = self.I(lambda: self.data.df['fisher'], name='Fisher')
        self.vi_plus = self.I(lambda: self.data.df['vi_plus'], name='VI_Plus')
        self.vi_minus = self.I(lambda: self.data.df['vi_minus'], name='VI_Minus')
        self.adx = self.I(lambda: self.data.df['adx'], name='ADX')
        self.vol_sma = self.I(lambda: self.data.df['vol_sma20'], name='Vol_SMA20')
        self.atr = self.I(lambda: self.data.df['atr14'], name='ATR14')

    def next(self):
        if len(self.data) < 25:
            return

        if not self.position:
            vol_ok = self.data.Volume[-1] > self.vol_sma[-1]

            # Fisher turns up (reversal from down) while Vortex is bearish → contrarian long
            fisher_turns_up = (self.fisher[-3] > self.fisher[-2] and self.fisher[-2] < self.fisher[-1])
            vortex_bearish = self.vi_minus[-1] > self.vi_plus[-1]

            # Fisher turns down while Vortex is bullish → contrarian short
            fisher_turns_down = (self.fisher[-3] < self.fisher[-2] and self.fisher[-2] > self.fisher[-1])
            vortex_bullish = self.vi_plus[-1] > self.vi_minus[-1]

            if fisher_turns_up and vortex_bearish and vol_ok:
                sl = self.data.Close[-1] - self.atr_mult * self.atr[-1]
                tp = self.data.Close[-1] + self.atr_mult * self.atr[-1]
                self.buy(sl=sl, tp=tp)

            elif fisher_turns_down and vortex_bullish and vol_ok:
                sl = self.data.Close[-1] + self.atr_mult * self.atr[-1]
                tp = self.data.Close[-1] - self.atr_mult * self.atr[-1]
                self.sell(sl=sl, tp=tp)

        else:
            # Exit when ADX flattens below 25
            if self.adx[-1] < 25 and self.adx[-2] > self.adx[-1]:
                self.position.close()


bt = Backtest(data, FisherVortexDivergence, cash=1_000_000, commission=.002)
stats = bt.run()
print(stats)
print(stats._strategy)
