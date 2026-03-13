#!/usr/bin/env python3
"""Run all v2 backtests and collect results."""
import os
import sys
import subprocess
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
BT_DIR = PROJECT_ROOT / "src" / "data" / "rbi" / "02_26_2026" / "backtests_v2"
PYTHON = PROJECT_ROOT / "venv" / "bin" / "python3"

results = []

for bt_file in sorted(BT_DIR.glob("*_BTFinal.py")):
    name = bt_file.stem.replace("_BTFinal", "")
    print(f"\n{'='*60}")
    print(f"Running: {name}")
    print(f"{'='*60}")

    try:
        result = subprocess.run(
            [str(PYTHON), str(bt_file)],
            capture_output=True, text=True, timeout=120,
            cwd=str(PROJECT_ROOT)
        )
        output = result.stdout + result.stderr

        # Parse key metrics from backtesting.py output
        metrics = {}
        for line in output.split('\n'):
            line = line.strip()
            for key in ['Return [%]', 'Sharpe Ratio', 'Max. Drawdown [%]', 'Win Rate [%]', '# Trades', 'Profit Factor']:
                if line.startswith(key):
                    val = line.split()[-1]
                    try:
                        metrics[key] = float(val)
                    except ValueError:
                        metrics[key] = val

        if metrics:
            results.append((name, metrics))
            ret = metrics.get('Return [%]', 'N/A')
            sharpe = metrics.get('Sharpe Ratio', 'N/A')
            dd = metrics.get('Max. Drawdown [%]', 'N/A')
            wr = metrics.get('Win Rate [%]', 'N/A')
            trades = metrics.get('# Trades', 'N/A')
            pf = metrics.get('Profit Factor', 'N/A')
            print(f"  Return: {ret}% | Sharpe: {sharpe} | MaxDD: {dd}% | WR: {wr}% | Trades: {trades} | PF: {pf}")
        else:
            print(f"  FAILED — no metrics parsed")
            if result.stderr:
                # Print last 5 lines of stderr
                err_lines = result.stderr.strip().split('\n')[-5:]
                for l in err_lines:
                    print(f"    {l}")

    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT (120s)")
    except Exception as e:
        print(f"  ERROR: {e}")

print(f"\n\n{'='*60}")
print("SUMMARY — Training Data (BTC 2023-01 to 2025-06)")
print(f"{'='*60}")
print(f"{'Strategy':<35} {'Return':>8} {'Sharpe':>8} {'MaxDD':>8} {'WinRate':>8} {'Trades':>8} {'PF':>8}")
print("-" * 95)

for name, m in sorted(results, key=lambda x: float(x[1].get('Return [%]', -999)), reverse=True):
    ret = m.get('Return [%]', 'N/A')
    sharpe = m.get('Sharpe Ratio', 'N/A')
    dd = m.get('Max. Drawdown [%]', 'N/A')
    wr = m.get('Win Rate [%]', 'N/A')
    trades = m.get('# Trades', 'N/A')
    pf = m.get('Profit Factor', 'N/A')
    flag = "***" if isinstance(ret, float) and ret > 0 and isinstance(trades, float) and trades >= 30 else ""
    print(f"{name:<35} {ret:>8} {sharpe:>8} {dd:>8} {wr:>8} {trades:>8} {pf:>8} {flag}")

print(f"\n*** = Profitable with 30+ trades (candidates for validation)")
