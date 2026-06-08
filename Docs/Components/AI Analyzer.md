# AI Analyzer — Мультиагентний аналіз через Claude

Викликається для токенів що пройшли Python pre-filter. Використовує 3-стадійну архітектуру:

---

## Архітектура: 3 стадії

```
Токен (пройшов mcap > $5k)
       │
       ▼
┌─────────────────────────────────────────────────────┐
│  СТАДІЯ 1: Python pre-filter  (без Claude, ~90% відхиляє)  │
│  DexScreener + Birdeye паралельно                   │
│  Hard reject якщо: нема обʼєму / mint authority /   │
│  freeze authority / creator >20% / top10 >70%       │
└──────────────────────┬──────────────────────────────┘
                       │ пройшов (~10%)
                       ▼
┌─────────────────────────────────────────────────────┐
│  СТАДІЯ 2: 2 спеціалісти (Haiku, паралельно)        │
│  [Twitter agent] → JSON звіт                        │
│  [GMGN agent]    → JSON звіт                        │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│  СТАДІЯ 3: Master agent (Opus)                      │
│  Отримує: DexScreener дані + Birdeye дані +         │
│           Twitter звіт + GMGN звіт                  │
│  Повертає: вердикт JSON з score 1-10                │
└─────────────────────────────────────────────────────┘
```

---

## Стадія 1 — Python pre-filter (без Claude)

Детерміновані правила, жодного AI виклику:

```python
# DexScreener перевірки
if not pairs:             → reject "no_dex_pairs"
if buys_1h < 5:           → reject "no_buying_activity"
if volume_1h < $500:      → reject "low_volume"

# Birdeye security перевірки
if is_mintable:           → reject "mint_authority_not_revoked"
if is_freezable:          → reject "freeze_authority_exists"
if creator_pct > 20:      → reject "creator_X_pct"
if top10_holder_pct > 70: → reject "top10_X_pct"
if lp_locked_pct < 10:    → reject "lp_not_locked"
```

**Результат:** ~90% токенів відхиляються. 0 Claude API викликів витрачено.

---

## Стадія 2 — Спеціалісти (Haiku)

Два агенти запускаються паралельно через `asyncio.gather()`.

### Twitter агент

Шукає по тикеру (`$SYMBOL`) і по темі (якщо назва схожа на меми/знаменитість):

```
Повертає JSON:
{
  "sentiment": "bullish|bearish|neutral|mixed",
  "organic_score": 1-10,
  "kol_count": <кількість аккаунтів >10k фолловерів>,
  "bot_likelihood": "low|medium|high",
  "narrative": "<реальна тема що драйвить інтерес>",
  "pre_existing_hype": <true якщо тема існувала ДО токена>,
  "top_accounts": ["@handle (Xk): цитата"],
  "summary": "2-3 речення"
}
```

### GMGN агент

Перевіряє smart money, поведінку dev'а, rug ризик:

```
Повертає JSON:
{
  "smart_money_count": <кількість або null>,
  "dev_behavior": "healthy|suspicious|dumping|unknown",
  "rat_traders": "low|medium|high|unknown",
  "rug_risk": "low|medium|high|unknown",
  "red_flags": ["<прапор>"],
  "summary": "2-3 речення"
}
```

---

## Стадія 3 — Master agent (Opus)

Отримує всі 4 звіти і приймає фінальне рішення:

```python
MASTER_SYSTEM = """
Ти фінальний арбітр. Токен вже пройшов DexScreener + Birdeye фільтри.
Твоя задача: оцінити потенціал на основі 4 джерел.

Score 8-10: сильний обʼєм + органічний Twitter нарратив + smart money
Score 7:    3 з 4 сигналів позитивні
Score 5-6:  змішані сигнали, пропустити
Score 1-4:  GMGN показує rug risk / dev dumps / Twitter = боти
"""
```

Вердикт JSON:
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

## Вартість викликів

| Сценарій | Claude виклики | Приблизна вартість |
|----------|---------------|-------------------|
| Відхилено на pre-filter (~90%) | **0** | $0.00 |
| Пройшов (2 Haiku + 1 Opus) | **3** | ~$0.02 |

**При 100 токенах за цикл:** ~10 проходять pre-filter → ~$0.20 на цикл vs ~$5.00 у старій архітектурі.

---

## Моделі

| Агент | Модель | Причина |
|-------|--------|---------|
| Twitter спеціаліст | `claude-haiku-4-5-20251001` | Дешевий, достатньо для одного джерела |
| GMGN спеціаліст | `claude-haiku-4-5-20251001` | Дешевий, достатньо для одного джерела |
| Master | `claude-opus-4-8` | Найкраща модель для фінального рішення |

---

## Ссылки

- [[Components/Data Sources]] — джерела даних
- [[Components/Trade Executor]] — що відбувається після score ≥ 7
- [[Strategy/Filters and Security]] — Python pre-filter деталі
