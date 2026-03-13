"""
Batch Backtest Runner
Runs all existing BTFinal backtest scripts, auto-fixes common issues,
captures stats, and ranks strategies by performance.

Usage:
    python src/scripts/batch_backtest_runner.py           # Run all
    python src/scripts/batch_backtest_runner.py --limit 50 # Run first 50
    python src/scripts/batch_backtest_runner.py --results   # Show results from last run
"""

import os
import re
import sys
import csv
import time
import signal
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "src" / "data" / "rbi"
BTC_DATA = DATA_DIR / "BTC-USD-15m.csv"
RESULTS_CSV = PROJECT_ROOT / "src" / "data" / "backtest_results.csv"

# The original author's path that needs replacing
OLD_DATA_PATHS = [
    "/Users/md/Dropbox/dev/github/moon-dev-ai-agents-for-trading/src/data/rbi/BTC-USD-15m.csv",
    "/Users/md/Dropbox/dev/github/moon-dev-ai-agents-for-trading/src/data/rbi",
]


def find_all_backtests():
    """Find all BTFinal backtest files."""
    backtests = []
    for root, dirs, files in os.walk(DATA_DIR):
        for f in files:
            if "BTFinal" in f and f.endswith(".py"):
                backtests.append(Path(root) / f)
    backtests.sort()
    return backtests


def fix_backtest_code(code):
    """Fix common issues in backtest code so it can actually run."""

    # 1. Extract code from markdown fences if present
    if "```" in code:
        # Extract all code blocks
        blocks = re.findall(r"```(?:python)?\s*\n(.*?)```", code, re.DOTALL)
        if blocks:
            code = "\n\n".join(blocks)

    # 2. Remove leading AI commentary text before actual Python code
    lines = code.split("\n")
    code_start = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if (
            stripped.startswith("import ")
            or stripped.startswith("from ")
            or stripped.startswith("# ")
            or stripped.startswith("#!")
            or stripped.startswith('"""')
            or stripped.startswith("# -*-")
            or re.match(r"^[A-Z_]+ = ", stripped)  # constant assignment
            or re.match(r"^class ", stripped)
            or re.match(r"^def ", stripped)
        ):
            code_start = i
            break
    if code_start > 0:
        code = "\n".join(lines[code_start:])

    # 3. Remove any remaining markdown fence lines
    code = re.sub(r"^```(?:python)?$", "", code, flags=re.MULTILINE)
    code = re.sub(r"^```$", "", code, flags=re.MULTILINE)

    # 2. Fix data path to point to our local BTC data
    for old_path in OLD_DATA_PATHS:
        code = code.replace(old_path, str(BTC_DATA))

    # Also catch any path that references BTC-USD-15m.csv with a different base
    code = re.sub(
        r'["\'][^"\']*BTC-USD-15m\.csv["\']',
        f'"{BTC_DATA}"',
        code,
    )

    # 3. Replace backtesting.lib crossover with inline implementation
    if "from backtesting.lib import" in code or "backtesting.lib" in code:
        # Remove the import
        code = re.sub(r"from backtesting\.lib import[^\n]*\n", "", code)
        code = re.sub(r"import backtesting\.lib[^\n]*\n", "", code)

        # Add a crossover helper at the top (after imports)
        crossover_func = """
def crossover(series_a, series_b):
    try:
        return series_a[-2] < series_b[-2] and series_a[-1] > series_b[-1]
    except (IndexError, KeyError):
        return False

"""
        # Insert after the last import line
        import_end = 0
        for i, line in enumerate(code.split("\n")):
            if line.strip().startswith("import ") or line.strip().startswith("from "):
                import_end = i + 1
        lines = code.split("\n")
        lines.insert(import_end, crossover_func)
        code = "\n".join(lines)

    # 4. Fix broken emoji strings (unterminated f-strings/strings with emojis)
    # Comment out print lines that have unterminated strings
    fixed_lines = []
    for line in code.split("\n"):
        stripped = line.strip()
        if stripped.startswith("print(") or stripped.startswith("print ("):
            # Check for unterminated strings
            try:
                compile(line.strip(), "<string>", "exec")
                fixed_lines.append(line)
            except SyntaxError:
                fixed_lines.append(line.split("print")[0] + "pass  # broken print removed")
        else:
            fixed_lines.append(line)
    code = "\n".join(fixed_lines)

    # 5. Suppress plot calls that would hang
    code = re.sub(r"bt\.plot\([^)]*\)", "pass  # plot disabled", code)
    code = re.sub(r"\.plot\([^)]*\)", "  # plot disabled", code)

    # 6. Suppress any input() calls
    code = code.replace("input(", "# input(")

    return code


def parse_backtest_stats(output):
    """Parse backtesting.py stats output into a dict."""
    stats = {}

    # Common stat patterns from backtesting.py output
    patterns = {
        "Return [%]": r"Return \[%\]\s+([-\d.]+)",
        "Buy & Hold Return [%]": r"Buy & Hold Return \[%\]\s+([-\d.]+)",
        "Return (Ann.) [%]": r"Return \(Ann\.\) \[%\]\s+([-\d.]+)",
        "Sharpe Ratio": r"Sharpe Ratio\s+([-\d.]+)",
        "Sortino Ratio": r"Sortino Ratio\s+([-\d.]+)",
        "Max. Drawdown [%]": r"Max\. Drawdown \[%\]\s+([-\d.]+)",
        "Win Rate [%]": r"Win Rate \[%\]\s+([-\d.]+)",
        "# Trades": r"# Trades\s+(\d+)",
        "Profit Factor": r"Profit Factor\s+([-\d.]+)",
        "Expectancy [%]": r"Expectancy \[%\]\s+([-\d.]+)",
        "Avg. Trade [%]": r"Avg\. Trade \[%\]\s+([-\d.]+)",
        "Calmar Ratio": r"Calmar Ratio\s+([-\d.]+)",
        "Equity Final [$]": r"Equity Final \[\$\]\s+([-\d.]+)",
        "Equity Peak [$]": r"Equity Peak \[\$\]\s+([-\d.]+)",
        "Avg. Trade Duration": r"Avg\. Trade Duration\s+(.+)",
        "Max. Trade Duration": r"Max\. Trade Duration\s+(.+)",
    }

    for name, pattern in patterns.items():
        match = re.search(pattern, output)
        if match:
            stats[name] = match.group(1).strip()

    return stats


def run_single_backtest(filepath, timeout=60):
    """Run a single backtest file and return results."""
    strategy_name = filepath.stem.replace("_BTFinal", "")
    date_folder = filepath.parent.parent.name

    try:
        with open(filepath, "r") as f:
            original_code = f.read()
    except Exception as e:
        return {
            "strategy": strategy_name,
            "date": date_folder,
            "status": "READ_ERROR",
            "error": str(e),
        }

    # Fix common issues
    fixed_code = fix_backtest_code(original_code)

    if not fixed_code.strip():
        return {
            "strategy": strategy_name,
            "date": date_folder,
            "status": "EMPTY_CODE",
            "error": "No code after cleanup",
        }

    # Write to temp file and execute
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, dir=str(PROJECT_ROOT)
    ) as tmp:
        tmp.write(fixed_code)
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(PROJECT_ROOT),
        )

        combined_output = result.stdout + "\n" + result.stderr
        stats = parse_backtest_stats(combined_output)

        if stats:
            stats["strategy"] = strategy_name
            stats["date"] = date_folder
            stats["status"] = "SUCCESS"
            stats["file"] = str(filepath)
            return stats
        elif result.returncode != 0:
            # Get last 3 lines of error for diagnosis
            error_lines = [
                l for l in result.stderr.strip().split("\n") if l.strip()
            ]
            error_msg = " | ".join(error_lines[-3:]) if error_lines else "Unknown error"
            return {
                "strategy": strategy_name,
                "date": date_folder,
                "status": "RUNTIME_ERROR",
                "error": error_msg[:500],
            }
        else:
            return {
                "strategy": strategy_name,
                "date": date_folder,
                "status": "NO_STATS",
                "error": "Ran but no stats parsed",
            }

    except subprocess.TimeoutExpired:
        return {
            "strategy": strategy_name,
            "date": date_folder,
            "status": "TIMEOUT",
            "error": f"Exceeded {timeout}s",
        }
    except Exception as e:
        return {
            "strategy": strategy_name,
            "date": date_folder,
            "status": "EXEC_ERROR",
            "error": str(e)[:500],
        }
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def show_results():
    """Display results from the last batch run."""
    if not RESULTS_CSV.exists():
        print("No results file found. Run the batch first.")
        return

    import pandas as pd

    df = pd.read_csv(RESULTS_CSV)

    total = len(df)
    success = df[df["status"] == "SUCCESS"]
    errors = df[df["status"] != "SUCCESS"]

    print(f"\n{'='*70}")
    print(f"  BATCH BACKTEST RESULTS SUMMARY")
    print(f"{'='*70}")
    print(f"  Total strategies tested: {total}")
    print(f"  Successful runs:         {len(success)} ({len(success)/total*100:.1f}%)")
    print(f"  Failed runs:             {len(errors)} ({len(errors)/total*100:.1f}%)")

    if len(success) == 0:
        print("\n  No successful backtests to analyze.")
        return

    # Convert numeric columns
    numeric_cols = [
        "Return [%]",
        "Sharpe Ratio",
        "Max. Drawdown [%]",
        "Win Rate [%]",
        "# Trades",
        "Profit Factor",
        "Avg. Trade [%]",
        "Expectancy [%]",
    ]
    for col in numeric_cols:
        if col in success.columns:
            success[col] = pd.to_numeric(success[col], errors="coerce")

    # Filter for strategies with enough trades
    tradeable = success[success["# Trades"] >= 10].copy()
    print(f"  With 10+ trades:         {len(tradeable)}")

    if len(tradeable) == 0:
        print("\n  No strategies with sufficient trades.")
        return

    # Profitable strategies
    profitable = tradeable[tradeable["Return [%]"] > 0]
    print(f"  Profitable (return > 0): {len(profitable)}")

    # Top strategies by return
    print(f"\n{'='*70}")
    print(f"  TOP 20 STRATEGIES BY RETURN")
    print(f"{'='*70}")
    top = tradeable.nlargest(20, "Return [%]")
    display_cols = [
        "strategy",
        "Return [%]",
        "Sharpe Ratio",
        "Max. Drawdown [%]",
        "Win Rate [%]",
        "# Trades",
        "Profit Factor",
    ]
    available_cols = [c for c in display_cols if c in top.columns]
    print(top[available_cols].to_string(index=False))

    # Top by Sharpe
    if "Sharpe Ratio" in tradeable.columns:
        sharpe_valid = tradeable.dropna(subset=["Sharpe Ratio"])
        if len(sharpe_valid) > 0:
            print(f"\n{'='*70}")
            print(f"  TOP 20 STRATEGIES BY SHARPE RATIO")
            print(f"{'='*70}")
            top_sharpe = sharpe_valid.nlargest(20, "Sharpe Ratio")
            print(top_sharpe[available_cols].to_string(index=False))

    # Best risk-adjusted (high return, low drawdown)
    if "Max. Drawdown [%]" in tradeable.columns:
        risk_adj = tradeable.copy()
        risk_adj["risk_score"] = risk_adj["Return [%]"] / (
            risk_adj["Max. Drawdown [%]"].abs() + 1
        )
        risk_adj = risk_adj.dropna(subset=["risk_score"])
        if len(risk_adj) > 0:
            print(f"\n{'='*70}")
            print(f"  TOP 20 RISK-ADJUSTED (Return / Drawdown)")
            print(f"{'='*70}")
            top_risk = risk_adj.nlargest(20, "risk_score")
            print(top_risk[available_cols].to_string(index=False))

    # Error summary
    if len(errors) > 0:
        print(f"\n{'='*70}")
        print(f"  ERROR BREAKDOWN")
        print(f"{'='*70}")
        print(errors["status"].value_counts().to_string())

    print(f"\nFull results saved to: {RESULTS_CSV}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Batch Backtest Runner")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of backtests to run (0 = all)")
    parser.add_argument("--results", action="store_true", help="Show results from last run")
    parser.add_argument("--timeout", type=int, default=60, help="Timeout per backtest in seconds")
    parser.add_argument("--runnable-only", action="store_true", help="Only run backtests that have print(stats)")
    parser.add_argument("--file-list", type=str, help="File containing list of backtest paths to run")
    args = parser.parse_args()

    if args.results:
        show_results()
        return

    if not BTC_DATA.exists():
        print(f"BTC data not found at {BTC_DATA}")
        sys.exit(1)

    if args.file_list:
        with open(args.file_list) as f:
            backtests = [Path(line.strip()) for line in f if line.strip()]
    elif args.runnable_only:
        # Only backtests that contain print(stats) — likely complete
        all_bt = find_all_backtests()
        backtests = []
        for bt_file in all_bt:
            try:
                content = bt_file.read_text()
                if "print(stats)" in content or "print(bt.run())" in content:
                    backtests.append(bt_file)
            except Exception:
                pass
    else:
        backtests = find_all_backtests()

    total = len(backtests)
    print(f"\nFound {total} backtest files")

    if args.limit > 0:
        backtests = backtests[: args.limit]
        print(f"Running first {args.limit}")

    to_run = len(backtests)
    results = []
    success_count = 0
    error_count = 0
    start_time = time.time()

    # CSV header
    fieldnames = [
        "strategy",
        "date",
        "status",
        "Return [%]",
        "Buy & Hold Return [%]",
        "Return (Ann.) [%]",
        "Sharpe Ratio",
        "Sortino Ratio",
        "Max. Drawdown [%]",
        "Win Rate [%]",
        "# Trades",
        "Profit Factor",
        "Expectancy [%]",
        "Avg. Trade [%]",
        "Calmar Ratio",
        "Equity Final [$]",
        "Equity Peak [$]",
        "Avg. Trade Duration",
        "Max. Trade Duration",
        "file",
        "error",
    ]

    with open(RESULTS_CSV, "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()

        for i, bt_file in enumerate(backtests, 1):
            strategy_name = bt_file.stem.replace("_BTFinal", "")
            elapsed = time.time() - start_time
            rate = i / elapsed if elapsed > 0 else 0
            eta = (to_run - i) / rate if rate > 0 else 0

            print(
                f"[{i}/{to_run}] {strategy_name:<40} ",
                end="",
                flush=True,
            )

            result = run_single_backtest(bt_file, timeout=args.timeout)

            if result["status"] == "SUCCESS":
                ret = result.get("Return [%]", "?")
                trades = result.get("# Trades", "?")
                sharpe = result.get("Sharpe Ratio", "?")
                print(f"OK  ret={ret}%  trades={trades}  sharpe={sharpe}")
                success_count += 1
            else:
                error_short = result.get("error", "")[:80]
                print(f"FAIL ({result['status']}) {error_short}")
                error_count += 1

            writer.writerow(result)
            csvfile.flush()
            results.append(result)

            # Progress every 50
            if i % 50 == 0:
                print(f"\n--- Progress: {i}/{to_run} | OK: {success_count} | FAIL: {error_count} | ETA: {eta/60:.1f}min ---\n")

    elapsed_total = time.time() - start_time
    print(f"\n{'='*70}")
    print(f"  BATCH RUN COMPLETE")
    print(f"  Time: {elapsed_total/60:.1f} minutes")
    print(f"  Success: {success_count}/{to_run}")
    print(f"  Failed: {error_count}/{to_run}")
    print(f"  Results: {RESULTS_CSV}")
    print(f"{'='*70}")

    # Show results summary
    show_results()


if __name__ == "__main__":
    main()
