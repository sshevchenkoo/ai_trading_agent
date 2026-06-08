# Фільтри і безпека

Двостадійна система відсіювання. ~90%+ токенів відхиляються до Claude.

---

## Стадія 0: mcap фільтр (Poller)

```python
MIN_MARKET_CAP_USD = 5_000  # токени з mcap < $5k → discard
```

Після DexScreener enrich — якщо ринкова капіталізація менше $5k, токен відкидається одразу.

---

## Стадія 1: Python pre-filter (без Claude)

Паралельний запит DexScreener + Birdeye, детерміновані правила. **0 Claude API викликів.**

### DexScreener перевірки

```python
MIN_BUYS_1H = 5           # мінімум 5 buy транзакцій за останню годину
MIN_VOLUME_1H_USD = 500   # мінімум $500 обʼєму за годину

if not pairs:             → reject "no_dex_pairs"
if buys_1h < 5:           → reject "buys_1h=N < 5"
if volume_1h_usd < 500:   → reject "volume_1h=$N < $500"
```

### Birdeye security перевірки

```python
if is_mintable:                → reject "mint_authority_not_revoked"
if is_freezable:               → reject "freeze_authority_exists"
if creator_pct > 20:           → reject "creator_Xpct"
if top10_holder_pct > 70:      → reject "top10_Xpct"
if lp_locked_pct is not None
   and lp_locked_pct < 10:     → reject "lp_locked_Xpct"
```

### Результат pre-filter

```
┌──────────────────────────────────────────────────┐
│  ~90% токенів відхиляються на цьому рівні        │
│  0 Claude API викликів витрачено                 │
│  Дані DexScreener + Birdeye зберігаються →       │
│  передаються в Stage 3 (Master agent)            │
└──────────────────────────────────────────────────┘
```

---

## Стадія 2: Specialist agents (Haiku, паралельно)

Для токенів що пройшли pre-filter (~10%):

- **Twitter агент** — шукає `$SYMBOL` і тему назви токена; оцінює органічність хайпу
- **GMGN агент** — smart money holders, поведінка dev'а, rug ratio

Якщо агент повертає помилку — Master все одно отримує 3 звіти і приймає рішення.

---

## Стадія 3: Master agent (Opus) — фінальне рішення

Hard reject правила всередині Master:
- GMGN `rug_risk = "high"` або `dev_behavior = "dumping"` → score 1-3
- Twitter `organic_score < 3` і `bot_likelihood = "high"` → знижує score
- Відсутність даних → знижує confidence, не блокує

---

## Підсумковий пайплайн

```
1. mcap > $5,000 (Poller)              → відхиляє ~70% нових токенів
2. Python pre-filter: DexScreener      → відхиляє ще ~15% (нема обʼєму)
3. Python pre-filter: Birdeye security → відхиляє ще ~10% (security flags)
   ─────────────────────────────────────────────────────────────────────
   Залишається ~5% → йдуть на AI аналіз (Haiku x2 + Opus x1)
```

**Claude API витрати:** тільки для ~5% токенів. 3 виклики на токен (~$0.02).

---

## Посилання

- [[Components/AI Analyzer]] — мультиагентний аналіз
- [[Strategy/Trading Strategy]] — умови входу в угоду
- [[Components/Data Sources]] — звідки беремо дані
