# Архітектура системи

## Загальна схема потоку даних

```
┌─────────────────────────────────────────────────────────┐
│                    DATA LAYER                           │
│                                                         │
│  [pump.fun WS] ──┐  WebSocket, пасивний, завжди живий  │
│  [DexScreener]  ──┼──► [asyncio.Queue]  (нові токени)  │
│                  └──► збирає кожні 5 хв                │
└───────────────────────────────┬─────────────────────────┘
                                │
                     кожні 5 хвилин (Poller)
                                │
                    ┌───────────▼───────────┐
                    │  DexScreener enrich   │
                    │  (real mcap/liquidity)│
                    └───────────┬───────────┘
                                │
                    ┌───────────▼───────────┐
                    │  mcap > $5,000?       │
                    │  NO → discard         │
                    └───────────┬───────────┘
                                │ YES
                                ▼
┌─────────────────────────────────────────────────────────┐
│              ANALYSIS LAYER (3 стадії)                  │
│                                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │ Стадія 1: Python pre-filter  (без Claude)        │  │
│  │  DexScreener ──┐  паралельно                     │  │
│  │  Birdeye ──────┘                                 │  │
│  │  Hard reject: нема обʼєму / security flags       │  │
│  │  ~90% токенів зупиняється тут (0 Claude calls)   │  │
│  └──────────────────────────┬───────────────────────┘  │
│                             │ ~10% пройшло              │
│  ┌──────────────────────────▼───────────────────────┐  │
│  │ Стадія 2: Specialist agents (Haiku, паралельно)  │  │
│  │  [Twitter Haiku] ──┐                             │  │
│  │  [GMGN Haiku]   ───┘ asyncio.gather()            │  │
│  └──────────────────────────┬───────────────────────┘  │
│                             │                           │
│  ┌──────────────────────────▼───────────────────────┐  │
│  │ Стадія 3: Master agent (Opus)                    │  │
│  │  Отримує: DexScreener + Birdeye + Twitter + GMGN │  │
│  │  Повертає: score 1-10 + вердикт                  │  │
│  └──────────────────────────┬───────────────────────┘  │
│                             │                           │
│                    score ≥ 7.0?                         │
│                   NO → discard   YES → BUY_SIGNAL       │
└─────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────┐
│                  TRADING LAYER (Phase 3)                │
│                                                         │
│          [Trade Executor] ──► [Solana Wallet]           │
│                │              (Jupiter swap)            │
│                │                                        │
│          [Position Manager]                             │
│                │                                        │
│     ┌──────────┼──────────┐                             │
│     ▼          ▼          ▼                             │
│  [+100%]    [+300%]    [+900%]   [-50%]                 │
│  sell 50%  sell 25%  sell rest  stop-loss               │
└─────────────────────────────────────────────────────────┘
```

---

## Компоненти і їх ролі

### Poller
Кожні 5 хвилин: дренує чергу pump.fun + запитує DexScreener нові пари. Дедублікує токени, збагачує реальними метриками (mcap, liquidity), відсіює mcap < $5k.

### Python pre-filter (Стадія 1)
Детерміновані перевірки — без AI. Паралельно запитує DexScreener і Birdeye, застосовує hard rules. ~90% токенів відхиляються тут без жодного Claude виклику.

### Specialist agents (Стадія 2)
Два Haiku агенти запускаються паралельно:
- **Twitter агент** — sentiment, KOL mentions, органічний нарратив
- **GMGN агент** — smart money, поведінка dev'а, rug risk

### Master agent (Стадія 3)
Opus отримує всі 4 звіти (DexScreener + Birdeye з pre-filter + Twitter + GMGN від спеціалістів) і приймає фінальний вердикт.

### Trade Executor (Phase 3)
Викликає Jupiter API для отримання котировки і виконання свопу. Підписує транзакцію ключем гаманця.

### Position Manager (Phase 3)
Зберігає всі відкриті позиції. Кожні N секунд запитує поточну ціну і перевіряє тригери продажу.

---

## Взаємодія в реальному часі

```
t=0ms     pump.fun WS → новий токен створений → в чергу
t=0ms     ...накопичуємо 5 хвилин...
t=300000ms Poller прокидається
t=300010ms drain черги + DexScreener нові пари
t=300050ms enrich всіх токенів (паралельно)
t=300200ms mcap < $5k → discard більшість
t=300210ms Stage 1: DexScreener + Birdeye паралельно (~90% reject)
t=300600ms Stage 2: Twitter + GMGN Haiku паралельно
t=301200ms Stage 3: Opus master вердикт
t=301201ms score ≥ 7.0 → BUY_SIGNAL
t=301300ms (Phase 3) Trade Executor → Jupiter swap
t=302000ms транзакція підтверджена, Position Manager додає позицію
```

---

## Зберігання даних

```
SQLite:
├── tokens    — всі побачені токени і їх метрики
├── signals   — всі сигнали від джерел
├── positions — відкриті і закриті позиції
├── trades    — історія всіх угод (buy/sell)
```

---

## Посилання

- [[Components/Data Sources]] — деталі по кожному джерелу
- [[Components/AI Analyzer]] — мультиагентний аналіз
- [[Components/Trade Executor]] — Jupiter інтеграція
- [[Components/Position Manager]] — логіка виходів
- [[Strategy/Filters and Security]] — Python pre-filter правила
