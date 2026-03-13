import os
import pandas as pd
import pandas_ta as ta
import numpy as np
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
# Rolling min over 1440 bars (30 days of 15m candles), shift to avoid lookahead
data['bb_width_min'] = data['bb_width'].rolling(window=1440, min_periods=100).min().shift(1)
data['atr14'] = ta.atr(data['High'], data['Low'], data['Close'], length=14)
data['rsi14'] = ta.rsi(data['Close'], length=14)

# RSI divergence detection: bullish = price lower low, RSI higher low over 14 bars
data['price_low_14'] = data['Low'].rolling(window=14).min()
data['rsi_low_14'] = data['rsi14'].rolling(window=14).min()
data['price_high_14'] = data['High'].rolling(window=14).max()
data['rsi_high_14'] = data['rsi14'].rolling(window=14).max()

# Bullish: current low near 14-bar low AND current RSI > 14-bar RSI low
data['bull_div'] = ((data['Low'] <= data['price_low_14'] * 1.005) &
                    (data['rsi14'] > data['rsi_low_14'] + 3)).astype(int)
# Bearish: current high near 14-bar high AND current RSI < 14-bar RSI high
data['bear_div'] = ((data['High'] >= data['price_high_14'] * 0.995) &
                    (data['rsi14'] < data['rsi_high_14'] - 3)).astype(int)


class VolSqueezeDivergence(Strategy):
    """BB squeeze (30-day min) + RSI divergence + breakout. ATR SL/TP."""
    atr_sl_mult = 2
    atr_tp_mult = 4

    def init(self):
        self.bb_upper = self.I(lambda: self.data.df['bb_upper'], name='BB_Upper')
        self.bb_lower = self.I(lambda: self.data.df['bb_lower'], name='BB_Lower')
        self.bb_width = self.I(lambda: self.data.df['bb_width'], name='BB_Width')
        self.bb_width_min = self.I(lambda: self.data.df['bb_width_min'], name='BB_Width_Min')
        self.atr = self.I(lambda: self.data.df['atr14'], name='ATR14')
        self.bull_div = self.I(lambda: self.data.df['bull_div'], name='Bull_Div')
        self.bear_div = self.I(lambda: self.data.df['bear_div'], name='Bear_Div')

    def next(self):
        if len(self.data) < 1500:
            return

        if not self.position:
            squeeze = self.bb_width[-1] <= self.bb_width_min[-1] * 1.1  # within 10% of min
            atr_val = self.atr[-1]

            # Long: squeeze + close above upper BB + bullish RSI divergence
            if (squeeze
                    and self.data.Close[-1] > self.bb_upper[-1]
                    and self.bull_div[-1] > 0):
                sl = self.data.Close[-1] - self.atr_sl_mult * atr_val
                tp = self.data.Close[-1] + self.atr_tp_mult * atr_val
                self.buy(sl=sl, tp=tp)

            # Short: squeeze + close below lower BB + bearish RSI divergence
            elif (squeeze
                    and self.data.Close[-1] < self.bb_lower[-1]
                    and self.bear_div[-1] > 0):
                sl = self.data.Close[-1] + self.atr_sl_mult * atr_val
                tp = self.data.Close[-1] - self.atr_tp_mult * atr_val
                self.sell(sl=sl, tp=tp)


bt = Backtest(data, VolSqueezeDivergence, cash=1_000_000, commission=.002)
stats = bt.run()
print(stats)
print(stats._strategy)
