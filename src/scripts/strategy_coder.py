#!/usr/bin/env python3
"""
Strategy Coder — Lists research files and tracks backtest coding status.

Usage:
    ./venv/bin/python3 src/scripts/strategy_coder.py                    # Show status of all research files
    ./venv/bin/python3 src/scripts/strategy_coder.py --date 02_26_2026  # Specific date folder
    ./venv/bin/python3 src/scripts/strategy_coder.py --run NAME         # Run a specific BTFinal backtest
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent.parent  # moon-dev-ai-agents/
RBI_DIR = PROJECT_ROOT / "src" / "data" / "rbi"
VENV_PYTHON = PROJECT_ROOT / "venv" / "bin" / "python3"


def get_date_dir(date_str=None):
    """Get the date directory, defaulting to today"""
    if date_str is None:
        date_str = datetime.now().strftime("%m_%d_%Y")
    return RBI_DIR / date_str


def list_research_files(date_dir):
    """List all research files in a date directory"""
    research_dir = date_dir / "research"
    if not research_dir.exists():
        print(f"No research directory found at {research_dir}")
        return []
    return sorted(research_dir.glob("*_strategy.txt"))


def get_strategy_name(research_file):
    """Extract strategy name from research filename"""
    return research_file.stem.replace("_strategy", "")


def find_btfinal(name, date_dir):
    """Check if a BTFinal file exists for this strategy"""
    final_dir = date_dir / "backtests_final"
    btfinal = final_dir / f"{name}_BTFinal.py"
    return btfinal if btfinal.exists() else None


def run_backtest(btfinal_path):
    """Run a BTFinal backtest and return the output"""
    result = subprocess.run(
        [str(VENV_PYTHON), str(btfinal_path)],
        capture_output=True, text=True, timeout=120,
        env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT)}
    )
    return result.stdout, result.stderr, result.returncode


def show_status(date_str=None):
    """Show the status of all research files"""
    date_dir = get_date_dir(date_str)
    research_files = list_research_files(date_dir)

    if not research_files:
        print("No research files found.")
        return

    print(f"\n{'='*70}")
    print(f"  Strategy Research Status — {date_dir.name}")
    print(f"{'='*70}")
    print(f"{'#':<4} {'Strategy':<35} {'BTFinal':<10} {'Status'}")
    print(f"{'-'*70}")

    coded = 0
    pending = 0
    for i, rf in enumerate(research_files, 1):
        name = get_strategy_name(rf)
        btfinal = find_btfinal(name, date_dir)
        if btfinal:
            status = "CODED"
            coded += 1
        else:
            status = "PENDING"
            pending += 1
        print(f"{i:<4} {name:<35} {'yes' if btfinal else 'no':<10} {status}")

    print(f"{'-'*70}")
    print(f"Total: {len(research_files)} | Coded: {coded} | Pending: {pending}")
    print()


def run_single(name, date_str=None):
    """Run a specific BTFinal backtest"""
    date_dir = get_date_dir(date_str)
    btfinal = find_btfinal(name, date_dir)
    if not btfinal:
        print(f"No BTFinal found for '{name}' in {date_dir / 'backtests_final'}")
        return

    print(f"\nRunning {btfinal.name}...")
    print(f"{'='*70}")
    stdout, stderr, rc = run_backtest(btfinal)
    if stdout:
        print(stdout)
    if stderr:
        print(f"STDERR:\n{stderr}", file=sys.stderr)
    if rc != 0:
        print(f"Exit code: {rc}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Strategy Coder — track research → backtest status")
    parser.add_argument("--date", type=str, default=None, help="Date folder (MM_DD_YYYY)")
    parser.add_argument("--run", type=str, default=None, help="Run a specific strategy BTFinal")
    args = parser.parse_args()

    if args.run:
        run_single(args.run, args.date)
    else:
        show_status(args.date)
