# Filters and Security

Two-stage filtering system. ~90%+ of tokens are rejected before reaching Claude.

---

## Stage 0: mcap gate (Poller)

```python
MIN_MARKET_CAP_USD = 5_000  # tokens with mcap < $5k → discard
```

After DexScreener enrichment — if market cap is below $5k, the token is immediately discarded.

---

## Stage 1: Python pre-filter (zero Claude calls)

Parallel DexScreener + Birdeye requests, deterministic rules. **Zero Claude API calls.**

### DexScreener checks

```python
MIN_BUYS_1H = 5           # minimum 5 buy transactions in the last hour
MIN_VOLUME_1H_USD = 500   # minimum $500 volume in the last hour

if not pairs:             → reject "no_dex_pairs"
if buys_1h < 5:           → reject "buys_1h=N < 5"
if volume_1h_usd < 500:   → reject "volume_1h=$N < $500"
```

### Birdeye security checks

```python
if is_mintable:                → reject "mint_authority_not_revoked"
if is_freezable:               → reject "freeze_authority_exists"
if creator_pct > 20:           → reject "creator_Xpct"
if top10_holder_pct > 70:      → reject "top10_Xpct"
if lp_locked_pct is not None
   and lp_locked_pct < 10:     → reject "lp_locked_Xpct"
```

### Pre-filter result

```
┌──────────────────────────────────────────────────┐
│  ~90% of tokens rejected at this stage           │
│  Zero Claude API calls spent                     │
│  DexScreener + Birdeye data is preserved →       │
│  passed to Stage 3 (Master agent)                │
└──────────────────────────────────────────────────┘
```

---

## Stage 2: Specialist agents (Haiku, parallel)

For tokens that passed the pre-filter (~10%):

- **Twitter agent** — searches `$SYMBOL` and the token's name theme; scores organic vs bot hype
- **GMGN agent** — smart money holders, dev behaviour, rug ratio

If an agent returns an error — Master still receives 3 reports and makes its decision.

---

## Stage 3: Master agent (Opus) — final decision

Hard reject rules inside Master:
- GMGN `rug_risk = "high"` or `dev_behavior = "dumping"` → score 1–3
- Twitter `organic_score < 3` and `bot_likelihood = "high"` → score reduction
- Missing data → reduces confidence, does not block

---

## Full pipeline summary

```
1. mcap > $5,000 (Poller)               → rejects ~70% of new tokens
2. Python pre-filter: DexScreener        → rejects ~15% more (no volume)
3. Python pre-filter: Birdeye security   → rejects ~10% more (security flags)
   ─────────────────────────────────────────────────────────────────────────
   ~5% remaining → go to AI analysis (Haiku ×2 + Opus ×1)
```

**Claude API cost:** only for ~5% of tokens. 3 calls per token (~$0.02).

---

## Links

- [[Components/AI Analyzer]] — multi-agent analysis
- [[Strategy/Trading Strategy]] — trade entry conditions
- [[Components/Data Sources]] — where data comes from
