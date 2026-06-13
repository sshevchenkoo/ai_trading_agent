# AI Analyzer — Multi-Agent Analysis via Claude

Called for tokens that passed the Python pre-filter. Uses a 3-stage architecture:

---

## Architecture: 3 stages

```
Token (passed mcap > $5k)
       │
       ▼
┌─────────────────────────────────────────────────────┐
│  STAGE 1: Python pre-filter  (no Claude, ~90% reject)│
│  DexScreener + Birdeye parallel                     │
│  Hard reject: no volume / mint authority /          │
│  freeze authority / creator >20% / top10 >70%       │
└──────────────────────┬──────────────────────────────┘
                       │ passed (~10%)
                       ▼
┌─────────────────────────────────────────────────────┐
│  STAGE 2: 2 specialists (Haiku, parallel)           │
│  [Twitter agent] → JSON report                      │
│  [GMGN agent]    → JSON report                      │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│  STAGE 3: Master agent (Opus)                       │
│  Receives: DexScreener data + Birdeye data +        │
│            Twitter report + GMGN report             │
│  Returns:  verdict JSON with score 1–10             │
└─────────────────────────────────────────────────────┘
```

---

## Stage 1 — Python pre-filter (no Claude)

Deterministic rules, zero AI calls:

```python
# DexScreener checks
if not pairs:             → reject "no_dex_pairs"
if buys_1h < 5:           → reject "no_buying_activity"
if volume_1h < $500:      → reject "low_volume"

# Birdeye security checks
if is_mintable:           → reject "mint_authority_not_revoked"
if is_freezable:          → reject "freeze_authority_exists"
if creator_pct > 20:      → reject "creator_X_pct"
if top10_holder_pct > 70: → reject "top10_X_pct"
if lp_locked_pct < 10:    → reject "lp_not_locked"
```

**Result:** ~90% of tokens rejected. Zero Claude API calls spent.

---

## Stage 2 — Specialists (Haiku)

Two agents launched in parallel via `asyncio.gather()`.

### Twitter agent

Searches by ticker (`$SYMBOL`) and by topic (if the name resembles a meme/celebrity):

```
Returns JSON:
{
  "sentiment": "bullish|bearish|neutral|mixed",
  "organic_score": 1-10,
  "kol_count": <accounts with >10k followers>,
  "bot_likelihood": "low|medium|high",
  "narrative": "<real topic driving interest>",
  "pre_existing_hype": <true if topic existed BEFORE the token>,
  "top_accounts": ["@handle (Xk): quote"],
  "summary": "2-3 sentences"
}
```

### GMGN agent

Checks smart money wallets, dev behaviour, rug risk:

```
Returns JSON:
{
  "smart_money_count": <count or null>,
  "dev_behavior": "healthy|suspicious|dumping|unknown",
  "rat_traders": "low|medium|high|unknown",
  "rug_risk": "low|medium|high|unknown",
  "red_flags": ["<flag>"],
  "summary": "2-3 sentences"
}
```

---

## Stage 3 — Master agent (Opus)

Receives all 4 reports and makes the final decision:

```python
MASTER_SYSTEM = """
You are the final arbiter. The token has already passed DexScreener + Birdeye filters.
Your task: evaluate potential based on 4 data sources.

Score 8-10: strong volume + organic Twitter narrative + smart money
Score 7:    3 of 4 signals positive
Score 5-6:  mixed signals, skip
Score 1-4:  GMGN shows rug risk / dev dumps / Twitter = bots
"""
```

Verdict JSON:
```json
{
  "score": 8,
  "confidence": "high",
  "reasoning": "Strong organic community around pre-existing meme...",
  "risk_level": "medium",
  "suggested_position_sol": 0.2,
  "red_flags": [],
  "narrative_strength": 9,
  "estimated_timeframe": "hours"
}
```

---

## Cost per token

| Scenario | Claude calls | Approximate cost |
|----------|-------------|-----------------|
| Rejected at pre-filter (~90%) | **0** | $0.00 |
| Passed (2× Haiku + 1× Opus) | **3** | ~$0.02 |

**At 100 tokens per cycle:** ~10 pass pre-filter → ~$0.20 per cycle vs ~$5.00 in the old architecture.

---

## Models

| Agent | Model | Reason |
|-------|-------|--------|
| Twitter specialist | `claude-haiku-4-5-20251001` | Fast and cheap for single-source analysis |
| GMGN specialist | `claude-haiku-4-5-20251001` | Fast and cheap for single-source analysis |
| Master | `claude-opus-4-8` | Best model for final verdict |

---

## Links

- [[Components/Data Sources]] — data sources
- [[Components/Trade Executor]] — what happens after score ≥ 7
- [[Strategy/Filters and Security]] — Python pre-filter details
