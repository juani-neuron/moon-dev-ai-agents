#!/usr/bin/env python3
"""
Sub-period validation: Run surviving strategies on two time periods separately.
A real edge should be profitable in BOTH periods, not just one.

Period 1: 2023-01-01 to 2024-06-30 (18 months)
Period 2: 2024-07-01 to 2026-02-28 (20 months)

Tests VolumetricBollinger and RangeBoundPut on BTC, ETH, SOL for each period.
"""
import sys
import os
import pandas as pd
import numpy as np
import talib
from backtesting import Backtest, Strategy

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'rbi')
SPLIT_DATE = '2024-07-01'

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


# ─── Strategy 2: RangeBoundPut ───────────────────────────────────────────────
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


# ─── Data Loader ──────────────────────────────────────────────────────────────
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


def run_backtest(data, strat_cls):
    bt = Backtest(data, strat_cls, cash=1_000_000, commission=0.002)
    stats = bt.run()
    return {
        'Return [%]': round(stats['Return [%]'], 2),
        'Sharpe': round(stats['Sharpe Ratio'], 2) if not np.isnan(stats['Sharpe Ratio']) else 0,
        'Max DD [%]': round(stats['Max. Drawdown [%]'], 2),
        'Win Rate [%]': round(stats['Win Rate [%]'], 2) if not np.isnan(stats['Win Rate [%]']) else 0,
        'Trades': stats['# Trades'],
        'Profit Factor': round(stats['Profit Factor'], 2) if not np.isnan(stats.get('Profit Factor', float('nan'))) else 0,
    }


STRATEGIES = [
    ('VolumetricBollinger', VolumetricBollinger),
    ('RangeBoundPut', RangeBoundPut),
]

ASSETS = ['BTC', 'ETH', 'SOL']

if __name__ == '__main__':
    results = []

    for asset in ASSETS:
        print(f"\n{'='*60}")
        print(f"  Loading {asset} data...")
        print(f"{'='*60}")
        full_data = load_data(asset)
        print(f"  {len(full_data)} candles, {full_data.index[0]} to {full_data.index[-1]}")

        period1 = full_data[full_data.index < SPLIT_DATE]
        period2 = full_data[full_data.index >= SPLIT_DATE]
        print(f"  Period 1: {len(period1)} candles ({period1.index[0].date()} to {period1.index[-1].date()})")
        print(f"  Period 2: {len(period2)} candles ({period2.index[0].date()} to {period2.index[-1].date()})")

        for name, strat_cls in STRATEGIES:
            for period_label, period_data in [('P1 (2023-01 to 2024-06)', period1),
                                               ('P2 (2024-07 to 2026-02)', period2)]:
                tag = f"{name} | {asset} | {period_label}"
                print(f"\n  Running {tag}...", end=' ')
                try:
                    row = run_backtest(period_data, strat_cls)
                    row['Asset'] = asset
                    row['Strategy'] = name
                    row['Period'] = period_label
                    results.append(row)
                    print(f"OK  Return={row['Return [%]']}%  Trades={row['Trades']}  Sharpe={row['Sharpe']}")
                except Exception as e:
                    print(f"FAILED: {e}")
                    results.append({
                        'Asset': asset, 'Strategy': name, 'Period': period_label,
                        'Return [%]': None, 'Sharpe': None, 'Max DD [%]': None,
                        'Win Rate [%]': None, 'Trades': None, 'Profit Factor': None,
                        'Error': str(e),
                    })

    # ─── Summary ──────────────────────────────────────────────────────────────
    print(f"\n\n{'='*90}")
    print("  SUB-PERIOD VALIDATION RESULTS")
    print(f"  Split date: {SPLIT_DATE}")
    print(f"{'='*90}")
    df_results = pd.DataFrame(results)

    for strat_name in [s[0] for s in STRATEGIES]:
        print(f"\n  === {strat_name} ===")
        strat_rows = df_results[df_results['Strategy'] == strat_name]

        for period_label in strat_rows['Period'].unique():
            print(f"\n  {period_label}:")
            period_rows = strat_rows[strat_rows['Period'] == period_label]
            for _, r in period_rows.iterrows():
                if r.get('Error'):
                    print(f"    {r['Asset']:>4s}: FAILED - {r['Error']}")
                else:
                    trades_flag = " <30!" if r['Trades'] < 30 else ""
                    print(f"    {r['Asset']:>4s}: Return={r['Return [%]']:>8.1f}%  Sharpe={r['Sharpe']:>5.2f}  "
                          f"MaxDD={r['Max DD [%]']:>7.1f}%  WinRate={r['Win Rate [%]']:>5.1f}%  "
                          f"Trades={int(r['Trades']):>4d}  PF={r['Profit Factor']:>5.2f}{trades_flag}")

    # ─── Verdict ──────────────────────────────────────────────────────────────
    print(f"\n{'='*90}")
    print("  VERDICT: Strategy passes if profitable in BOTH periods on 2+ assets")
    print(f"{'='*90}")

    for strat_name in [s[0] for s in STRATEGIES]:
        strat_rows = df_results[(df_results['Strategy'] == strat_name) & (df_results['Return [%]'].notna())]

        p1_rows = strat_rows[strat_rows['Period'].str.startswith('P1')]
        p2_rows = strat_rows[strat_rows['Period'].str.startswith('P2')]

        p1_profitable = len(p1_rows[p1_rows['Return [%]'] > 0])
        p2_profitable = len(p2_rows[p2_rows['Return [%]'] > 0])
        p1_total = len(p1_rows)
        p2_total = len(p2_rows)

        # Must be profitable on 2+ assets in EACH period
        p1_pass = p1_profitable >= 2
        p2_pass = p2_profitable >= 2
        overall = "PASS" if (p1_pass and p2_pass) else "FAIL"

        print(f"\n  {strat_name}:")
        print(f"    Period 1: {p1_profitable}/{p1_total} profitable -> {'PASS' if p1_pass else 'FAIL'}")
        print(f"    Period 2: {p2_profitable}/{p2_total} profitable -> {'PASS' if p2_pass else 'FAIL'}")
        print(f"    Overall: {overall}")

    # ─── Save ─────────────────────────────────────────────────────────────────
    out_path = os.path.join(DATA_DIR, '..', 'subperiod_results.csv')
    df_results.to_csv(out_path, index=False)
    print(f"\n  Results saved to {out_path}")
