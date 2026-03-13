"""
DivergenceVolatilityBreakout Strategy — RSI Divergence + Keltner Channel Breakout + BB Expansion
Long only. Requires:
1. RSI bullish divergence (RSI higher low while price lower low)
2. BB width expanding (current > recent average)
3. Price closes above upper Keltner Channel
Exit: price closes below upper Keltner Channel.
"""
import pandas as pd
import numpy as np
import talib
from backtesting import Backtest, Strategy
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))
DATA_PATH = os.path.join(PROJECT_ROOT, "src", "data", "rbi", "BTC-USD-15m-train.csv")


def keltner_upper(high, low, close, ema_period, atr_period, atr_mult):
    ema = talib.EMA(close, timeperiod=ema_period)
    atr = talib.ATR(high, low, close, timeperiod=atr_period)
    return ema + atr_mult * atr


def bb_width(close, period, std):
    upper, mid, lower = talib.BBANDS(close, timeperiod=period, nbdevup=std, nbdevdn=std)
    return (upper - lower) / mid


def bb_width_avg(close, period, std, avg_period):
    w = bb_width(close, period, std)
    return talib.SMA(w, timeperiod=avg_period)


class DivergenceVolatilityBreakout(Strategy):
    rsi_period = 14
    kc_ema_period = 20
    kc_atr_period = 14
    kc_atr_mult = 1.5
    bb_period = 20
    bb_std = 2
    bbw_avg_period = 20
    divergence_lookback = 20
    sl_atr_mult = 1.5

    def init(self):
        self.rsi = self.I(talib.RSI, self.data.Close, timeperiod=self.rsi_period)
        self.kc_upper = self.I(keltner_upper, self.data.High, self.data.Low, self.data.Close,
                               self.kc_ema_period, self.kc_atr_period, self.kc_atr_mult)
        self.bbw = self.I(bb_width, self.data.Close, self.bb_period, self.bb_std)
        self.bbw_avg = self.I(bb_width_avg, self.data.Close, self.bb_period, self.bb_std, self.bbw_avg_period)
        self.atr = self.I(talib.ATR, self.data.High, self.data.Low, self.data.Close,
                          timeperiod=self.kc_atr_period)

    def _check_bullish_divergence(self):
        """Check for bullish RSI divergence: price lower low, RSI higher low."""
        lb = self.divergence_lookback
        if len(self.data) < lb + 2:
            return False

        half = lb // 2
        if half < 3:
            return False

        # Price lows and RSI in each half
        price_lows_first = [self.data.Low[-(lb) + i] for i in range(half)]
        price_lows_second = [self.data.Low[-(half) + i] for i in range(half)]
        rsi_first = [self.rsi[-(lb) + i] for i in range(half)]
        rsi_second = [self.rsi[-(half) + i] for i in range(half)]

        if any(np.isnan(v) for v in price_lows_first + price_lows_second + rsi_first + rsi_second):
            return False

        # Find min price in each half
        min_price_first = min(price_lows_first)
        min_price_second = min(price_lows_second)
        idx_first = price_lows_first.index(min_price_first)
        idx_second = price_lows_second.index(min_price_second)
        rsi_at_first = rsi_first[idx_first]
        rsi_at_second = rsi_second[idx_second]

        # Bullish divergence: price lower low, RSI higher low
        return min_price_second < min_price_first and rsi_at_second > rsi_at_first

    def next(self):
        if len(self.data) < max(self.bb_period, self.kc_ema_period) + self.divergence_lookback + 10:
            return

        price = self.data.Close[-1]
        kc_upper = self.kc_upper[-1]
        bbw = self.bbw[-1]
        bbw_avg = self.bbw_avg[-1]
        atr_val = self.atr[-1]

        if np.isnan(kc_upper) or np.isnan(bbw) or np.isnan(bbw_avg) or np.isnan(atr_val) or atr_val <= 0:
            return

        # Exit: close below upper Keltner
        if self.position.is_long:
            if price < kc_upper:
                self.position.close()
                return

        if self.position:
            return

        # Entry conditions
        # 1. BB width expanding
        if bbw <= bbw_avg:
            return

        # 2. Price closes above upper Keltner Channel
        if price <= kc_upper:
            return

        # 3. RSI bullish divergence
        if not self._check_bullish_divergence():
            return

        sl = price - self.sl_atr_mult * atr_val
        if sl < price:
            self.buy(sl=sl)


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

    bt = Backtest(data, DivergenceVolatilityBreakout, cash=1_000_000, commission=0.002)
    stats = bt.run()
    print(stats)
