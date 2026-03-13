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
data['bb_bandwidth'] = (data['bb_upper'] - data['bb_lower']) / data['bb_mid']

# Bandwidth percentile rank over 100 bars
data['bw_pctrank'] = data['bb_bandwidth'].rolling(window=100).rank(pct=True) * 100

# Stochastic RSI
_srsi = ta.stochrsi(data['Close'], length=14, rsi_length=14, k=3, d=3)
data['stochrsi_k'] = _srsi.iloc[:, 0]
data['stochrsi_d'] = _srsi.iloc[:, 1]


class VolContractionMomentum(Strategy):
    """BB bandwidth < 20th percentile + Stochastic RSI cross. Exit at opposite BB or 2:1 RR."""
    sl_pct = 0.02
    tp_pct = 0.04

    def init(self):
        self.bb_upper = self.I(lambda: self.data.df['bb_upper'], name='BB_Upper')
        self.bb_lower = self.I(lambda: self.data.df['bb_lower'], name='BB_Lower')
        self.bw_pctrank = self.I(lambda: self.data.df['bw_pctrank'], name='BW_PctRank')
        self.srsi_k = self.I(lambda: self.data.df['stochrsi_k'], name='StochRSI_K')
        self.srsi_d = self.I(lambda: self.data.df['stochrsi_d'], name='StochRSI_D')

    def next(self):
        if len(self.data) < 120:
            return

        if not self.position:
            low_vol = self.bw_pctrank[-1] < 20

            # Long: low vol + StochRSI K crosses above D from below 20
            if (low_vol
                    and self.srsi_k[-1] > self.srsi_d[-1]
                    and self.srsi_k[-2] <= 20
                    and self.srsi_k[-1] > 20):
                sl = self.data.Close[-1] * (1 - self.sl_pct)
                tp = self.data.Close[-1] * (1 + self.tp_pct)
                self.buy(sl=sl, tp=tp)

            # Short: low vol + StochRSI K crosses below D from above 80
            elif (low_vol
                    and self.srsi_k[-1] < self.srsi_d[-1]
                    and self.srsi_k[-2] >= 80
                    and self.srsi_k[-1] < 80):
                sl = self.data.Close[-1] * (1 + self.sl_pct)
                tp = self.data.Close[-1] * (1 - self.tp_pct)
                self.sell(sl=sl, tp=tp)

        elif self.position.is_long:
            if self.data.Close[-1] >= self.bb_upper[-1]:
                self.position.close()

        elif self.position.is_short:
            if self.data.Close[-1] <= self.bb_lower[-1]:
                self.position.close()


bt = Backtest(data, VolContractionMomentum, cash=1_000_000, commission=.002)
stats = bt.run()
print(stats)
print(stats._strategy)
