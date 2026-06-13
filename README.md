# Solana AI Trading Agent

> Automated meme-token trading bot on Solana — powered by a hybrid multi-agent Claude AI pipeline.

![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python)
![Claude](https://img.shields.io/badge/Claude-Opus%20%2B%20Haiku-purple?logo=anthropic)
![Solana](https://img.shields.io/badge/Solana-mainnet-9945FF?logo=solana)
![License](https://img.shields.io/badge/license-MIT-green)
![Status](https://img.shields.io/badge/status-Phase%203%20complete-brightgreen)

---

## Overview

The agent monitors **pump.fun** (via WebSocket) and **DexScreener** every 5 minutes, collects new Solana tokens from three parallel sources, and passes candidates through a cost-optimised three-stage pipeline:

| Stage | Who does it | Rejects |
|-------|-------------|---------|
| **0 — mcap gate** | Python | tokens < $5k market cap |
| **1 — Python pre-filter** | Python + DexScreener/Birdeye API | ~90% of remaining tokens, **0 Claude calls** |
| **2 — Specialist agents** | 2× Claude Haiku (parallel) | Twitter sentiment · GMGN smart money |
| **3 — Master agent** | Claude Opus | final verdict, score 1–10 |

Only ~5% of all seen tokens reach Claude. Cost is roughly **$0.02 per token analysed** vs $5+ in a single-agent approach.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  pump.fun WebSocket (always-on, passive)            │
│  → pushes new tokens into asyncio.Queue             │
└──────────────────────┬──────────────────────────────┘
                       │
              every 5 minutes
                       ▼
┌─────────────────────────────────────────────────────┐
│                  POLLER CYCLE                       │
│                                                     │
│  Drain pump.fun queue                               │
│  + DexScreener new pairs     ─┐ parallel            │
│  + Birdeye top-5m gainers    ─┘                     │
│  → DexScreener enrich (real mcap / liquidity)       │
│  → mcap < $5,000 → discard                          │
│                                                     │
│  STAGE 1 — Python pre-filter (zero Claude calls):  │
│  ├── DexScreener: buys_1h < 5      → discard       │
│  ├── DexScreener: volume_1h < $500 → discard       │
│  ├── Birdeye: mint / freeze auth   → discard       │
│  ├── Birdeye: creator wallet > 20% → discard       │
│  └── Birdeye: top-10 holders > 70% → discard       │
│  (~90% stopped here, $0 spent on AI)               │
│                                                     │
│  STAGE 2 — Specialist agents (Haiku, parallel):    │
│  ├── Twitter agent → sentiment, KOLs, narrative    │
│  └── GMGN agent   → smart money, dev behaviour     │
│                                                     │
│  STAGE 3 — Master agent (Opus):                    │
│  Receives: DexScreener + Birdeye + Twitter + GMGN  │
│  Returns:  score 1–10 + full verdict               │
│                                                     │
│           score ≥ 7.0 → BUY_SIGNAL                 │
└─────────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│              TRADING LAYER                          │
│                                                     │
│  TradeExecutor → Jupiter v6 swap                   │
│  PositionMonitor (10-second price loop)            │
│                                                     │
│  Exit strategy:                                     │
│  x2  → sell 50%   (recover capital)                │
│  x4  → sell 25%   (lock more profit)               │
│  x10 → sell rest  (full exit)                      │
│  -50% → stop-loss (cut loss immediately)           │
└─────────────────────────────────────────────────────┘
```

**Example BUY signal in logs:**
```
BUY_SIGNAL  symbol=BARRONDOG  score=8.7  confidence=high
            risk=medium  suggested_sol=0.2  timeframe=hours
            reasoning="Pre-existing Twitter hype around 'barron trump dog',
                       12 smart money wallets holding, clean security,
                       buy/sell ratio 4.2x in last hour"
```

---

## Quick Start

### Requirements

- Python 3.11+
- [Poetry](https://python-poetry.org/docs/#installation)

### Installation

```bash
git clone https://github.com/sshevchenkoo/ai_trading_agent.git
cd ai_trading_agent
poetry install
cp .env.example .env
```

### Configuration

Edit `.env` and fill in the required keys:

```bash
# Required for Phase 1 — token monitoring
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com

# Required for Phase 2 — AI analysis
ANTHROPIC_API_KEY=sk-ant-...

# Recommended — security & on-chain data (free tier available)
BIRDEYE_API_KEY=...

# Optional — Twitter KOL signals
TWITTER_BEARER_TOKEN=...

# Required for Phase 3 — live trading
WALLET_PRIVATE_KEY=your_base58_private_key_here
```

> **Security:** Never commit `.env` or `wallet.json` — both are listed in `.gitignore`.

### Run

```bash
# Paper trading mode (default — no real trades executed)
poetry run python main.py

# Live trading (only after validating on paper trading!)
PAPER_TRADING=false poetry run python main.py
```

---

## Strategy Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `AI_SCORE_THRESHOLD` | `7.0` | Minimum Claude score to trigger a buy |
| `MAX_POSITION_SIZE_SOL` | `0.2` | Maximum SOL per position |
| `MAX_OPEN_POSITIONS` | `5` | Maximum concurrent open positions |
| `STOP_LOSS_PCT` | `50` | Stop-loss threshold in % |
| `PAPER_TRADING` | `true` | Simulate trades without spending real SOL |

---

## Project Structure

```
├── main.py                  # Entry point, async orchestrator
├── config.py                # All settings loaded from .env
│
├── sources/
│   ├── signal.py            # TokenSignal, TweetInfo, MarketContext models
│   ├── pumpfun.py           # WebSocket listener — pushes tokens to queue
│   ├── poller.py            # Scheduler — runs pipeline every 5 min
│   ├── dexscreener.py       # New pairs + metric enrichment
│   ├── birdeye.py           # Security checks, holder data, top gainers
│   ├── twitter.py           # Token mention search
│   ├── price.py             # Current price via DexScreener
│   └── market_data.py       # SOL/BTC price, market trend (CoinGecko)
│
├── analysis/
│   ├── filters.py           # (legacy) Rule-based filters
│   ├── rugcheck.py          # (legacy) rugcheck.xyz integration
│   └── ai_analyzer.py       # Multi-agent pipeline: pre-filter + Haiku×2 + Opus
│
├── trading/
│   ├── wallet.py            # Solana keypair loader
│   ├── jupiter.py           # Jupiter v6 quote + swap
│   └── executor.py          # TradeExecutor — paper and live modes
│
├── positions/
│   ├── manager.py           # PositionManager — open/partial/closed tracking
│   └── monitor.py           # Price monitoring loop (every 10 sec)
│
├── db/
│   ├── models.py            # Token, Trade, Position SQLModel tables
│   └── database.py          # SQLite connection
│
└── utils/
    └── logger.py            # structlog structured logging
```

---

## External APIs

| Service | Purpose | Cost |
|---------|---------|------|
| [Anthropic](https://console.anthropic.com) | Claude AI (Haiku specialists + Opus master) | ~$0.50–2/day |
| [Birdeye](https://birdeye.so) | Security checks, holder data, top gainers | Free tier |
| CoinGecko | SOL/BTC price, market context | Free |
| DexScreener | Liquidity, volume, new pairs | Free |
| [GMGN](https://gmgn.ai) | Smart money, dev behaviour | Free (public API) |
| pump.fun WebSocket | Real-time new token stream | Free |
| [Helius RPC](https://helius.dev) | Reliable Solana RPC (Phase 3) | $49+/mo |
| [Twitter/X API](https://developer.twitter.com) | KOL monitoring | $100/mo |

**Minimum budget to start (Phase 1–2):** ~$5/mo (Anthropic API only)

---

## Roadmap

- [x] **Phase 1** — pump.fun WebSocket + DexScreener + SQLite + structlog
- [x] **Phase 2** — Multi-agent Claude AI + Birdeye + GMGN + Twitter + Python pre-filter
- [x] **Phase 3** — Jupiter swap + Solana wallet + Position Manager + auto-sell triggers
- [ ] **Phase 4** — Trailing stop, Telegram alerts, prompt optimisation
- [ ] **Phase 5** — Whale wallet tracking, scaling

---

## Disclaimer

This is an experimental project. Meme-token trading carries extreme risk.
Always start with `PAPER_TRADING=true` and never trade money you cannot afford to lose.
