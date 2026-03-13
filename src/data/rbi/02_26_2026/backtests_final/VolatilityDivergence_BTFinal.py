"""
VolatilityDivergence Strategy — Hidden Bullish/Bearish Divergence (Price vs ATR)
Long: price > EMA50, price makes higher low but ATR declining, breakout above swing high.
Short: price < EMA50, price makes lower high but ATR declining, breakdown below swing low.
"""
import pandas as pd
import numpy as np
import talib
from backtesting import Backtest, Strategy
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))
DATA_PATH = os.path.join(PROJECT_ROOT, "src", "data", "rbi", "BTC-USD-15m-train.csv")


class VolatilityDivergence(Strategy):
    ema_period = 50
    atr_period = 14
    swing_period = 20
    divergence_lookback = 10
    sl_atr_mult = 1.5
    tp_rr = 2.0

    def init(self):
        self.ema = self.I(talib.EMA, self.data.Close, timeperiod=self.ema_period)
        self.atr = self.I(talib.ATR, self.data.High, self.data.Low, self.data.Close,
                          timeperiod=self.atr_period)
        self.sw_high = self.I(talib.MAX, self.data.High, timeperiod=self.swing_period)
        self.sw_low = self.I(talib.MIN, self.data.Low, timeperiod=self.swing_period)

    def next(self):
        idx = len(self.data)
        if idx < self.ema_period + self.divergence_lookback + 5:
            return

        price = self.data.Close[-1]
        ema_val = self.ema[-1]
        atr_val = self.atr[-1]

        if np.isnan(ema_val) or np.isnan(atr_val) or atr_val <= 0:
            return

        if self.position:
            return

        lb = self.divergence_lookback
        half = lb // 2
        if half < 2:
            return

        # Hidden Bullish Divergence (long): price higher low, ATR declining
        if price > ema_val:
            first_half_low = min(self.data.Low[-(lb):-(half)])
            second_half_low = min(self.data.Low[-(half):])
            first_half_atr = np.mean([self.atr[-(lb) + i] for i in range(half)])
            second_half_atr = np.mean([self.atr[-(half) + i] for i in range(half)])

            if np.isnan(first_half_atr) or np.isnan(second_half_atr):
                return

            # Higher low in price + declining ATR
            if second_half_low > first_half_low and second_half_atr < first_half_atr:
                # Breakout above recent swing high (use -2 to avoid lookahead)
                sw_high_val = self.sw_high[-2]
                if not np.isnan(sw_high_val) and price > sw_high_val:
                    sl = price - self.sl_atr_mult * atr_val
                    tp = price + self.tp_rr * self.sl_atr_mult * atr_val
                    if sl < price:
                        self.buy(sl=sl, tp=tp)
                        return

        # Hidden Bearish Divergence (short): price lower high, ATR declining
        elif price < ema_val:
            first_half_high = max(self.data.High[-(lb):-(half)])
            second_half_high = max(self.data.High[-(half):])
            first_half_atr = np.mean([self.atr[-(lb) + i] for i in range(half)])
            second_half_atr = np.mean([self.atr[-(half) + i] for i in range(half)])

            if np.isnan(first_half_atr) or np.isnan(second_half_atr):
                return

            # Lower high in price + declining ATR
            if second_half_high < first_half_high and second_half_atr < first_half_atr:
                sw_low_val = self.sw_low[-2]
                if not np.isnan(sw_low_val) and price < sw_low_val:
                    sl = price + self.sl_atr_mult * atr_val
                    tp = price - self.tp_rr * self.sl_atr_mult * atr_val
                    if sl > price:
                        self.sell(sl=sl, tp=tp)


if __name__ == "__main__":
    data = pd.read_csv(DATA_PATH)
    data.columns = data.columns.str.strip()
    data = data.rename(columns={
        'datetime': 'Date', 'open': 'Open', 'high': 'High',
        'low': 'Low', 'close': 'Close', 'volume': 'Volume'
    })
    data['Date'] = pd.to_datetime(data['Date'])
    data = data.set_index('Date')
    data = data.drop(columns=[c for c in data.columns if 'unnamed' in c.lower()], errors='ignore')

    bt = Backtest(data, VolatilityDivergence, cash=1_000_000, commission=0.002)
    stats = bt.run()
    print(stats)
