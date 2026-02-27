#!/usr/bin/env python3
"""
Swarm Backtester — Historical AI Voting Simulation

Replays historical candles through the real AI swarm (Claude + DeepSeek),
simulates position management (SL/TP/signals), and outputs trading statistics.

Usage:
    # Default: BTC, Feb 24-26, real API calls
    ./venv/bin/python3 src/scripts/swarm_backtester.py --start 2026-02-24 --end 2026-02-26

    # Resume interrupted run
    ./venv/bin/python3 src/scripts/swarm_backtester.py --start 2026-02-24 --end 2026-02-26 --resume

    # Show last results
    ./venv/bin/python3 src/scripts/swarm_backtester.py --results

Cost: ~$2-5 for 72 candles (144 API calls). Runtime: ~6-10 minutes.
"""

import os
import sys
import json
import time
import argparse
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from termcolor import colored, cprint

# Add project root to path
project_root = str(Path(__file__).parent.parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

from src.agents.swarm_agent import SwarmAgent

# ============================================================================
# CONFIGURATION
# ============================================================================

SYMBOL = "BTC"
TIMEFRAME = "1H"
LOOKBACK_BARS = 120          # How many bars each AI sees (5 days of 1H)
STARTING_BALANCE = 10_000.0
LEVERAGE = 3
MAX_POSITION_PCT = 0.40       # 40% of balance as margin
STOP_LOSS_PCT = -5.0          # -5% triggers stop loss
TAKE_PROFIT_PCT = 8.0         # +8% triggers take profit
LONG_ONLY = True

OUTPUT_DIR = Path(project_root) / "src" / "data" / "swarm_backtester"

# System prompt — same as live trading_agent
SWARM_TRADING_PROMPT = """You are an expert cryptocurrency trading AI analyzing market data.

CRITICAL RULES:
1. Your response MUST be EXACTLY one of these three words: Buy, Sell, or Do Nothing
2. Do NOT provide any explanation, reasoning, or additional text
3. Respond with ONLY the action word
4. Do NOT show your thinking process or internal reasoning

Analyze the market data below and decide:

- "Buy" = Strong bullish signals, recommend opening/holding position
- "Sell" = Bearish signals or major weakness, recommend closing position entirely
- "Do Nothing" = Unclear/neutral signals, recommend holding current state unchanged

IMPORTANT: "Do Nothing" means maintain current position (if we have one, keep it; if we don't, stay out)

RESPOND WITH ONLY ONE WORD: Buy, Sell, or Do Nothing"""


# ============================================================================
# DATA FETCHING
# ============================================================================

def fetch_data(symbol, start_date, end_date, lookback_bars):
    """Fetch enough data so we have lookback_bars before start_date + candles through end_date."""
    import requests
    import pandas_ta as ta

    # We need lookback_bars BEFORE the start_date, plus the backtest window
    buffer_hours = lookback_bars + 24  # extra padding
    fetch_start = start_date - timedelta(hours=buffer_hours)

    cprint(f"\nFetching {symbol} {TIMEFRAME} data from HyperLiquid...", "cyan")
    cprint(f"  Fetch range: {fetch_start} to {end_date}", "white")

    start_ts = int(fetch_start.timestamp() * 1000)
    end_ts = int(end_date.timestamp() * 1000)

    url = "https://api.hyperliquid.xyz/info"
    # HyperLiquid expects lowercase intervals (1h, 15m, etc.)
    hl_interval = TIMEFRAME.lower()

    payload = {
        "type": "candleSnapshot",
        "req": {
            "coin": symbol,
            "interval": hl_interval,
            "startTime": start_ts,
            "endTime": end_ts
        }
    }

    response = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=30)

    if response.status_code != 200:
        cprint(f"API error: {response.status_code} — {response.text[:200]}", "red")
        sys.exit(1)

    raw = response.json()
    if not raw:
        cprint("No data returned from API", "red")
        sys.exit(1)

    # Build DataFrame
    rows = []
    for c in raw:
        ts = datetime.utcfromtimestamp(c["t"] / 1000)
        rows.append([ts, float(c["o"]), float(c["h"]), float(c["l"]), float(c["c"]), float(c["v"])])
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df = df.sort_values("timestamp").reset_index(drop=True)

    # Add technical indicators
    df["sma_20"] = ta.sma(df["close"], length=20)
    df["sma_50"] = ta.sma(df["close"], length=50)
    df["rsi"] = ta.rsi(df["close"], length=14)
    macd = ta.macd(df["close"])
    df = pd.concat([df, macd], axis=1)
    bbands = ta.bbands(df["close"])
    df = pd.concat([df, bbands], axis=1)

    cprint(f"  Fetched {len(df)} candles: {df['timestamp'].iloc[0]} to {df['timestamp'].iloc[-1]}", "green")
    return df


# ============================================================================
# VOTE PARSING (same logic as trading_agent._calculate_swarm_consensus)
# ============================================================================

def parse_votes(swarm_result):
    """Parse individual votes from swarm result.
    Returns: (action, confidence_pct, per_model_votes_dict)
    """
    votes = {"BUY": 0, "SELL": 0, "NOTHING": 0}
    per_model = {}

    for provider, data in swarm_result["responses"].items():
        if not data["success"]:
            per_model[provider] = "ERROR"
            continue
        txt = data["response"].strip().upper()
        if "BUY" in txt:
            votes["BUY"] += 1
            per_model[provider] = "Buy"
        elif "SELL" in txt:
            votes["SELL"] += 1
            per_model[provider] = "Sell"
        else:
            votes["NOTHING"] += 1
            per_model[provider] = "Do Nothing"

    total = sum(votes.values())
    if total == 0:
        return "NOTHING", 0, per_model

    action = max(votes, key=votes.get)
    confidence = int((votes[action] / total) * 100)
    return action, confidence, per_model


# ============================================================================
# FORMAT MARKET DATA (same as trading_agent._format_market_data_for_swarm)
# ============================================================================

def format_market_data(symbol, window_df):
    """Format a lookback window DataFrame into the prompt the swarm expects."""
    return f"""TOKEN: {symbol}
TIMEFRAME: {TIMEFRAME} bars
TOTAL BARS: {len(window_df)}
DATE RANGE: {window_df['timestamp'].iloc[0]} to {window_df['timestamp'].iloc[-1]}

RECENT PRICE ACTION (Last 10 bars):
{window_df.tail(10).to_string(index=False)}

FULL DATASET:
{window_df.to_string(index=False)}
"""


# ============================================================================
# POSITION SIMULATOR
# ============================================================================

class Position:
    __slots__ = ("entry_price", "entry_time", "size_usd", "margin")

    def __init__(self, entry_price, entry_time, size_usd, margin):
        self.entry_price = entry_price
        self.entry_time = entry_time
        self.size_usd = size_usd   # notional
        self.margin = margin

    def pnl_pct(self, price):
        return ((price / self.entry_price) - 1) * 100 * LEVERAGE

    def pnl_usd(self, price):
        return self.margin * ((price / self.entry_price) - 1) * LEVERAGE


class Simulator:
    def __init__(self, balance):
        self.starting_balance = balance
        self.balance = balance
        self.position = None
        self.trades = []          # closed trades
        self.equity_curve = []    # (timestamp, equity)
        self.peak_equity = balance
        self.max_drawdown = 0.0

    @property
    def equity(self):
        if self.position:
            return self.balance + self.position.margin + self.position.pnl_usd(self._last_price)
        return self.balance

    def _update_drawdown(self, ts):
        eq = self.equity
        self.equity_curve.append((ts, eq))
        if eq > self.peak_equity:
            self.peak_equity = eq
        dd = (eq - self.peak_equity) / self.peak_equity * 100
        if dd < self.max_drawdown:
            self.max_drawdown = dd

    def check_sl_tp(self, candle):
        """Check if SL or TP is hit within this candle. Returns close reason or None."""
        if self.position is None:
            return None

        low, high = candle["low"], candle["high"]
        sl_hit = self.position.pnl_pct(low) <= STOP_LOSS_PCT
        tp_hit = self.position.pnl_pct(high) >= TAKE_PROFIT_PCT

        # Conservative: if both possible in same bar, assume SL hit first
        if sl_hit and tp_hit:
            return "SL"
        if sl_hit:
            return "SL"
        if tp_hit:
            return "TP"
        return None

    def close_position(self, price, ts, reason):
        """Close current position at given price."""
        if self.position is None:
            return
        pnl = self.position.pnl_usd(price)
        self.balance += self.position.margin + pnl
        self.trades.append({
            "entry_time": self.position.entry_time,
            "entry_price": self.position.entry_price,
            "exit_time": ts,
            "exit_price": price,
            "pnl_usd": round(pnl, 2),
            "pnl_pct": round(self.position.pnl_pct(price), 2),
            "reason": reason,
            "size_usd": round(self.position.size_usd, 2),
        })
        self.position = None

    def open_long(self, price, ts):
        """Open a new long position."""
        if self.position is not None:
            return  # already in a position
        margin = self.balance * MAX_POSITION_PCT
        size_usd = margin * LEVERAGE
        self.balance -= margin
        self.position = Position(price, ts, size_usd, margin)

    def process_candle(self, candle, action):
        """Process one candle: check SL/TP first, then apply signal.
        Returns a string describing what happened."""
        ts = candle["timestamp"]
        self._last_price = candle["close"]

        # 1. Check SL / TP
        sl_tp = self.check_sl_tp(candle)
        if sl_tp:
            exit_price = (self.position.entry_price * (1 + STOP_LOSS_PCT / 100 / LEVERAGE)
                          if sl_tp == "SL"
                          else self.position.entry_price * (1 + TAKE_PROFIT_PCT / 100 / LEVERAGE))
            self.close_position(exit_price, ts, sl_tp)
            self._update_drawdown(ts)
            return f"{sl_tp} @ ${exit_price:,.0f}"

        # 2. Apply signal
        result = "No Position" if self.position is None else f"In Position (PnL {self.position.pnl_pct(candle['close']):+.1f}%)"

        if action == "BUY" and self.position is None:
            self.open_long(candle["close"], ts)
            result = f"-> OPEN LONG @ ${candle['close']:,.0f}"
        elif action == "SELL" and self.position is not None:
            self.close_position(candle["close"], ts, "SIGNAL")
            result = f"-> CLOSE @ ${candle['close']:,.0f}"

        self._update_drawdown(ts)
        return result

    def summary(self):
        """Return summary stats dict."""
        wins = [t for t in self.trades if t["pnl_usd"] > 0]
        losses = [t for t in self.trades if t["pnl_usd"] <= 0]
        gross_profit = sum(t["pnl_usd"] for t in wins) if wins else 0
        gross_loss = abs(sum(t["pnl_usd"] for t in losses)) if losses else 0
        pf = (gross_profit / gross_loss) if gross_loss > 0 else float("inf") if gross_profit > 0 else 0

        final_eq = self.equity
        ret = (final_eq - self.starting_balance) / self.starting_balance * 100

        return {
            "starting_balance": self.starting_balance,
            "final_equity": round(final_eq, 2),
            "return_pct": round(ret, 2),
            "total_trades": len(self.trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins) / len(self.trades) * 100, 1) if self.trades else 0,
            "profit_factor": round(pf, 2),
            "max_drawdown_pct": round(self.max_drawdown, 2),
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(gross_loss, 2),
        }


# ============================================================================
# COMPLETED CANDLE DETECTION (skip already-processed timestamps)
# ============================================================================

def load_completed_candles(symbol):
    """Scan all existing candle_log CSVs for this symbol and return a dict
    mapping timestamp_str -> (action, confidence, per_model_votes).
    This lets us skip API calls for candles we've already processed."""
    completed = {}
    if not OUTPUT_DIR.exists():
        return completed

    for csv_path in OUTPUT_DIR.glob(f"candle_log_{symbol}_*.csv"):
        try:
            df = pd.read_csv(csv_path)
            for _, row in df.iterrows():
                ts = str(row["timestamp"])
                # Reconstruct vote columns
                per_model = {}
                for col in df.columns:
                    if col.startswith("vote_"):
                        provider = col.replace("vote_", "")
                        if pd.notna(row[col]):
                            per_model[provider] = row[col]
                completed[ts] = (row["action"], int(row["confidence"]), per_model)
        except Exception as e:
            cprint(f"Warning: could not read {csv_path.name}: {e}", "yellow")

    return completed


# ============================================================================
# CHECKPOINT (resume support)
# ============================================================================

def checkpoint_path(symbol, start_date, end_date):
    return OUTPUT_DIR / f"checkpoint_{symbol}_{start_date:%Y%m%d}_{end_date:%Y%m%d}.json"


def save_checkpoint(state, symbol, start_date, end_date):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    p = checkpoint_path(symbol, start_date, end_date)
    with open(p, "w") as f:
        json.dump(state, f, indent=2, default=str)


def load_checkpoint(symbol, start_date, end_date):
    p = checkpoint_path(symbol, start_date, end_date)
    if not p.exists():
        return None
    with open(p) as f:
        return json.load(f)


# ============================================================================
# MAIN BACKTEST LOOP
# ============================================================================

def run_backtest(symbol, start_date, end_date, resume=False):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Fetch data
    df = fetch_data(symbol, start_date, end_date, LOOKBACK_BARS)

    # Determine backtest window indices
    bt_mask = (df["timestamp"] >= start_date) & (df["timestamp"] <= end_date)
    bt_indices = df.index[bt_mask].tolist()

    if not bt_indices:
        cprint("No candles in the requested date range!", "red")
        return

    total_candles = len(bt_indices)
    cprint(f"\nBacktest window: {total_candles} candles ({start_date} to {end_date})", "yellow", attrs=["bold"])

    # Resume support
    start_offset = 0
    candle_log = []
    sim_state = None

    if resume:
        ckpt = load_checkpoint(symbol, start_date, end_date)
        if ckpt:
            start_offset = ckpt["next_candle_idx"]
            candle_log = ckpt.get("candle_log", [])
            sim_state = ckpt.get("sim_state")
            cprint(f"Resuming from candle {start_offset}/{total_candles}", "green")
        else:
            cprint("No checkpoint found, starting fresh", "yellow")

    # Init simulator
    sim = Simulator(STARTING_BALANCE)
    if sim_state:
        sim.balance = sim_state["balance"]
        sim.trades = sim_state["trades"]
        sim.peak_equity = sim_state["peak_equity"]
        sim.max_drawdown = sim_state["max_drawdown"]
        sim.equity_curve = [(e[0], e[1]) for e in sim_state.get("equity_curve", [])]
        if sim_state.get("position"):
            p = sim_state["position"]
            sim.position = Position(p["entry_price"], p["entry_time"], p["size_usd"], p["margin"])
        sim._last_price = sim_state.get("last_price", 0)

    # Load already-completed candles to skip redundant API calls
    completed = load_completed_candles(symbol)
    skip_count = 0
    if completed:
        # Count how many of our backtest candles are already done
        for idx in bt_indices[start_offset:]:
            ts_str = str(df.iloc[idx]["timestamp"])
            if ts_str in completed:
                skip_count += 1
        if skip_count > 0:
            cprint(f"Found {skip_count}/{total_candles - start_offset} candles already completed — will reuse cached votes", "green")

    # Init swarm (only if we have new candles to process)
    new_candles = (total_candles - start_offset) - skip_count
    swarm = None
    if new_candles > 0:
        swarm = SwarmAgent()
    cprint(f"\nStarting backtest loop... ({new_candles} new + {skip_count} cached = {total_candles - start_offset} candles)\n", "cyan", attrs=["bold"])

    api_call_count = 0
    cached_count = 0
    start_time = time.time()

    for i in range(start_offset, total_candles):
        bt_idx = bt_indices[i]
        candle = df.iloc[bt_idx]
        ts = candle["timestamp"]
        ts_str = str(ts)

        # Check if this candle was already processed
        if ts_str in completed:
            action, confidence, per_model = completed[ts_str]
            cached_count += 1
        else:
            # Need real API call — init swarm lazily if needed
            if swarm is None:
                swarm = SwarmAgent()

            # Build lookback window (the last LOOKBACK_BARS bars up to and including this candle)
            window_start = max(0, bt_idx - LOOKBACK_BARS + 1)
            window = df.iloc[window_start:bt_idx + 1].copy()

            # Format market data and query swarm
            prompt = format_market_data(symbol, window)

            try:
                swarm_result = swarm.query(prompt=prompt, system_prompt=SWARM_TRADING_PROMPT)
                api_call_count += 1
            except KeyboardInterrupt:
                cprint("\n\nInterrupted! Saving checkpoint...", "yellow", attrs=["bold"])
                _save_state(sim, candle_log, i, symbol, start_date, end_date)
                cprint(f"Checkpoint saved at candle {i}/{total_candles}. Use --resume to continue.", "green")
                return
            except Exception as e:
                cprint(f"Swarm error on candle {i}: {e}", "red")
                swarm_result = None

            # Parse votes
            if swarm_result:
                action, confidence, per_model = parse_votes(swarm_result)
            else:
                action, confidence, per_model = "NOTHING", 0, {}

        # Simulate
        event = sim.process_candle(candle.to_dict(), action)

        # Per-model vote string
        vote_parts = []
        for prov, vote in per_model.items():
            vote_parts.append(f"{prov.capitalize()}: {vote}")
        votes_str = " | ".join(vote_parts)

        # Print progress line
        label = f"[{i+1}/{total_candles}]"
        ts_fmt = ts.strftime("%Y-%m-%d %H:%M") if hasattr(ts, "strftime") else str(ts)
        price_str = f"${candle['close']:,.0f}"
        consensus_str = f"{action} {confidence}%"
        source_tag = "(cached)" if ts_str in completed else ""

        line = f"{label} {ts_fmt} | {symbol} {price_str} | {votes_str} | Consensus: {consensus_str} | {event} {source_tag}"
        color = "green" if "OPEN" in event else "red" if ("CLOSE" in event or "SL" in event) else "cyan" if "TP" in event else "white"
        cprint(line, color)

        # Log
        candle_log.append({
            "candle_num": i + 1,
            "timestamp": str(ts),
            "close": candle["close"],
            "action": action,
            "confidence": confidence,
            "votes": per_model,
            "event": event,
            "equity": round(sim.equity, 2),
        })

        # Auto-checkpoint every 10 candles
        if (i + 1) % 10 == 0:
            _save_state(sim, candle_log, i + 1, symbol, start_date, end_date)

    # Final results
    elapsed = time.time() - start_time
    stats = sim.summary()

    cprint("\n" + "=" * 70, "cyan")
    cprint(f"  SWARM BACKTEST -- {symbol} {TIMEFRAME} -- {start_date:%b %d} to {end_date:%b %d} {end_date.year}", "cyan", attrs=["bold"])
    cprint("=" * 70, "cyan")
    cprint(f"  Starting: ${stats['starting_balance']:,.0f} | Final: ${stats['final_equity']:,.2f} | Return: {stats['return_pct']:+.2f}%", "green" if stats["return_pct"] > 0 else "red")
    cprint(f"  Trades: {stats['total_trades']} | Wins: {stats['wins']} | Losses: {stats['losses']} | Win Rate: {stats['win_rate']}%", "white")
    cprint(f"  PF: {stats['profit_factor']} | Max DD: {stats['max_drawdown_pct']}% | Gross P: ${stats['gross_profit']:,.2f} | Gross L: ${stats['gross_loss']:,.2f}", "white")
    cprint(f"  API calls: {api_call_count} new + {cached_count} cached | Runtime: {elapsed/60:.1f} min | Cost est: ${api_call_count * 0.03:.2f}", "yellow")
    cprint("=" * 70 + "\n", "cyan")

    # Save outputs
    _save_outputs(sim, candle_log, stats, symbol, start_date, end_date)

    # Clean up checkpoint
    cp = checkpoint_path(symbol, start_date, end_date)
    if cp.exists():
        cp.unlink()
        cprint("Checkpoint cleaned up (backtest complete).", "green")


def _save_state(sim, candle_log, next_idx, symbol, start_date, end_date):
    """Save checkpoint for resume."""
    pos_data = None
    if sim.position:
        pos_data = {
            "entry_price": sim.position.entry_price,
            "entry_time": str(sim.position.entry_time),
            "size_usd": sim.position.size_usd,
            "margin": sim.position.margin,
        }
    state = {
        "next_candle_idx": next_idx,
        "candle_log": candle_log,
        "sim_state": {
            "balance": sim.balance,
            "trades": sim.trades,
            "position": pos_data,
            "peak_equity": sim.peak_equity,
            "max_drawdown": sim.max_drawdown,
            "equity_curve": sim.equity_curve,
            "last_price": getattr(sim, "_last_price", 0),
        }
    }
    save_checkpoint(state, symbol, start_date, end_date)


def _save_outputs(sim, candle_log, stats, symbol, start_date, end_date):
    """Save trade log, candle log, and summary."""
    suffix = f"{symbol}_{start_date:%Y%m%d}_{end_date:%Y%m%d}"

    # Trades CSV
    if sim.trades:
        trades_df = pd.DataFrame(sim.trades)
        trades_path = OUTPUT_DIR / f"trades_{suffix}.csv"
        trades_df.to_csv(trades_path, index=False)
        cprint(f"Trades saved: {trades_path.relative_to(Path(project_root))}", "green")

    # Candle log CSV
    log_df = pd.DataFrame(candle_log)
    log_path = OUTPUT_DIR / f"candle_log_{suffix}.csv"
    # Flatten votes dict to columns
    if "votes" in log_df.columns:
        votes_expanded = log_df["votes"].apply(pd.Series)
        votes_expanded.columns = [f"vote_{c}" for c in votes_expanded.columns]
        log_df = pd.concat([log_df.drop(columns=["votes"]), votes_expanded], axis=1)
    log_df.to_csv(log_path, index=False)
    cprint(f"Candle log saved: {log_path.relative_to(Path(project_root))}", "green")

    # Summary JSON
    summary_path = OUTPUT_DIR / f"summary_{suffix}.json"
    with open(summary_path, "w") as f:
        json.dump(stats, f, indent=2)
    cprint(f"Summary saved: {summary_path.relative_to(Path(project_root))}", "green")


# ============================================================================
# SHOW RESULTS
# ============================================================================

def show_results():
    """Show the most recent backtest results from output dir."""
    if not OUTPUT_DIR.exists():
        cprint("No results found. Run a backtest first.", "yellow")
        return

    summaries = sorted(OUTPUT_DIR.glob("summary_*.json"), key=os.path.getmtime, reverse=True)
    if not summaries:
        cprint("No summary files found.", "yellow")
        return

    for sp in summaries[:5]:
        with open(sp) as f:
            stats = json.load(f)
        name = sp.stem.replace("summary_", "")
        ret_color = "green" if stats["return_pct"] > 0 else "red"
        cprint(f"\n  {name}", "cyan", attrs=["bold"])
        cprint(f"    Return: {stats['return_pct']:+.2f}% | Final: ${stats['final_equity']:,.2f}", ret_color)
        cprint(f"    Trades: {stats['total_trades']} | WR: {stats['win_rate']}% | PF: {stats['profit_factor']} | Max DD: {stats['max_drawdown_pct']}%", "white")


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Swarm Backtester — Historical AI Voting Simulation")
    parser.add_argument("--start", type=str, default="2026-02-24", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default="2026-02-26", help="End date (YYYY-MM-DD)")
    parser.add_argument("--symbol", type=str, default=SYMBOL, help="Trading symbol (default: BTC)")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    parser.add_argument("--results", action="store_true", help="Show last results and exit")
    args = parser.parse_args()

    if args.results:
        show_results()
        return

    start_date = datetime.strptime(args.start, "%Y-%m-%d")
    end_date = datetime.strptime(args.end, "%Y-%m-%d") + timedelta(hours=23, minutes=59)

    cprint("\n" + "=" * 70, "cyan")
    cprint("  SWARM BACKTESTER — Historical AI Voting Simulation", "cyan", attrs=["bold"])
    cprint("=" * 70, "cyan")
    cprint(f"  Symbol: {args.symbol} | Timeframe: {TIMEFRAME} | Lookback: {LOOKBACK_BARS} bars", "white")
    cprint(f"  Period: {start_date:%Y-%m-%d} to {end_date:%Y-%m-%d}", "white")
    cprint(f"  Balance: ${STARTING_BALANCE:,.0f} | Leverage: {LEVERAGE}x | SL: {STOP_LOSS_PCT}% | TP: {TAKE_PROFIT_PCT}%", "white")
    cprint(f"  Mode: {'Long Only' if LONG_ONLY else 'Long/Short'}", "white")
    cprint("=" * 70 + "\n", "cyan")

    run_backtest(args.symbol, start_date, end_date, resume=args.resume)


if __name__ == "__main__":
    main()
