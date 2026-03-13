#!/usr/bin/env python3
"""
Research Extractor — Sends selected trading ideas to DeepSeek to extract
structured strategy specifications for Claude to code as backtests.

Pipeline step 2: ideas_scored.csv → DeepSeek research specs → research/ folder

Usage:
    ./venv/bin/python3 src/scripts/research_extractor.py          # Extract all 10 specs
    ./venv/bin/python3 src/scripts/research_extractor.py --dry-run # Show ideas without calling API
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

PROJECT_ROOT = Path(__file__).parent.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "src" / "data" / "rbi" / "02_26_2026" / "research_v2"

DEEPSEEK_MODEL = "deepseek-chat"

# 10 selected ideas — one per diverse category, all score 10
SELECTED_IDEAS = {
    "01_MACD_Volume_BBTouch": {
        "id": 2275,
        "idea": "Enter long positions when price breaches the lower Bollinger Band accompanied by a spike in volume exceeding 1.5x the 20-day average and MACD histogram crosses above zero, exiting at the middle band."
    },
    "02_GoldenCross_VolumeSpike": {
        "id": 2889,
        "idea": "Trade breakouts when the 50-day moving average crosses the 200-day while volume spikes above its 20-day average, with exits triggered by a 2x ATR stop or 5% trailing stop."
    },
    "03_BBSqueeze_ATRBreakout": {
        "id": 1456,
        "idea": "A volatility squeeze breakout strategy that enters long when Bollinger Bands contract to their narrowest point in 20 days and price closes above the upper band, with exits based on a trailing ATR stop set at 2x the average true range."
    },
    "04_Donchian_ADX_Volume": {
        "id": 3386,
        "idea": "A breakout strategy that triggers when price crosses a 20-day high/low while the ADX rises above 25 and volume exceeds its 10-day average, with exits on a 2:1 risk-reward ratio."
    },
    "05_BBSqueeze_RSIDivergence": {
        "id": 1195,
        "idea": "A volatility squeeze strategy that enters trades when Bollinger Bands contract to their narrowest point in 30 days and exits when price breaks out with a 2x ATR move, combined with a confirming RSI divergence."
    },
    "06_OBVDivergence_BBTouch": {
        "id": 495,
        "idea": "Trade long when price touches the lower Bollinger Band while OBV diverges positively, exiting at the middle band, and short on upper band touch with negative OBV divergence, exiting at middle band."
    },
    "07_Vortex_ElderForce": {
        "id": 3410,
        "idea": "A trend-following strategy using the Vortex Indicator's VI+ and VI- crossover combined with Elder Force Index confirmation, exiting on a trailing stop-loss set at 2x the 14-period ATR."
    },
    "08_Fisher_VortexDivergence": {
        "id": 1964,
        "idea": "Combine Fisher Transform and Vortex Indicator divergence with volume confirmation, entering trades when Fisher reverses direction against the Vortex trend on above-average volume, exiting when ADX slope flattens below 25."
    },
    "09_ATRBreakout_VolumeSpike": {
        "id": 560,
        "idea": "Trade breakouts when the 20-period ATR exceeds its 90-day high and volume spikes above its 30-day average, with exits based on a 2:1 risk-reward ratio."
    },
    "10_BBWidth_StochRSI": {
        "id": 2099,
        "idea": "Trade volatility contractions using Bollinger Bandwidth percentile under 20 combined with a momentum confirmation from Stochastic RSI, exiting at opposing Bollinger Band touch or 2:1 risk-reward."
    },
}

SYSTEM_PROMPT = """You are a quantitative trading strategy researcher. Your job is to take a trading idea
and produce a precise, unambiguous specification that a programmer can implement as a backtest.

The target market is CRYPTO SPOT (BTC, ETH, SOL) on 15-MINUTE candles using OHLCV data only.
The backtesting framework is backtesting.py (Python). Indicators come from pandas_ta or talib.

OUTPUT FORMAT — Return a JSON object with these exact keys:

{
  "strategy_name": "CamelCase name, max 25 chars",
  "description": "One paragraph explaining the strategy logic",
  "indicators": [
    {"name": "indicator_name", "library": "pandas_ta or talib", "params": {"period": 20, ...}},
    ...
  ],
  "entry_long": {
    "conditions": ["exact condition 1 using indicator names", "condition 2", ...],
    "logic": "ALL conditions must be true (AND) / ANY condition (OR)"
  },
  "entry_short": {
    "conditions": ["exact condition 1", ...],
    "logic": "ALL / ANY"
  },
  "exit_long": {
    "conditions": ["exact exit condition 1", ...],
    "stop_loss": "description with exact multiplier/percentage",
    "take_profit": "description with exact multiplier/percentage"
  },
  "exit_short": {
    "conditions": ["exact exit condition 1", ...],
    "stop_loss": "description",
    "take_profit": "description"
  },
  "position_sizing": "fixed 100% equity per trade (backtesting.py default)",
  "parameters": {"param_name": value, ...},
  "expected_trade_frequency": "estimate trades per 1000 candles",
  "notes": "any implementation warnings or edge cases"
}

RULES:
1. Be SPECIFIC — "RSI(14) < 30" not "RSI is oversold"
2. Every indicator must have exact parameters (period, multiplier, etc.)
3. Entry conditions must be testable on a single candle (no future looking)
4. Stop loss and take profit must be numeric (e.g., "2x ATR(14)" or "5% from entry")
5. If the idea is vague on exits, add a sensible default (e.g., 2x ATR trailing stop)
6. If the idea mentions only long, make short the mirror image
7. Indicators must be available in pandas_ta or talib — no custom/exotic ones
8. Keep it simple — 3-5 indicators max, 2-4 entry conditions max
9. For divergence detection: specify the lookback window and how to detect it programmatically
   (e.g., "price makes lower low over 14 bars while RSI makes higher low over same 14 bars")
10. Return ONLY the JSON object, no markdown wrapping, no extra text
"""


def extract_spec(client, idea_name, idea_text):
    """Send one idea to DeepSeek, return structured spec."""
    user_prompt = f"""Extract a precise backtest specification from this trading idea:

IDEA: {idea_text}

Return the JSON specification. Remember: crypto 15-minute candles, OHLCV only, pandas_ta/talib indicators."""

    response = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
        max_tokens=2048,
        stream=False,
    )
    content = (response.choices[0].message.content or "").strip()

    # Strip markdown code fences if present
    if content.startswith("```"):
        lines = content.split("\n")
        # Remove first and last fence lines
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines)

    # Validate JSON
    try:
        spec = json.loads(content)
    except json.JSONDecodeError as e:
        print(f"  WARNING: Invalid JSON from DeepSeek for {idea_name}: {e}")
        spec = {"raw_text": content, "parse_error": str(e)}

    return spec, response.usage


def main():
    parser = argparse.ArgumentParser(description="Extract structured research specs from ideas")
    parser.add_argument("--dry-run", action="store_true", help="Show ideas without calling API")
    args = parser.parse_args()

    api_key = os.getenv("DEEPSEEK_KEY")
    if not api_key and not args.dry_run:
        print("ERROR: DEEPSEEK_KEY not found in .env")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"=== Research Extractor ===")
    print(f"Model: {DEEPSEEK_MODEL}")
    print(f"Output: {OUTPUT_DIR}")
    print(f"Ideas: {len(SELECTED_IDEAS)}")
    print()

    if args.dry_run:
        for name, info in SELECTED_IDEAS.items():
            print(f"  {name} [ID={info['id']}]")
            print(f"    {info['idea']}")
            print()
        print("Dry run — no API calls made.")
        return

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    total_input = 0
    total_output = 0
    results = {}

    for name, info in SELECTED_IDEAS.items():
        out_file = OUTPUT_DIR / f"{name}_spec.json"
        if out_file.exists():
            print(f"  SKIP {name} — already exists")
            with open(out_file) as f:
                results[name] = json.load(f)
            continue

        print(f"  Extracting: {name} [ID={info['id']}]...")
        spec, usage = extract_spec(client, name, info["idea"])

        # Save
        with open(out_file, "w") as f:
            json.dump(spec, f, indent=2)

        results[name] = spec
        tokens_in = usage.prompt_tokens if usage else 0
        tokens_out = usage.completion_tokens if usage else 0
        total_input += tokens_in
        total_output += tokens_out
        print(f"    OK — {tokens_in} in / {tokens_out} out tokens")
        print(f"    Strategy: {spec.get('strategy_name', 'N/A')}")
        print(f"    Indicators: {len(spec.get('indicators', []))}")

        time.sleep(0.5)  # rate limit courtesy

    print()
    print(f"=== Done ===")
    print(f"Total tokens: {total_input} in / {total_output} out")
    est_cost = (total_input * 0.14 + total_output * 0.28) / 1_000_000
    print(f"Estimated cost: ${est_cost:.4f}")
    print(f"Specs saved to: {OUTPUT_DIR}")

    # Summary
    print()
    print("=== Strategy Summary ===")
    for name, spec in results.items():
        sname = spec.get("strategy_name", "N/A")
        n_ind = len(spec.get("indicators", []))
        n_entry = len(spec.get("entry_long", {}).get("conditions", []))
        print(f"  {name}: {sname} ({n_ind} indicators, {n_entry} entry conditions)")


if __name__ == "__main__":
    main()
