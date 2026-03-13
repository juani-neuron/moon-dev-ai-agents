"""
BandStochasticBreakout Strategy — Bollinger Band Breakout + Stochastic Momentum
Long: close > upper BB AND Stoch %K crosses above 20 (leaving oversold).
Short: close < lower BB AND Stoch %K crosses below 80 (leaving overbought).
SL: middle BB. TP: 2:1 R:R or Stoch reaches opposite extreme.
"""
import pandas as pd
import numpy as np
import talib
from backtesting import Backtest, Strategy
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))
DATA_PATH = os.path.join(PROJECT_ROOT, "src", "data", "rbi", "BTC-USD-15m-train.csv")


def bb_upper(close, period, std):
    u, _, _ = talib.BBANDS(close, timeperiod=period, nbdevup=std, nbdevdn=std)
    return u


def bb_mid(close, period, std):
    _, m, _ = talib.BBANDS(close, timeperiod=period, nbdevup=std, nbdevdn=std)
    return m


def bb_lower(close, period, std):
    _, _, l = talib.BBANDS(close, timeperiod=period, nbdevup=std, nbdevdn=std)
    return l


def stoch_k(high, low, close, fastk, slowk, slowd):
    k, _ = talib.STOCH(high, low, close,
                       fastk_period=fastk, slowk_period=slowk,
                       slowk_matype=0, slowd_period=slowd, slowd_matype=0)
    return k


class BandStochasticBreakout(Strategy):
    bb_period = 20
    bb_std = 2
    stoch_fastk = 14
    stoch_slowk = 3
    stoch_slowd = 3
    rr_ratio = 2.0

    def init(self):
        self.bb_up = self.I(bb_upper, self.data.Close, self.bb_period, self.bb_std)
        self.bb_m = self.I(bb_mid, self.data.Close, self.bb_period, self.bb_std)
        self.bb_lo = self.I(bb_lower, self.data.Close, self.bb_period, self.bb_std)
        self.slowk = self.I(stoch_k, self.data.High, self.data.Low, self.data.Close,
                            self.stoch_fastk, self.stoch_slowk, self.stoch_slowd)

    def next(self):
        if len(self.data) < self.bb_period + 5:
            return

        price = self.data.Close[-1]
        up = self.bb_up[-1]
        lo = self.bb_lo[-1]
        mid = self.bb_m[-1]
        k_now = self.slowk[-1]
        k_prev = self.slowk[-2]

        if np.isnan(up) or np.isnan(k_now) or np.isnan(k_prev):
            return

        # Exit conditions
        if self.position.is_long:
            if k_now > 80 or price < mid:
                self.position.close()
                return
        elif self.position.is_short:
            if k_now < 20 or price > mid:
                self.position.close()
                return

        if self.position:
            return

        # Long: close above upper BB + stochastic crosses above 20
        if price > up and k_prev < 20 and k_now >= 20:
            sl = mid
            if sl < price:
                tp = price + self.rr_ratio * (price - sl)
                self.buy(sl=sl, tp=tp)

        # Short: close below lower BB + stochastic crosses below 80
        elif price < lo and k_prev > 80 and k_now <= 80:
            sl = mid
            if sl > price:
                tp = price - self.rr_ratio * (sl - price)
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

    bt = Backtest(data, BandStochasticBreakout, cash=1_000_000, commission=0.002)
    stats = bt.run()
    print(stats)
