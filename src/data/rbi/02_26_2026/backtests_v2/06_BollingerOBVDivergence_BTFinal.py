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
data['obv'] = ta.obv(data['Close'], data['Volume'])
data['atr14'] = ta.atr(data['High'], data['Low'], data['Close'], length=14)

# OBV divergence: bullish = price near 14-bar low but OBV above its 14-bar low
data['price_low_14'] = data['Low'].rolling(window=14).min()
data['obv_low_14'] = data['obv'].rolling(window=14).min()
data['price_high_14'] = data['High'].rolling(window=14).max()
data['obv_high_14'] = data['obv'].rolling(window=14).max()

# Stricter divergence: price makes new low but OBV must be significantly higher than its low
data['obv_pct_above_low'] = (data['obv'] - data['obv_low_14']) / (data['obv_high_14'] - data['obv_low_14'] + 1e-10)
data['obv_pct_below_high'] = (data['obv_high_14'] - data['obv']) / (data['obv_high_14'] - data['obv_low_14'] + 1e-10)

data['obv_bull_div'] = ((data['Low'] <= data['price_low_14'] * 1.002) &
                        (data['obv_pct_above_low'] > 0.3)).astype(int)
data['obv_bear_div'] = ((data['High'] >= data['price_high_14'] * 0.998) &
                        (data['obv_pct_below_high'] > 0.3)).astype(int)


class BollingerOBVDivergence(Strategy):
    """Long at lower BB + OBV bullish div. Short at upper BB + OBV bearish div. Exit at mid BB."""
    atr_stop_mult = 2.5

    def init(self):
        self.bb_lower = self.I(lambda: self.data.df['bb_lower'], name='BB_Lower')
        self.bb_mid = self.I(lambda: self.data.df['bb_mid'], name='BB_Mid')
        self.bb_upper = self.I(lambda: self.data.df['bb_upper'], name='BB_Upper')
        self.obv_bull = self.I(lambda: self.data.df['obv_bull_div'], name='OBV_Bull')
        self.obv_bear = self.I(lambda: self.data.df['obv_bear_div'], name='OBV_Bear')
        self.atr = self.I(lambda: self.data.df['atr14'], name='ATR14')

    def next(self):
        if len(self.data) < 30:
            return

        if not self.position:
            atr_val = self.atr[-1]
            if atr_val <= 0:
                return

            # Long: price touches lower BB + OBV bullish divergence
            if self.data.Close[-1] <= self.bb_lower[-1] and self.obv_bull[-1] > 0:
                sl = self.data.Close[-1] - self.atr_stop_mult * atr_val
                # TP at middle band, but clamp to at least 1x ATR
                tp_target = self.bb_mid[-1]
                tp_min = self.data.Close[-1] + 1.5 * atr_val
                tp = max(tp_target, tp_min)
                self.buy(sl=sl, tp=tp)

            # Short: price touches upper BB + OBV bearish divergence
            elif self.data.Close[-1] >= self.bb_upper[-1] and self.obv_bear[-1] > 0:
                sl = self.data.Close[-1] + self.atr_stop_mult * atr_val
                tp_target = self.bb_mid[-1]
                tp_max = self.data.Close[-1] - 1.5 * atr_val
                tp = min(tp_target, tp_max)
                self.sell(sl=sl, tp=tp)


bt = Backtest(data, BollingerOBVDivergence, cash=1_000_000, commission=.002)
stats = bt.run()
print(stats)
print(stats._strategy)
