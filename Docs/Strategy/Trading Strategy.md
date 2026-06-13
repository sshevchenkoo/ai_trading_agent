# Trading Strategy

---

## Two signal types

### Type 1: New token on pump.fun
- Token just launched (0–30 minutes ago)
- Catching it in the early pump stage
- High risk / high potential
- Key criterion: narrative quality + initial growth speed

### Type 2: Existing token with new hype
- Token has been around for hours or days
- A KOL just started mentioning it on Twitter
- Lower multiple potential, but more predictable
- Key criterion: audience size + volume before the mention

---

## Entry criteria

```
Required (Rule Filters):
  ✓ Liquidity ≥ 50 SOL
  ✓ Holders ≥ 100
  ✓ Top-10 holders < 50% of supply
  ✓ Dev wallet has not sold
  ✓ No honeypot indicators (mint authority revoked)

Desired:
  ✓ Buy/Sell ratio over last hour ≥ 3:1
  ✓ Tweets from real accounts
  ✓ Unique narrative (not a clone of a popular token)
  ✓ Price up ≥ 20% in last 30 minutes

AI Score (Claude):
  ✓ final_score ≥ 7.0 out of 10
```

---

## Position sizing

```
Base capital: 3–5 SOL (total in bot)

Size by score:
  score 6.0–7.0 → 0.05 SOL (1% of capital)
  score 7.0–8.0 → 0.10 SOL (2% of capital)
  score 8.0–8.5 → 0.20 SOL (4% of capital)
  score 8.5+    → 0.30 SOL (6% of capital)

Maximum simultaneous open positions: 5
Maximum total exposure: 50% of deposit
```

---

## Exit strategy (partial sells)

```
BUY: X tokens for P SOL

At x2 price:
  → Sell 50% of tokens
  → Receive ~P SOL (capital recovered)
  → Remaining 50% are "free"

At x4 price:
  → Sell 50% of remainder (25% from original)
  → Lock additional profit
  → Remaining 25% rides further

At x10 price:
  → Sell everything remaining
  → If x10 not reached and price falls → Trailing Stop
```

### Why partial sells instead of all at once?

| Strategy | Risk | Return |
|----------|------|--------|
| Sell everything at x2 | low | capped |
| Wait for x10, sell all | high | high, but rare |
| **Partial sells** | **medium** | **consistently high** |

Meme tokens often do x2–x5 then retrace 80%. Partial sells capture both the short-term gain and rare x10 runs.

---

## Stop-loss

```
Fixed: -50% from entry price → sell everything immediately

Why -50%:
  - Meme tokens are volatile, -20% is a normal pullback
  - -50% is a clear signal the thesis failed
  - Losing 0.5x on one trade is covered by one x4 on another

After first x2:
  Trailing Stop: -30% from peak
  → If price falls 30% from its high → sell the remainder
```

---

## Daily limits (risk management)

```
Daily stop:
  If 1 SOL lost in a day → halt trading until next day

Weekly stop:
  If balance falls 30% below starting balance → pause for analysis

Maximum AI spending:
  ≤ $5/day on Claude API calls
```

---

## Best trading hours

Based on historical pump.fun data:

```
UTC 13:00–21:00 (New York 09:00–17:00) — most active period
UTC 00:00–04:00 (Asia session) — second most active

Avoid:
  UTC 04:00–10:00 — low volume, many fake pumps
  Weekends — lower volume, more scams
```

---

## Links

- [[Strategy/Filters and Security]] — entry filter details
- [[Components/Position Manager]] — exit implementation
- [[Components/AI Analyzer]] — how score is calculated
