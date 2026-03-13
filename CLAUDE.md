# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an experimental AI trading system that orchestrates 48+ specialized AI agents to analyze markets, execute strategies, and manage risk across cryptocurrency markets (primarily Solana). The project uses a modular agent architecture with unified LLM provider abstraction supporting Claude, GPT-4, DeepSeek, Groq, Gemini, and local Ollama models.

This is a forked/cloned repo — not originally authored by the current user. We are adapting it to our environment and goals.

## Current Environment

### Python Environment
```bash
# Use the project venv (NOT conda, NOT system python)
# Python binary:
/Users/juanignaciopercovich/Desktop/personal-projects/moon-dev-ai-agents/venv/bin/python3
# Version: Python 3.12.12

# Install packages:
./venv/bin/pip install <package>

# IMPORTANT: Always use the venv python for running scripts:
./venv/bin/python3 src/scripts/your_script.py
```

### Installed Packages (verified working)
- backtesting.py (Backtesting library)
- pandas, numpy
- pandas_ta (technical indicators)
- TA-Lib (C library + Python wrapper — installed via brew + pip)
- anthropic (Claude API)
- All packages from requirements.txt

### API Keys Configured (in .env)
- `ANTHROPIC_KEY` — Claude models
- `DEEPSEEK_KEY` — DeepSeek models (cheap reasoning, good for code generation)

### API Keys NOT Configured (needed for live trading)
- `BIRDEYE_API_KEY` — Solana token data (needed for market data)
- `RPC_ENDPOINT` — Helius Solana RPC (needed for blockchain interaction)
- `SOLANA_PRIVATE_KEY` — Trading wallet (needed for executing trades)
- `OPENAI_KEY` — GPT models (rbi_agent currently configured for gpt-5, needs switching to deepseek)
- `COINGECKO_API_KEY`, `MOONDEV_API_KEY`, `GROQ_API_KEY`, etc. — optional enhancements

## Current Project Status

### Phase: AI Swarm Live Trading on HyperLiquid
We pivoted from backtesting (0/179 TA strategies profitable on 15m) to Moon Dev's actual approach:
- **AI Swarm voting** (Claude + DeepSeek) analyzes 1H OHLCV data from HyperLiquid
- **HyperLiquid perps** — free data API, BTC/ETH/SOL perpetual futures
- **Observation mode active** — system runs but doesn't place real trades yet
- Next step: fund wallet ($50-100 USDC on Arbitrum) and switch to live

### What We've Done
- Explored full repo structure and understood all 57 agents
- Built `src/scripts/batch_backtest_runner.py` to batch-run existing backtests
- Ran all 152 "runnable" backtests from historical RBI output — 55 ran, 4 profitable on BTC
- Built `src/scripts/data_fetcher.py` — CCXT + Binance data fetcher (no API key needed, paginated, multi-pair)
- Fetched fresh OHLCV data: BTC, ETH, SOL — 110,677 candles each (2023-01-01 to 2026-02-26, 15m)
- Built `src/scripts/multi_asset_validation.py` — runs strategies across BTC/ETH/SOL, pass/fail verdict
- Multi-asset validation: VolumetricBollinger + RangeBoundPut passed (3/3 assets), VolSurgeReversion failed
- Built `src/scripts/subperiod_validation.py` — splits data into two periods, tests regime consistency
- Sub-period validation: **Both surviving strategies FAILED** — profitable only in 2023-2024, lost money on ETH/SOL in 2024-2026
- **0 of 152 existing strategies survived the full validation pipeline**
- Switched RBI agent from GPT-5 (no key) to DeepSeek (deepseek-chat + deepseek-reasoner)
- Fixed DeepSeek reasoner model: removed unsupported `temperature` param, increased `max_tokens`, handled None content
- Increased `AI_MAX_TOKENS` from 1024 to 4096 in config.py for backtest code generation
- Created training-only data splits: `BTC/ETH/SOL-USD-15m-train.csv` (2023-01 to 2025-06, holdout: 2025-07 to 2026-02)
- Launched RBI agent to generate new strategies from the 4,481 idea pool using DeepSeek + training data only
- New strategies output to `src/data/rbi/02_26_2026/backtests_final/`
- Full run log: `src/data/rbi/02_26_2026/rbi_run_log.txt`
- Built `src/scripts/idea_filter.py` — scored all 4,481 ideas with DeepSeek ($0.50 cost). 57% are BB squeeze variants.
- Built `src/scripts/research_extractor.py` — sends ideas to DeepSeek for structured JSON specs ($0.003 cost)
- Built `src/scripts/run_v2_backtests.py` — batch-runs v2 backtests with summary table
- **Filtered idea pool → DeepSeek research specs → Claude backtests: 15 strategies tested, ALL LOST MONEY**
- **Hand-crafted structural strategies (momentum, RSI bounce, trend+ADX, vol reversion, range break): ALL LOST MONEY**
- **Conclusion: Standard TA indicators on 15m crypto have no edge. Must pivot approach.**
- Built `src/scripts/swarm_backtester.py` — replays historical candles through real AI swarm, simulates positions with SL/TP
- **First swarm backtest (BTC 1H, Feb 24-26): +4.47% return, PF 2.69, max DD -2.18%, 7 trades**
- Extended swarm backtest to 20 days (Feb 20 - Mar 11): +5.95% return, PF 1.28, max DD -4.92%, 41 trades
- Built `src/scripts/swarm_dashboard.py` — real-time Dash + Plotly dashboard for swarm backtests
  - Candlestick charts with trade markers, equity curve, AI vote bars
  - Live terminal showing each agent's vote as candles are processed
  - Can launch/stop backtests from UI, auto-refreshes every 3 seconds
  - Run: `PYTHONPATH=. ./venv/bin/python3 src/scripts/swarm_dashboard.py` → http://localhost:8050
- Modified swarm_backtester to write `live_feed.jsonl` (one line per candle) for real-time dashboard updates
- Installed `streamlit`, `plotly`, `dash` packages

### Available Backtest Data
| File | Pair | Candles | Date Range |
|------|------|---------|------------|
| `src/data/rbi/BTC-USD-15m.csv` | BTC/USDT | 110,677 | 2023-01-01 → 2026-02-26 |
| `src/data/rbi/ETH-USD-15m.csv` | ETH/USDT | 110,677 | 2023-01-01 → 2026-02-26 |
| `src/data/rbi/SOL-USD-15m.csv` | SOL/USDT | 110,677 | 2023-01-01 → 2026-02-26 |
| `src/data/rbi/BTC-USD-15m-train.csv` | BTC/USDT | 87,547 | 2023-01-01 → 2025-06-30 |
| `src/data/rbi/ETH-USD-15m-train.csv` | ETH/USDT | 87,547 | 2023-01-01 → 2025-06-30 |
| `src/data/rbi/SOL-USD-15m-train.csv` | SOL/USDT | 87,547 | 2023-01-01 → 2025-06-30 |

**Training/holdout split**: `-train.csv` files are used by the RBI agent for strategy generation. The holdout period (2025-07 to 2026-02, ~23,130 candles) is reserved for out-of-sample validation. Never let the RBI agent see the holdout data.

To refresh data: `./venv/bin/python3 src/scripts/data_fetcher.py --update-rbi`
To fetch other pairs/timeframes: `./venv/bin/python3 src/scripts/data_fetcher.py --help`

### Existing Backtest Quality Issues
- 1,277 total BTFinal files exist, but only 152 are "complete" (have print(stats))
- Of those 152, only 55 actually execute without errors (36.2% success rate)
- Common failures: truncated AI output, broken emoji f-strings, wrong data paths, backtesting.lib imports
- The batch runner auto-fixes: data paths, markdown wrapping, backtesting.lib imports, broken print statements
- Most strategies generated 0 trades — conditions too restrictive or indicators didn't match the data

### Batch Run Results — BTC 3-Year (2026-02-26)
- **152 tested → 55 ran → 27 with 10+ trades → 4 profitable**
- Full results: `src/data/backtest_results.csv`

| Strategy | Return | Sharpe | Max DD | Win Rate | Trades | PF |
|---|---|---|---|---|---|---|
| VolumetricBollinger | +103.3% | 0.86 | -30.7% | 80.0% | 45 | 1.88 |
| VolSurgeReversion | +22.6% | 0.68 | -10.0% | 61.5% | 96 | 1.54 |
| RangeBoundPut | +14.7% | 0.96 | -5.1% | 82.9% | 35 | 2.27 |
| VolumetricBreakout | +0.8% | 0.04 | -12.7% | 40.0% | 30 | 0.89 |

**Discarded (failed out-of-sample):** VIXContraMomentum (-8.5%), VolatilitySurge (-27.7%)

### Multi-Asset Validation Results (2026-02-26)
- Script: `src/scripts/multi_asset_validation.py`
- Results: `src/data/multi_asset_results.csv`
- Tested top 3 BTC strategies on BTC + ETH + SOL (110,677 candles each, 2023–2026)

#### VolumetricBollinger — PASS (3/3 profitable)
| Asset | Return | Sharpe | Max DD | Win Rate | Trades | PF |
|---|---|---|---|---|---|---|
| BTC | +103.3% | 0.86 | -30.7% | 80.0% | 45 | 1.88 |
| ETH | +47.1% | 0.36 | -39.3% | 73.2% | 71 | 1.29 |
| SOL | +135.3% | 0.52 | -50.7% | 73.3% | 150 | 1.29 |

Strengths: High returns, 30+ trades on all assets, consistent win rate >73%.
Concerns: High drawdowns on ETH (-39%) and SOL (-51%). Risk-adjusted performance weaker outside BTC.
Source file: `src/data/rbi/03_15_2025/backtests_final/VolumetricBollinger_BTFinal.py`

#### RangeBoundPut — PASS (3/3 profitable)
| Asset | Return | Sharpe | Max DD | Win Rate | Trades | PF |
|---|---|---|---|---|---|---|
| BTC | +14.7% | 0.96 | -5.1% | 82.9% | 35 | 2.27 |
| ETH | +3.2% | 0.17 | -11.9% | 70.4% | 54 | 1.12 |
| SOL | +11.7% | 0.41 | -16.6% | 71.5% | 116 | 1.18 |

Strengths: Lowest drawdowns, highest win rates, best Sharpe on BTC (0.96), 30+ trades on all assets.
Concerns: Lower absolute returns. ETH performance marginal (+3.2%, Sharpe 0.17).
Source file: `src/data/rbi/03_13_2025/backtests_final/RangeBoundPut_BTFinal.py`

#### VolSurgeReversion — FAIL (0/3 profitable, eliminated)
- BTC: -9.3%, ETH: -13.1%, SOL: -49.2%
- The batch runner's +22.6% BTC result came from a different file version (`04_11`) that used synthetic VIX data
- The clean version (`04_09`, no synthetic data) loses money on all assets — no real edge
- Source files: `src/data/rbi/04_09_2025/` (clean, used here) vs `04_11_2025/` (synthetic VIX, unreliable)

### Sub-Period Validation (2026-02-26) — BOTH FAIL
- Script: `src/scripts/subperiod_validation.py`
- Results: `src/data/subperiod_results.csv`
- Split: P1 = 2023-01 to 2024-06 vs P2 = 2024-07 to 2026-02
- Criterion: profitable on 2+ assets in BOTH periods

#### VolumetricBollinger — FAIL (P2: only BTC positive)
| Period | BTC | ETH | SOL |
|---|---|---|---|
| P1 (2023-01 to 2024-06) | +93.2% | +70.2% | +243.7% |
| P2 (2024-07 to 2026-02) | +5.4% | -16.6% | -31.6% |

#### RangeBoundPut — FAIL (P2: only BTC positive)
| Period | BTC | ETH | SOL |
|---|---|---|---|
| P1 (2023-01 to 2024-06) | +12.9% | +9.4% | +24.2% |
| P2 (2024-07 to 2026-02) | +3.9% | -4.8% | -10.1% |

**Conclusion**: Both strategies were profitable only in the 2023-2024 bull regime. In the more recent 2024-2026 period, only BTC stayed marginally positive while ETH and SOL lost money. The full-period results were misleading — big P1 gains masked P2 losses. Neither strategy has a stable edge across market regimes.

### Surviving Strategies (0 of all tested)
**No strategy has survived any validation stage.** Full search history:

**Round 1 — Existing BTFinal strategies:**
1. 152 complete BTFinal files tested → 55 ran → 4 profitable on BTC
2. 2 passed multi-asset (VolumetricBollinger, RangeBoundPut)
3. **0 passed sub-period** — both only worked in 2023-2024 bull regime

**Round 2 — DeepSeek RBI-generated strategies:**
4. 15 ideas → 12 BTFinal files → massive code bugs → **0 viable after fixes**

**Round 3 — Filtered pool → DeepSeek specs → Claude code (v2 pipeline):**
5. 10 diverse strategies from idea pool + 5 hand-crafted structural strategies = 15 total
6. Research specs: `src/data/rbi/02_26_2026/research_v2/` (10 JSON files)
7. Backtests: `src/data/rbi/02_26_2026/backtests_v2/` (15 Python files)
8. Runner: `./venv/bin/python3 src/scripts/run_v2_backtests.py`
9. **ALL 15 LOST MONEY.** Best was GoldenCrossVolume at -32% (PF 0.58). Worst lost 96%.
10. Win rates consistently 15-40%, profit factors 0.10-0.58. No strategy came close to profitability.

**Key conclusion: Standard TA indicators (RSI, MACD, BB, Donchian, ADX, EMA, OBV, Vortex, Fisher, StochRSI, ATR) on 15-minute crypto candles do not provide an edge.** The market is too efficient at this timeframe for these signals.

### V2 Backtest Results (Training Data, BTC 2023-01 to 2025-06)
| # | Strategy | Type | Return | Sharpe | WR% | Trades | PF |
|---|---|---|---|---|---|---|---|
| 01 | BollingerVolumeMACD | Pool | -86.9% | -10.9 | 24% | 662 | 0.20 |
| 02 | GoldenCrossVolume | Pool | -31.7% | -0.94 | 9% | 107 | 0.58 |
| 03 | VolSqueezeBreakout | Pool | -71.1% | -5.01 | 36% | 385 | 0.49 |
| 04 | ADXVolumeBreakout | Pool | -92.4% | -9.69 | 29% | 822 | 0.52 |
| 05 | VolSqueezeDivergence | Pool | -6.8% | -1.89 | 21% | 19 | 0.12 |
| 06 | BollingerOBVDivergence | Pool | -92.0% | -12.8 | 32% | 593 | 0.23 |
| 07 | VortexElderTrend | Pool | -96.5% | -12.4 | 14% | 980 | 0.32 |
| 08 | FisherVortexDivergence | Pool | -19.7 | -19.7 | 16% | 948 | 0.12 |
| 09 | ATRVolumeBreakout | Pool | -23.9% | -1.11 | 20% | 25 | 0.45 |
| 10 | VolContractionMomentum | Pool | -92.3% | -12.9 | 30% | 783 | 0.19 |
| 11 | MomentumContinuation | Custom | -91.7% | -14.5 | 29% | 766 | 0.17 |
| 12 | RSIOversoldBounce | Custom | -67.9% | -14.0 | 20% | 265 | 0.11 |
| 13 | TrendADXTrail | Custom | -48.7% | -4.12 | 23% | 182 | 0.50 |
| 14 | VolBreakdownReversion | Custom | -31.3% | -2.94 | 27% | 48 | 0.38 |
| 15 | RangeBreakVolume | Custom | -94.3% | -6.92 | 37% | 945 | 0.46 |

## Key Development Commands

### Environment Setup
```bash
# Use the project venv
source venv/bin/activate
# OR reference directly:
./venv/bin/python3 <script>
./venv/bin/pip install <package>

# IMPORTANT: Update requirements.txt every time you add a new package
./venv/bin/pip freeze > requirements.txt
```

### Running the System
```bash
# Run main orchestrator (controls multiple agents — all currently disabled)
./venv/bin/python3 src/main.py

# Run individual agents standalone
./venv/bin/python3 src/agents/trading_agent.py
./venv/bin/python3 src/agents/rbi_agent.py
# ... any agent in src/agents/ can run independently
```

### Backtesting
```bash
# Batch-run existing backtests and rank by performance
./venv/bin/python3 src/scripts/batch_backtest_runner.py --runnable-only
./venv/bin/python3 src/scripts/batch_backtest_runner.py --results  # Show last results

# Use backtesting.py library (NOT their built-in indicators)
# Use pandas_ta or talib for technical indicators instead
```

### Swarm Backtesting
```bash
# Backtest the AI swarm over a historical period (real API calls, ~$2-5 per 72 candles)
./venv/bin/python3 src/scripts/swarm_backtester.py --start 2026-02-24 --end 2026-02-26

# Resume an interrupted run (Ctrl+C safe, auto-checkpoints every 10 candles)
./venv/bin/python3 src/scripts/swarm_backtester.py --start 2026-02-24 --end 2026-02-26 --resume

# Show saved results
./venv/bin/python3 src/scripts/swarm_backtester.py --results
```

Output: `src/data/swarm_backtester/` — trades CSV, per-candle vote log, summary JSON.
Skips already-completed candles automatically when extending date ranges.

### Data Fetching
```bash
# Update RBI backtest data (BTC/ETH/SOL 15m from 2023 to now)
./venv/bin/python3 src/scripts/data_fetcher.py --update-rbi

# Fetch all default pairs at all timeframes (15m, 1h, 4h)
./venv/bin/python3 src/scripts/data_fetcher.py --all --since 2023-01-01

# Fetch a specific pair and timeframe
./venv/bin/python3 src/scripts/data_fetcher.py --symbol BTC/USDT --timeframe 4h --since 2022-01-01

# List available Binance symbols
./venv/bin/python3 src/scripts/data_fetcher.py --list-symbols
```

## Architecture Overview

### Core Structure
```
src/
├── agents/              # 57 specialized AI agents (each <800 lines)
├── models/              # LLM provider abstraction (ModelFactory pattern, 8 providers)
├── strategies/          # User-defined trading strategies (base class + examples)
├── scripts/             # Utility scripts (batch_backtest_runner.py)
├── data/                # Agent outputs, backtest results, OHLCV data
│   ├── rbi/             # 4,481 strategy ideas, 1,277 backtest files, BTC CSV data
│   ├── backtest_results.csv  # Batch runner output with strategy rankings
│   └── [agent_name]/    # Per-agent output directories
├── config.py            # Global configuration (positions, risk limits, API settings)
├── main.py              # Main orchestrator (all agents disabled by default)
├── nice_funcs.py        # ~1,200 lines of shared Solana trading utilities
├── nice_funcs_hyperliquid.py  # HyperLiquid perps utilities
├── nice_funcs_aster.py  # Aster futures DEX utilities
├── exchange_manager.py  # Unified multi-exchange interface
└── ezbot.py             # Legacy trading controller
```

### Agent Ecosystem (57 agents)

**Trading Agents**: `trading_agent` (dual-mode: single/6-model swarm), `strategy_agent`, `risk_agent`, `copybot_agent`
**Market Analysis**: `sentiment_agent`, `whale_agent`, `funding_agent`, `liquidation_agent`, `chartanalysis_agent`, `volume_agent`
**Strategy Development**: `rbi_agent` (Research-Backtest-Implement), `rbi_agent_pp_multi` (18-thread production), `research_agent`, `websearch_agent`
**Content Creation**: `chat_agent`, `clips_agent`, `tweet_agent`, `video_agent`, `phone_agent`
**Specialized**: `sniper_agent`, `solana_agent`, `polymarket_agent`, `swarm_agent`, `housecoin_agent`

Each agent can run independently or as part of the main orchestrator loop.

### LLM Integration (Model Factory)

Located at `src/models/model_factory.py` — supports 8 providers:
1. Anthropic Claude (default)
2. OpenAI (GPT models)
3. DeepSeek (reasoning, cheap)
4. Groq (fast inference)
5. Google Gemini (multimodal)
6. xAI Grok
7. Ollama (local/free)
8. OpenRouter (200+ models)

```python
from src.models.model_factory import ModelFactory
model = ModelFactory.create_model('anthropic')  # or 'deepseek', 'groq', etc.
response = model.generate_response(system_prompt, user_content, temperature, max_tokens)
```

### Configuration Management

**Primary Config**: `src/config.py`
- Exchange: `EXCHANGE = 'solana'` (or 'hyperliquid')
- Position sizing: `usd_size = $25`, `max_usd_order_size = $3`
- Risk: `MAX_LOSS_USD = $25`, `MAX_GAIN_USD = $25`, `MINIMUM_BALANCE_USD = $50`
- AI: `AI_MODEL = "claude-3-haiku-20240307"`, temp 0.7, max 1024 tokens
- `USE_AI_CONFIRMATION = True` — consult AI before closing positions

**Environment Variables**: `.env` (see `.env_example` for full template)

### RBI Agent (Strategy Generation Pipeline)

The RBI agent is the core strategy research tool:
1. Takes input: YouTube URL, PDF link, or text description of a trading idea
2. **Research AI** — analyzes and extracts strategy logic, names the strategy
3. **Backtest AI** — generates backtesting.py code
4. **Package AI** — fixes indicator imports (removes backtesting.lib)
5. **Debug AI** — fixes syntax and runtime errors

Now configured for DeepSeek (switched from GPT-5 on 2026-02-26):
```python
# Current active config in src/agents/rbi_agent.py:
RESEARCH_CONFIG = {"type": "deepseek", "name": "deepseek-chat"}
BACKTEST_CONFIG = {"type": "deepseek", "name": "deepseek-reasoner"}
DEBUG_CONFIG = {"type": "deepseek", "name": "deepseek-chat"}
PACKAGE_CONFIG = {"type": "deepseek", "name": "deepseek-chat"}
```

### Batch Backtest Runner

`src/scripts/batch_backtest_runner.py` — runs existing backtest files in batch:
- Auto-fixes: data paths, markdown wrapping, backtesting.lib imports, broken emoji prints
- Parses backtesting.py stats output (Return, Sharpe, Drawdown, Win Rate, etc.)
- Ranks strategies by performance
- Saves results to `src/data/backtest_results.csv`

```bash
./venv/bin/python3 src/scripts/batch_backtest_runner.py --runnable-only  # Run complete backtests
./venv/bin/python3 src/scripts/batch_backtest_runner.py --limit 10       # Test first 10
./venv/bin/python3 src/scripts/batch_backtest_runner.py --results        # Show saved results
```

## Development Rules

### File Management
- **Keep files under 800 lines** — split into new files if longer
- **DO NOT move files without asking** — create new files instead
- **Use the project venv** — never create new virtual environments
- **Update requirements.txt** after adding any new package

### Backtesting Standards
- Use `backtesting.py` library (NOT their built-in indicators like backtesting.lib)
- Use `pandas_ta` or `talib` for technical indicators
- **Minimum 30+ trades** for statistical significance
- **Test on multiple assets** — a strategy should work on BTC, ETH, and SOL, not just one
- **Fresh data required** — use the data fetcher to keep CSVs up to date

### Overfitting Prevention Rules

**CRITICAL: Follow the correct validation approach for each scenario.**

#### Case 1: Running existing hard-coded strategies (BTFinal files)
- These strategies were AI-generated using 2023 data — that's their implicit "training" set
- **No split needed** — run on the full dataset (2023–2026)
- 2024–2026 is already genuine out-of-sample data for these strategies
- A strategy profitable on 2023 but failing on 2024–2026 = overfitted, discard it
- A strategy profitable across the full 3-year range = more robust signal

#### Case 2: Generating NEW strategies with the RBI agent
- The AI will see whatever data you give it to generate strategy logic
- **Split required BEFORE generation** — hold out the last 6–12 months of data
- Generate strategies using only the training portion (e.g., 2023-01 to 2025-06)
- Validate on the held-out portion (e.g., 2025-07 to 2026-02)
- NEVER let the RBI agent see the validation data during strategy creation
- A strategy that works on both periods has a real signal

#### Case 3: Optimizing parameters with `bt.optimize()`
- **Always split the data first** — this is where overfitting risk is highest
- Train split: optimize parameters (e.g., 70% of data)
- Test split: evaluate with the optimized parameters (remaining 30%)
- NEVER report optimized-on-full-data results as expected performance
- If optimization improves train but not test results = overfitted parameters, reject

#### Case 4: Manual strategy development / iteration
- If you keep tweaking a strategy after seeing its backtest results, you are fitting to the data
- **Keep a final holdout period you never look at** until you're done iterating
- Limit the number of iterations — more tweaks = more overfitting risk
- Document which data periods were used for development vs. final validation

#### General rules (all cases)
- **Minimum 30+ trades per period** — low trade count means results are noise
- **Test on multiple assets** — BTC + ETH + SOL, not just one
- **Beware survivorship bias** — don't only look at top performers, check the full distribution
- **Simpler is better** — a 3-parameter strategy that works is better than a 10-parameter one
- **Suspect >100% annual returns** — extreme results are almost always overfitting or bugs

### Code Style
- **No fake/synthetic data** — always use real data or fail the script
- **Minimal error handling** — user wants to see errors, not over-engineered try/except
- **No API key exposure** — never show keys from `.env` in output

### Agent Development Pattern
1. Inherit from base patterns in existing agents
2. Use `ModelFactory` for LLM access
3. Store outputs in `src/data/[agent_name]/`
4. Make agent independently executable (standalone script)
5. Add configuration to `config.py` if needed
6. Follow naming: `[purpose]_agent.py`

## Important Context

### Risk-First Philosophy
- Risk Agent runs first in main loop before any trading decisions
- Configurable circuit breakers (`MAX_LOSS_USD`, `MINIMUM_BALANCE_USD`)
- AI confirmation for position-closing decisions (configurable via `USE_AI_CONFIRMATION`)

### Data Sources
1. **BirdEye API** — Solana token data (price, volume, liquidity, OHLCV)
2. **Moon Dev API** — Custom signals (liquidations, funding rates, OI, copybot data)
3. **CoinGecko API** — 15,000+ token metadata, market caps, sentiment
4. **Helius RPC** — Solana blockchain interaction
5. **Free OHLCV sources** — yfinance, CCXT (Binance/others) for historical crypto data

### Autonomous Execution
- Main loop runs every 15 minutes by default (`SLEEP_BETWEEN_RUNS_MINUTES`)
- All agents disabled in `main.py` by default (safety-first)
- Keyboard interrupt for graceful shutdown
- All agents log to console with color-coded output (termcolor)

## Next Steps

_Update this section as steps are completed — delete done items, add new ones._

### Current: Validate Swarm Edge & Prepare for Live

**Status:** 20-day backtest complete (Feb 20 - Mar 11). Edge is real but thin (PF 1.28). Need more validation before going live.

**Next steps:**
1. **Extend backtest further** — run more weeks/months to confirm PF stays above 1.0
2. **Test on ETH/SOL** — currently BTC only, need multi-asset validation
3. **Analyze losing streaks** — 7 consecutive losses Feb 20-23, understand max streak risk
4. **Consider parameter tweaks** — SL/TP levels, position sizing, short signals
5. **If edge holds over 30+ days and multiple assets** → fund wallet and go live

### Live Trading Setup (ready but not started)

**How to run (observation mode — no real trades):**
```bash
PYTHONPATH=. ./venv/bin/python3 src/agents/trading_agent.py
```

**To go live:**
1. Create ETH wallet (MetaMask or `python -c "from eth_account import Account; a=Account.create(); print(a.key.hex())"`)
2. Deposit $50-100 USDC on Arbitrum, bridge to HyperLiquid
3. Add `HYPER_LIQUID_ETH_PRIVATE_KEY=0x...` to `.env`
4. Set `OBSERVATION_MODE = False` in `src/agents/trading_agent.py`
5. Run: `PYTHONPATH=. ./venv/bin/python3 src/agents/trading_agent.py`

**Current config (trading_agent.py):**
| Setting | Value |
|---|---|
| Exchange | HyperLiquid |
| AI Mode | Swarm (Claude Sonnet 4.6 + DeepSeek Chat) |
| Symbols | BTC |
| Timeframe | 1H (120 bars, 5 days) |
| Leverage | 3x |
| Max Position | 40% of balance |
| Stop Loss | -5% |
| Take Profit | +8% |
| Long Only | Yes |
| Cycle Interval | 60 minutes |
| Observation Mode | ON (no real trades) |

**What was changed (2026-02-26):**
- `trading_agent.py`: EXCHANGE=HYPERLIQUID, OBSERVATION_MODE, HL get_position wrapper, kill_switch for exits
- `swarm_agent.py`: Only Claude + DeepSeek enabled (2 models we have keys for)
- `risk_agent.py`: Soft warning for missing OPENAI_KEY (was hard crash)
- `ohlcv_collector.py`: Lazy imports to avoid Birdeye crash when using HL
- Installed `hyperliquid-python-sdk`

### Swarm Backtester Results

**Extended run: BTC 1H, Feb 20 - Mar 11, 2026 (480 candles, 41 trades)**

| Metric | Value |
|---|---|
| Return | **+5.95%** |
| Final Equity | $10,594.80 |
| Profit Factor | **1.28** |
| Max Drawdown | -4.92% |
| Trades | 41 (14W / 27L) |
| Win Rate | 34.1% |
| Gross Profit | $2,728.07 |
| Gross Loss | $2,133.27 |

Key observations:
- **9 TP hits at +8%** drove all profit (~$2,893 total), only **1 SL hit** in 41 trades
- Avg win: +$195, avg loss: -$79 → **2.5:1 win:loss ratio** compensates for 34% win rate
- Swarm correctly stayed flat during Feb 22-24 selloff ($68k→$63k) and Mar 5-8 crash ($73k→$67k)
- Back-to-back TP hits on Mar 4 during BTC rally ($68k→$73k)
- PF dropped from 2.16 (4-day sample) to 1.28 (20-day) — edge is real but thin
- Pattern: catch rallies with TP, cut losers fast via signal reversal before SL

**Earlier run: BTC 1H, Feb 24-26 (72 candles):** +4.47%, PF 2.69, DD -2.18%, 7 trades

### Swarm Dashboard

Real-time Dash + Plotly dashboard for monitoring backtests:
```bash
PYTHONPATH=. ./venv/bin/python3 src/scripts/swarm_dashboard.py
# Open http://localhost:8050
```

Features:
- Launch/stop backtests from UI (sidebar controls)
- Auto-refreshes every 3 seconds (reads `live_feed.jsonl`)
- Candlestick chart with trade entry/exit markers
- Equity curve, AI vote bars (color-coded per model)
- Live agent terminal showing votes as they arrive
- Load and compare completed runs from dropdown

## Project Philosophy

This is an **experimental, educational project** demonstrating AI agent patterns through algorithmic trading:
- No guarantees of profitability (substantial risk of loss)
- Research and backtest FIRST, fund LATER
- Open source and free for learning
- The goal is to find and validate trading edges before risking real money
