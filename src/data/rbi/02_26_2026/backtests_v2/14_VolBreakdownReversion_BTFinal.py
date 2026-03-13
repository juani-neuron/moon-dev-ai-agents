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
data['atr14'] = ta.atr(data['High'], data['Low'], data['Close'], length=14)
data['atr_sma'] = ta.sma(data['atr14'], length=50)
data['vol_sma20'] = ta.sma(data['Volume'], length=20)
data['ema20'] = ta.ema(data['Close'], length=20)
_bb = ta.bbands(data['Close'], length=20, std=2)
data['bb_lower'] = _bb.iloc[:, 0]
data['bb_mid'] = _bb.iloc[:, 1]
data['bb_upper'] = _bb.iloc[:, 2]


class VolBreakdownReversion(Strategy):
    """
    Edge: After a volatility spike (ATR >> its average), price has overshoot and tends
    to revert. Wait for the spike, then enter mean reversion toward EMA20.

    Entry: ATR > 2x its 50-period average (vol spike just happened), price is outside
    BB band (overextended), AND current candle is a reversal (close vs open direction
    is toward the mean).
    Exit: TP at BB mid (EMA20), SL at 2x ATR from entry.
    """

    def init(self):
        self.atr = self.I(lambda: self.data.df['atr14'], name='ATR14')
        self.atr_sma = self.I(lambda: self.data.df['atr_sma'], name='ATR_SMA')
        self.bb_lower = self.I(lambda: self.data.df['bb_lower'], name='BB_Lower')
        self.bb_mid = self.I(lambda: self.data.df['bb_mid'], name='BB_Mid')
        self.bb_upper = self.I(lambda: self.data.df['bb_upper'], name='BB_Upper')

    def next(self):
        if len(self.data) < 60:
            return

        if self.position:
            return

        atr_val = self.atr[-1]
        atr_avg = self.atr_sma[-1]
        if atr_val <= 0 or atr_avg <= 0:
            return

        vol_spike = atr_val > 2.0 * atr_avg

        if not vol_spike:
            return

        # Price below lower BB + bullish reversal candle → long toward mean
        if (self.data.Close[-1] < self.bb_lower[-1]
                and self.data.Close[-1] > self.data.Open[-1]):  # green candle
            sl = self.data.Close[-1] - 2 * atr_val
            tp = self.bb_mid[-1]
            if tp > self.data.Close[-1]:  # only if TP is above entry
                self.buy(sl=sl, tp=tp)

        # Price above upper BB + bearish reversal candle → short toward mean
        elif (self.data.Close[-1] > self.bb_upper[-1]
                and self.data.Close[-1] < self.data.Open[-1]):  # red candle
            sl = self.data.Close[-1] + 2 * atr_val
            tp = self.bb_mid[-1]
            if tp < self.data.Close[-1]:  # only if TP is below entry
                self.sell(sl=sl, tp=tp)


bt = Backtest(data, VolBreakdownReversion, cash=1_000_000, commission=.002)
stats = bt.run()
print(stats)
print(stats._strategy)
