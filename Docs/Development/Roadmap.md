# Roadmap — Development Phases

---

## Phase 1: Foundation ✅ COMPLETE

**Goal:** observe tokens and log signals, no real trades.

### Tasks
- [x] Set up project (pyproject.toml, .env, folder structure)
- [x] pump.fun WebSocket — listen for new tokens
- [x] DexScreener API — fetch token metrics
- [x] Basic Rule Filters (liquidity, holders, age)
- [x] Database (SQLite) — store all seen tokens
- [x] Structured logging (structlog)
- [x] Rugcheck API integration

---

## Phase 2: AI Analysis ✅ COMPLETE

**Goal:** multi-agent analysis of every token via Claude.

### Tasks
- [x] Birdeye integration — security, holders, on-chain data
- [x] GMGN integration — smart money, dev behaviour
- [x] Twitter integration — KOL mentions, sentiment, narrative hype
- [x] CoinGecko — SOL/BTC price, market context
- [x] Python pre-filter (DexScreener + Birdeye hard rules, zero Claude calls)
- [x] Twitter specialist (Haiku) — social signal analysis
- [x] GMGN specialist (Haiku) — smart money analysis
- [x] Master agent (Opus) — final verdict based on all reports
- [x] Hybrid architecture: ~90% of tokens rejected without Claude calls

**Current cost:** ~$0.50–2/day (vs ~$10–20 in the first version)

---

## Phase 3: Trade Execution ✅ COMPLETE

**Goal:** real trades with a small deposit.

### Tasks
- [x] `trading/wallet.py` — keypair loading
- [x] Jupiter API integration — quotes and swap execution
- [x] `trading/executor.py` — buy and sell functions
- [x] `positions/manager.py` — open position tracking
- [x] Price monitoring loop (every 10 sec)
- [x] Auto-sells: x2 → 50%, x4 → 25%, x10 → 100%, -50% stop-loss
- [ ] Test on devnet with test tokens

**Starting deposit: 0.5 SOL** (for testing)

---

## Phase 4: Optimisation

**Goal:** improve accuracy and profitability using real trade data.

### Tasks
- [ ] Analyse first 2 weeks of trading
- [ ] Tune pre-filter thresholds based on data
- [ ] Improve prompts (based on what the bot called right / wrong)
- [ ] Trailing Stop implementation
- [ ] Anti-sandwich protection (Jito bundles)
- [ ] Telegram alerts: bought, sold, stop-loss

### Telegram alerts (example)
```
🟢 BOUGHT $BONK2
   Amount: 0.2 SOL | Price: $0.0000234
   AI Score: 8.4/10 | Narrative: "trump dog meme"

🔴 SOLD $BONK2 (50% → x2 target)
   Received: ~0.2 SOL | P&L: +0.2 SOL (+100%)
```

---

## Phase 5: Scaling

**Goal:** increase deposit and optimise for profitability.

### Tasks
- [ ] Increase deposit to 2–5 SOL (only if Phase 4 is profitable)
- [ ] Whale wallet tracking (Birdeye smart money)
- [ ] Expand KOL monitoring list
- [ ] Backtesting on 3+ months of historical data
- [ ] Automatic position size rebalancing

---

## Success Metrics

| Metric | Poor | Good | Excellent |
|--------|------|------|-----------|
| Win rate | < 30% | 35–50% | > 50% |
| Avg winner | < x1.5 | x2–x3 | > x4 |
| Max drawdown | > 50% | 20–40% | < 20% |
| ROI / month | < 0% | 20–50% | > 100% |

**Core rule:** if the system is unprofitable after 2 weeks of paper trading — do not move to real money; analyse and fix the filters.

---

## Links

- [[🏠 Home]] — overall project status
- [[Development/Tech Stack]] — what we use
- [[Strategy/Trading Strategy]] — parameters to tune
