#!/usr/bin/env python3
"""
Idea Filter — Uses DeepSeek (cheap) to score and rank trading ideas
for crypto 15m timeframe compatibility before Claude writes backtest code.

Pipeline: ideas.txt → DeepSeek scores in batches → ranked output CSV

Usage:
    ./venv/bin/python3 src/scripts/idea_filter.py                  # Score all unscored ideas
    ./venv/bin/python3 src/scripts/idea_filter.py --top 30         # Show top 30 after scoring
    ./venv/bin/python3 src/scripts/idea_filter.py --results        # Show existing results
    ./venv/bin/python3 src/scripts/idea_filter.py --batch-size 50  # Process 50 ideas per API call
"""

import os
import sys
import csv
import json
import time
import argparse
import hashlib
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).parent.parent.parent
IDEAS_FILE = PROJECT_ROOT / "src" / "data" / "rbi" / "ideas.txt"
OUTPUT_FILE = PROJECT_ROOT / "src" / "data" / "rbi" / "ideas_scored.csv"
PROCESSED_FILE = PROJECT_ROOT / "src" / "data" / "rbi" / "ideas_filter_log.txt"

# DeepSeek is ~$0.14/M input, $0.28/M output tokens — very cheap for bulk filtering
DEEPSEEK_MODEL = "deepseek-chat"
BATCH_SIZE = 20  # ideas per API call (balances cost vs context quality)

SYSTEM_PROMPT = """You are a quantitative trading strategy evaluator. Your job is to score trading ideas
for their compatibility with CRYPTO SPOT markets (BTC, ETH, SOL) on a 15-MINUTE timeframe using
OHLCV data only (Open, High, Low, Close, Volume — NO external data feeds).

For each idea, return a JSON object with:
- "score": integer 1-10 (10 = perfect fit for crypto 15m OHLCV)
- "reason": one-line explanation (max 15 words)
- "kill": true if the idea is fundamentally incompatible, false otherwise

SCORE GUIDE:
- 10: Uses only price/volume indicators (RSI, BB, MACD, ATR, EMA, SMA, volume), clear entry/exit rules, works on any liquid asset
- 8-9: Good indicator combo, minor adaptation needed, clear logic
- 6-7: Decent concept but vague entry/exit rules or might need parameter tuning
- 4-5: Partially applicable — references stocks but core logic works on crypto
- 2-3: Mostly incompatible — references options, VIX, sectors, earnings, or requires external data
- 1: Completely incompatible — needs options chains, VIX futures, S&P500, stock-specific data, or is just a title with no strategy

KILL = true for ANY of these:
- Requires VIX, options, puts, calls, gamma, implied volatility, option chains
- Requires stock-specific data (earnings, short interest, analyst ratings, sector rotation)
- Requires external feeds not in OHLCV (open interest, funding rates, liquidation data, order book)
- Is just a title or category name with no actual strategy description
- Requires multi-asset correlation or pairs trading between different instruments
- References specific stock tickers or equity indices as the trading instrument

IMPORTANT: Respond ONLY with a JSON array, no markdown, no explanation outside the array.
Each element must have keys: "id", "score", "reason", "kill"
"""


def load_ideas():
    """Load all ideas from ideas.txt, one per line"""
    with open(IDEAS_FILE, "r") as f:
        ideas = [line.strip() for line in f if line.strip()]
    return ideas


def hash_idea(idea):
    return hashlib.md5(idea.encode()).hexdigest()[:12]


def load_processed():
    """Load already-processed idea hashes"""
    if not PROCESSED_FILE.exists():
        return set()
    with open(PROCESSED_FILE, "r") as f:
        return {line.strip() for line in f if line.strip()}


def save_processed(hashes):
    """Append processed hashes to log"""
    with open(PROCESSED_FILE, "a") as f:
        for h in hashes:
            f.write(h + "\n")


def load_existing_scores():
    """Load existing scored results"""
    if not OUTPUT_FILE.exists():
        return []
    with open(OUTPUT_FILE, "r") as f:
        reader = csv.DictReader(f)
        return list(reader)


def save_scores(rows, append=True):
    """Save scores to CSV"""
    file_exists = OUTPUT_FILE.exists() and append
    mode = "a" if append else "w"
    with open(OUTPUT_FILE, mode, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "score", "kill", "reason", "idea"])
        if not file_exists:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)


def score_batch(ideas_batch, start_idx):
    """Send a batch of ideas to DeepSeek for scoring"""
    from openai import OpenAI

    client = OpenAI(
        api_key=os.environ["DEEPSEEK_KEY"],
        base_url="https://api.deepseek.com"
    )

    # Format ideas with IDs
    numbered = []
    for i, idea in enumerate(ideas_batch):
        numbered.append(f"[{start_idx + i}] {idea}")
    user_content = "\n".join(numbered)

    response = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content}
        ],
        temperature=0.1,
        max_tokens=4096,
    )

    content = response.choices[0].message.content.strip()

    # Strip markdown code fences if present
    if content.startswith("```"):
        content = content.split("\n", 1)[1]  # remove first line
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

    try:
        results = json.loads(content)
    except json.JSONDecodeError:
        print(f"  WARNING: Failed to parse JSON response, skipping batch")
        print(f"  Response was: {content[:200]}...")
        return []

    return results


def run_filter(batch_size=BATCH_SIZE, max_ideas=None):
    """Score all unscored ideas"""
    ideas = load_ideas()
    processed = load_processed()

    # Find unprocessed ideas
    to_process = []
    for i, idea in enumerate(ideas):
        h = hash_idea(idea)
        if h not in processed:
            to_process.append((i, idea, h))

    if max_ideas:
        to_process = to_process[:max_ideas]

    total = len(to_process)
    if total == 0:
        print("All ideas already scored.")
        return

    print(f"Scoring {total} ideas in batches of {batch_size}...")
    print(f"Estimated cost: ~${total * 0.0003:.2f} (DeepSeek)")

    scored = 0
    for batch_start in range(0, total, batch_size):
        batch = to_process[batch_start:batch_start + batch_size]
        ideas_batch = [idea for _, idea, _ in batch]
        indices = [idx for idx, _, _ in batch]
        hashes = [h for _, _, h in batch]

        print(f"  Batch {batch_start // batch_size + 1}/{(total + batch_size - 1) // batch_size} "
              f"(ideas {indices[0]}-{indices[-1]})...", end=" ", flush=True)

        try:
            results = score_batch(ideas_batch, indices[0])
        except Exception as e:
            print(f"ERROR: {e}")
            time.sleep(2)
            continue

        # Match results back to ideas
        rows = []
        for r in results:
            r_id = r.get("id", -1)
            # Find the matching idea by index
            matched_idea = None
            for idx, idea, h in batch:
                if idx == r_id:
                    matched_idea = idea
                    break
            if matched_idea is None and len(results) == len(batch):
                # Fallback: match by position
                pos = results.index(r)
                if pos < len(batch):
                    _, matched_idea, _ = batch[pos]

            rows.append({
                "id": r_id,
                "score": r.get("score", 0),
                "kill": r.get("kill", True),
                "reason": r.get("reason", ""),
                "idea": matched_idea or f"[idea {r_id}]"
            })

        save_scores(rows)
        save_processed(hashes)
        scored += len(results)
        print(f"OK ({len(results)} scored)")

        # Small delay to avoid rate limits
        time.sleep(0.5)

    print(f"\nDone. {scored} ideas scored. Results: {OUTPUT_FILE}")


def show_results(top_n=30):
    """Show top-scored ideas"""
    rows = load_existing_scores()
    if not rows:
        print("No results yet. Run without --results first.")
        return

    # Filter out killed ideas, sort by score descending
    alive = [r for r in rows if r["kill"].lower() != "true"]
    alive.sort(key=lambda r: int(r["score"]), reverse=True)

    killed = len(rows) - len(alive)
    print(f"\nTotal scored: {len(rows)} | Killed: {killed} | Alive: {len(alive)}")
    print(f"\nTop {min(top_n, len(alive))} ideas (score 1-10, higher = better fit for crypto 15m):\n")
    print(f"{'#':<4} {'Score':<6} {'Reason':<45} {'Idea'}")
    print("-" * 120)

    for i, r in enumerate(alive[:top_n], 1):
        idea_short = r["idea"][:65] + "..." if len(r["idea"]) > 65 else r["idea"]
        print(f"{i:<4} {r['score']:<6} {r['reason']:<45} {idea_short}")

    print(f"\nFull results: {OUTPUT_FILE}")
    print(f"Top ideas ready for DeepSeek research → Claude backtest coding")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Idea Filter — Score trading ideas with DeepSeek")
    parser.add_argument("--results", action="store_true", help="Show existing scored results")
    parser.add_argument("--top", type=int, default=30, help="Number of top ideas to show")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE, help="Ideas per API call")
    parser.add_argument("--max", type=int, default=None, help="Max ideas to process (for testing)")
    args = parser.parse_args()

    if args.results:
        show_results(args.top)
    else:
        run_filter(batch_size=args.batch_size, max_ideas=args.max)
        print()
        show_results(args.top)
