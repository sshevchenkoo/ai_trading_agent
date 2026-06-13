# System Architecture

## Data Flow Overview

```
┌─────────────────────────────────────────────────────────┐
│                      DATA LAYER                         │
│                                                         │
│  [pump.fun WS]  ──┐  WebSocket, passive, always-on     │
│  [DexScreener]  ──┼──► [asyncio.Queue]  (new tokens)   │
│                   └──► collected every 5 min           │
└───────────────────────────────┬─────────────────────────┘
                                │
                     every 5 minutes (Poller)
                                │
                    ┌───────────▼───────────┐
                    │  DexScreener enrich   │
                    │  (real mcap/liquidity)│
                    └───────────┬───────────┘
                                │
                    ┌───────────▼───────────┐
                    │   mcap > $5,000?      │
                    │   NO → discard        │
                    └───────────┬───────────┘
                                │ YES
                                ▼
┌─────────────────────────────────────────────────────────┐
│               ANALYSIS LAYER (3 stages)                 │
│                                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │ Stage 1: Python pre-filter  (zero Claude calls)  │  │
│  │  DexScreener ──┐  parallel                       │  │
│  │  Birdeye    ──┘                                  │  │
│  │  Hard reject: no volume / security flags         │  │
│  │  ~90% of tokens stopped here (0 Claude calls)    │  │
│  └──────────────────────────┬───────────────────────┘  │
│                             │ ~10% passed               │
│  ┌──────────────────────────▼───────────────────────┐  │
│  │ Stage 2: Specialist agents (Haiku, parallel)     │  │
│  │  [Twitter Haiku] ──┐                             │  │
│  │  [GMGN Haiku]   ──┘  asyncio.gather()           │  │
│  └──────────────────────────┬───────────────────────┘  │
│                             │                           │
│  ┌──────────────────────────▼───────────────────────┐  │
│  │ Stage 3: Master agent (Opus)                     │  │
│  │  Receives: DexScreener + Birdeye + Twitter + GMGN│  │
│  │  Returns:  score 1–10 + verdict                  │  │
│  └──────────────────────────┬───────────────────────┘  │
│                             │                           │
│                    score ≥ 7.0?                         │
│                   NO → discard   YES → BUY_SIGNAL       │
└─────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────┐
│                   TRADING LAYER (Phase 3)               │
│                                                         │
│           [Trade Executor] ──► [Solana Wallet]          │
│                 │               (Jupiter swap)          │
│                 │                                       │
│          [Position Manager]                             │
│                 │                                       │
│      ┌──────────┼──────────┐                            │
│      ▼          ▼          ▼                            │
│  [+100%]    [+300%]    [+900%]    [-50%]                │
│  sell 50%  sell 25%  sell rest  stop-loss               │
└─────────────────────────────────────────────────────────┘
```

---

## Components and Roles

### Poller
Every 5 minutes: drains the pump.fun queue + fetches DexScreener new pairs. Deduplicates tokens, enriches with real metrics (mcap, liquidity), discards mcap < $5k.

### Python pre-filter (Stage 1)
Deterministic checks — no AI. Queries DexScreener and Birdeye in parallel, applies hard rules. ~90% of tokens are rejected here with zero Claude API calls.

### Specialist agents (Stage 2)
Two Haiku agents run in parallel:
- **Twitter agent** — sentiment, KOL mentions, organic narrative detection
- **GMGN agent** — smart money wallets, dev behaviour, rug risk

### Master agent (Stage 3)
Opus receives all 4 reports (DexScreener + Birdeye from pre-filter + Twitter + GMGN from specialists) and makes the final verdict.

### Trade Executor (Phase 3)
Calls the Jupiter API to get a quote and execute the swap. Signs the transaction with the wallet keypair.

### Position Manager (Phase 3)
Stores all open positions. Every 10 seconds fetches the current price and checks sell triggers.

---

## Real-time Timeline

```
t=0ms       pump.fun WS → new token created → pushed to queue
t=0ms       ...accumulates over 5 minutes...
t=300000ms  Poller wakes up
t=300010ms  drain queue + DexScreener new pairs
t=300050ms  enrich all tokens (parallel)
t=300200ms  mcap < $5k → discard most
t=300210ms  Stage 1: DexScreener + Birdeye parallel (~90% reject)
t=300600ms  Stage 2: Twitter + GMGN Haiku parallel
t=301200ms  Stage 3: Opus master verdict
t=301201ms  score ≥ 7.0 → BUY_SIGNAL
t=301300ms  (Phase 3) Trade Executor → Jupiter swap
t=302000ms  transaction confirmed, Position Manager records position
```

---

## Data Storage

```
SQLite:
├── tokens     — all seen tokens and their metrics
├── signals    — all signals from sources
├── positions  — open and closed positions
├── trades     — full trade history (buy / sell)
```

---

## Links

- [[Components/Data Sources]] — details on each data source
- [[Components/AI Analyzer]] — multi-agent analysis
- [[Components/Trade Executor]] — Jupiter integration
- [[Components/Position Manager]] — exit logic
- [[Strategy/Filters and Security]] — Python pre-filter rules
