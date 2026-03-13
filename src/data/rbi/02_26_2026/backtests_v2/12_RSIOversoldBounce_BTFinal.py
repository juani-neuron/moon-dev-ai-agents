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
data['rsi7'] = ta.rsi(data['Close'], length=7)
data['atr14'] = ta.atr(data['High'], data['Low'], data['Close'], length=14)
data['ema200'] = ta.ema(data['Close'], length=200)


class RSIOversoldBounce(Strategy):
    """
    Edge: Extreme RSI readings revert. RSI(7) < 20 is deeply oversold on 15m.
    Enter long when RSI recovers (crosses back above 20) = reversal candle.
    Filter: only buy above EMA200 (uptrend context — don't buy falling knives).

    TP: 1.5x ATR, SL: 1x ATR. Quick scalp.
    """

    def init(self):
        self.rsi = self.I(lambda: self.data.df['rsi7'], name='RSI7')
        self.atr = self.I(lambda: self.data.df['atr14'], name='ATR14')
        self.ema200 = self.I(lambda: self.data.df['ema200'], name='EMA200')

    def next(self):
        if len(self.data) < 210:
            return

        if self.position:
            return

        atr_val = self.atr[-1]
        if atr_val <= 0:
            return

        # Long: RSI was deeply oversold, now recovering, in uptrend
        if (self.rsi[-2] < 20
                and self.rsi[-1] > 20
                and self.data.Close[-1] > self.ema200[-1]):
            sl = self.data.Close[-1] - 1.0 * atr_val
            tp = self.data.Close[-1] + 1.5 * atr_val
            self.buy(sl=sl, tp=tp)

        # Short: RSI was deeply overbought, now falling, in downtrend
        elif (self.rsi[-2] > 80
                and self.rsi[-1] < 80
                and self.data.Close[-1] < self.ema200[-1]):
            sl = self.data.Close[-1] + 1.0 * atr_val
            tp = self.data.Close[-1] - 1.5 * atr_val
            self.sell(sl=sl, tp=tp)


bt = Backtest(data, RSIOversoldBounce, cash=1_000_000, commission=.002)
stats = bt.run()
print(stats)
print(stats._strategy)
