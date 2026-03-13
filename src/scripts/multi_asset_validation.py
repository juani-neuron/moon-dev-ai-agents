#!/usr/bin/env python3
"""
Multi-asset validation: Run top 3 BTC strategies on ETH and SOL.
Tests whether the edge generalizes across assets.
"""
import sys
import os
import pandas as pd
import numpy as np
import talib
from backtesting import Backtest, Strategy

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'rbi')

# ─── Strategy 1: VolumetricBollinger ─────────────────────────────────────────
class VolumetricBollinger(Strategy):
    def init(self):
        self.sma20 = self.I(talib.SMA, self.data.Close, timeperiod=20, name='SMA20')
        self.std20 = self.I(talib.STDDEV, self.data.Close, timeperiod=20, nbdev=2, name='STD20')
        self.avg_volume = self.I(talib.SMA, self.data.Volume, timeperiod=96, name='AvgVolume')
        self.risk_percent = 0.5
        self.entry_window_size = 2

    def next(self):
        if not self.position:
            bb_width = (4 * self.std20[-1]) / self.sma20[-1] if self.sma20[-1] else 0
            vol_condition = self.data.Volume[-1] >= 2 * self.avg_volume[-1]

            if bb_width < 2.0 and vol_condition:
                self.entry_window = self.entry_window_size

            if hasattr(self, 'entry_window') and self.entry_window > 0:
                price = self.data.Close[-1]
                position_size = int(round((self.equity * self.risk_percent) / price))
                if position_size > 0:
                    sl = price * 0.80
                    tp = price * 1.10
                    self.buy(size=position_size, sl=sl, tp=tp)
                del self.entry_window
            elif hasattr(self, 'entry_window'):
                self.entry_window -= 1
                if self.entry_window <= 0:
                    del self.entry_window


# ─── Strategy 2: VolSurgeReversion ───────────────────────────────────────────
class VolSurgeReversion(Strategy):
    bb_period = 2880  # 30 days in 15m intervals
    rsi_period = 14
    vol_multiplier = 2
    risk_pct = 0.02
    swing_window = 20

    def init(self):
        self.upper_band, self.middle_band, self.lower_band = self.I(
            talib.BBANDS, self.data.Close,
            timeperiod=self.bb_period, nbdevup=2, nbdevdn=2, matype=0
        )
        self.vol_ma = self.I(talib.SMA, self.data.Volume, self.bb_period)
        self.rsi = self.I(talib.RSI, self.data.Close, self.rsi_period)
        self.swing_low = self.I(talib.MIN, self.data.Low, self.swing_window)

    def next(self):
        if len(self.data) < self.bb_period:
            return
        price = self.data.Close[-1]
        lower_band = self.lower_band[-1]
        volume = self.data.Volume[-1]
        vol_ma = self.vol_ma[-1]
        swing_low = self.swing_low[-1]

        if (not self.position and
            price < lower_band and
            volume > self.vol_multiplier * vol_ma):
            risk_amount = self.risk_pct * self.equity
            stop_loss = swing_low
            risk_per_share = price - stop_loss
            if risk_per_share > 0:
                position_size = int(round(risk_amount / risk_per_share))
                if position_size > 0:
                    self.buy(size=position_size, sl=stop_loss)

        if (self.position and self.position.is_long and
            self.rsi[-2] < 50 and self.rsi[-1] > 50):
            self.position.close()


# ─── Strategy 3: RangeBoundPut ───────────────────────────────────────────────
class RangeBoundPut(Strategy):
    ma_period = 200
    lookback_period = 20
    risk_pct = 0.02

    def init(self):
        self.sma = self.I(talib.SMA, self.data.Close, timeperiod=self.ma_period)
        self.above_sma = (self.data.Close > self.sma).astype(float)
        self.sum_above = self.I(talib.SUM, self.above_sma, timeperiod=self.lookback_period)

    def next(self):
        if not self.position:
            if len(self.data) > self.lookback_period and self.sum_above[-1] >= self.lookback_period:
                entry_price = self.data.Close[-1]
                sl_price = entry_price * 0.8
                tp_price = entry_price * 1.1
                risk_amount = self.equity * self.risk_pct
                risk_per_share = entry_price - sl_price
                if risk_per_share > 0:
                    position_size = int(round(risk_amount / risk_per_share))
                    if position_size > 0:
                        self.buy(size=position_size, sl=sl_price, tp=tp_price)


# ─── Runner ──────────────────────────────────────────────────────────────────
def load_data(asset):
    path = os.path.join(DATA_DIR, f'{asset}-USD-15m.csv')
    df = pd.read_csv(path)
    df.columns = df.columns.str.strip().str.lower()
    df = df.drop(columns=[c for c in df.columns if 'unnamed' in c.lower()])
    df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low',
                       'close': 'Close', 'volume': 'Volume'}, inplace=True)
    df['datetime'] = pd.to_datetime(df['datetime'])
    df.set_index('datetime', inplace=True)
    return df


STRATEGIES = [
    ('VolumetricBollinger', VolumetricBollinger),
    ('VolSurgeReversion', VolSurgeReversion),
    ('RangeBoundPut', RangeBoundPut),
]

ASSETS = ['BTC', 'ETH', 'SOL']

if __name__ == '__main__':
    results = []
    for asset in ASSETS:
        print(f"\n{'='*60}")
        print(f"  Loading {asset} data...")
        print(f"{'='*60}")
        data = load_data(asset)
        print(f"  {len(data)} candles, {data.index[0]} to {data.index[-1]}")

        for name, strat_cls in STRATEGIES:
            print(f"\n  Running {name} on {asset}...", end=' ')
            try:
                bt = Backtest(data, strat_cls, cash=1_000_000, commission=0.002)
                stats = bt.run()
                row = {
                    'Asset': asset,
                    'Strategy': name,
                    'Return [%]': round(stats['Return [%]'], 2),
                    'Sharpe': round(stats['Sharpe Ratio'], 2) if not np.isnan(stats['Sharpe Ratio']) else 0,
                    'Max DD [%]': round(stats['Max. Drawdown [%]'], 2),
                    'Win Rate [%]': round(stats['Win Rate [%]'], 2) if not np.isnan(stats['Win Rate [%]']) else 0,
                    'Trades': stats['# Trades'],
                    'Profit Factor': round(stats['Profit Factor'], 2) if not np.isnan(stats.get('Profit Factor', float('nan'))) else 0,
                }
                results.append(row)
                print(f"OK  Return={row['Return [%]']}%  Trades={row['Trades']}  Sharpe={row['Sharpe']}")
            except Exception as e:
                print(f"FAILED: {e}")
                results.append({
                    'Asset': asset, 'Strategy': name,
                    'Return [%]': None, 'Sharpe': None, 'Max DD [%]': None,
                    'Win Rate [%]': None, 'Trades': None, 'Profit Factor': None,
                    'Error': str(e),
                })

    # Print summary table
    print(f"\n\n{'='*80}")
    print("  MULTI-ASSET VALIDATION RESULTS")
    print(f"{'='*80}")
    df_results = pd.DataFrame(results)

    for strat_name in [s[0] for s in STRATEGIES]:
        strat_rows = df_results[df_results['Strategy'] == strat_name]
        print(f"\n  --- {strat_name} ---")
        for _, r in strat_rows.iterrows():
            if r.get('Error'):
                print(f"  {r['Asset']:>4s}: FAILED - {r['Error']}")
            else:
                print(f"  {r['Asset']:>4s}: Return={r['Return [%]']:>8.1f}%  Sharpe={r['Sharpe']:>5.2f}  "
                      f"MaxDD={r['Max DD [%]']:>7.1f}%  WinRate={r['Win Rate [%]']:>5.1f}%  "
                      f"Trades={int(r['Trades']):>4d}  PF={r['Profit Factor']:>5.2f}")

    # Verdict
    print(f"\n{'='*80}")
    print("  VERDICT: Strategy passes multi-asset test if profitable on 2+ assets")
    print(f"{'='*80}")
    for strat_name in [s[0] for s in STRATEGIES]:
        strat_rows = df_results[(df_results['Strategy'] == strat_name) & (df_results['Return [%]'].notna())]
        profitable = strat_rows[strat_rows['Return [%]'] > 0]
        sufficient_trades = strat_rows[strat_rows['Trades'] >= 30] if 'Trades' in strat_rows else strat_rows
        n_profitable = len(profitable)
        n_total = len(strat_rows)
        verdict = "PASS" if n_profitable >= 2 else "FAIL"
        print(f"  {strat_name}: {n_profitable}/{n_total} profitable -> {verdict}")

    # Save results
    out_path = os.path.join(DATA_DIR, '..', 'multi_asset_results.csv')
    df_results.to_csv(out_path, index=False)
    print(f"\n  Results saved to {out_path}")
