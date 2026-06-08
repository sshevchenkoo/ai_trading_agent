# Solana AI Trading Agent

Автоматичний бот для торгівлі meme-токенами на Solana.

Моніторить **pump.fun** і **DexScreener** кожні 5 хвилин, фільтрує токени через **Python pre-filter** (DexScreener + Birdeye), потім використовує **мультиагентний Claude AI** (Twitter + GMGN спеціалісти + Opus майстер) для прийняття рішення. Виконує угоди через **Jupiter** (Phase 3).

---

## Як це працює

```
┌─────────────────────────────────────────────────────┐
│  pump.fun WebSocket (пасивний, завжди живий)         │
│  → складає нові токени в чергу                      │
└──────────────────────┬──────────────────────────────┘
                       │
              кожні 5 хвилин
                       ▼
┌─────────────────────────────────────────────────────┐
│              POLLER CYCLE                           │
│                                                     │
│  Drain черги pump.fun + DexScreener нові пари       │
│  → DexScreener enrich (real mcap/liquidity)         │
│  → mcap < $5,000 → discard                         │
│                                                     │
│  STAGE 1 — Python pre-filter (без Claude):          │
│  ├── DexScreener: buys_1h < 5 → discard            │
│  ├── DexScreener: volume_1h < $500 → discard       │
│  ├── Birdeye: mint/freeze authority → discard       │
│  ├── Birdeye: creator >20% → discard               │
│  └── Birdeye: top10 >70% → discard                 │
│  (~90% токенів зупиняється тут, 0 Claude calls)     │
│                                                     │
│  STAGE 2 — Specialist agents (Haiku, паралельно):   │
│  ├── Twitter agent → sentiment, KOLs, narrative    │
│  └── GMGN agent → smart money, dev behavior        │
│                                                     │
│  STAGE 3 — Master agent (Opus):                     │
│  Отримує: DexScreener + Birdeye + Twitter + GMGN   │
│  Повертає: score 1-10                               │
│                                                     │
│              score ≥ 7.0?                           │
│              YES → BUY_SIGNAL                       │
│              (Phase 3: реальна угода)               │
└─────────────────────────────────────────────────────┘
```

**Стратегія виходу:** x2 → продати 50% | x4 → продати 25% | x10 → продати все | -50% стоп-лосс

---

## Швидкий старт

### Вимоги

- Python 3.11+
- [Poetry](https://python-poetry.org/docs/#installation)

### Встановлення

```bash
git clone https://github.com/sshevchenkoo/ai_trading_agent.git
cd ai_trading_agent
poetry install
cp .env.example .env
```

### Конфігурація

Відкрий `.env` і заповни потрібні ключі:

```bash
# Обовʼязково для Phase 1 — моніторинг токенів
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com

# Обовʼязково для Phase 2 — AI аналіз
ANTHROPIC_API_KEY=sk-ant-...

# Рекомендується — security і on-chain дані (безкоштовний план)
BIRDEYE_API_KEY=...

# Опціонально — Twitter KOL сигнали
TWITTER_BEARER_TOKEN=...

# Обовʼязково для Phase 3 — реальні угоди
WALLET_PRIVATE_KEY=your_base58_private_key_here
```

> ⚠️ Ніколи не комміть `.env` і `wallet.json` — вони в `.gitignore`

### Запуск

```bash
# Paper trading (без реальних угод, за замовчуванням)
poetry run python main.py

# Бойовий режим (тільки після перевірки на paper trading!)
PAPER_TRADING=false poetry run python main.py
```

---

## Мультиагентний аналіз

Кожен токен що пройшов pre-filter аналізується трьома агентами:

```
Twitter Haiku:     знаходить KOLів, оцінює органічність хайпу
                   якщо назва схожа на меми → шукає нарратив до токена
GMGN Haiku:        smart money holders, поведінка dev'а, rug risk

Opus master:       отримує всі 4 звіти → фінальний вердикт
```

**Приклад BUY сигналу в логах:**
```
BUY_SIGNAL  symbol=BARRONDOG  score=8.7  confidence=high
            risk=medium  suggested_sol=0.2  timeframe=hours
            reasoning="Pre-existing Twitter hype around 'barron trump dog',
                       12 smart money wallets holding, clean security,
                       buy/sell ratio 4.2x in last hour"
```

---

## Налаштування стратегії (.env)

| Змінна | За замовчуванням | Опис |
|--------|-----------------|------|
| `AI_SCORE_THRESHOLD` | 7.0 | Мінімальний score для покупки |
| `MAX_POSITION_SIZE_SOL` | 0.2 | Максимум SOL на одну позицію |
| `MAX_OPEN_POSITIONS` | 5 | Максимум одночасних позицій |
| `STOP_LOSS_PCT` | 50 | Стоп-лосс у % |
| `PAPER_TRADING` | true | Режим без реальних угод |

---

## Структура проекту

```
├── main.py                  # Точка входу, оркестратор
├── config.py                # Всі налаштування з .env
│
├── sources/
│   ├── signal.py            # Моделі TokenSignal, TweetInfo, MarketContext
│   ├── pumpfun.py           # WebSocket — збирає токени в чергу
│   ├── poller.py            # Планувальник — запускає цикл кожні 5 хв + mcap фільтр
│   ├── dexscreener.py       # Нові пари + збагачення метриками
│   ├── birdeye.py           # Security, holders, on-chain дані
│   ├── twitter.py           # Пошук згадок токена в Twitter
│   └── market_data.py       # Ціна SOL/BTC, тренд ринку (CoinGecko)
│
├── analysis/
│   ├── filters.py           # (legacy) Rule-based фільтри
│   ├── rugcheck.py          # (legacy) Перевірка контракту через rugcheck.xyz
│   └── ai_analyzer.py       # Мультиагентний аналіз: pre-filter + Haiku x2 + Opus
│
├── trading/                 # Phase 3 (в розробці)
│   ├── wallet.py            # Solana wallet
│   ├── jupiter.py           # Jupiter swap API
│   └── executor.py          # Trade Executor
│
├── positions/               # Phase 3 (в розробці)
│   ├── manager.py           # Управління позиціями
│   └── monitor.py           # Моніторинг цін кожні 10 сек
│
├── db/
│   ├── models.py            # Token, Signal, Trade, Position таблиці
│   └── database.py          # SQLite підключення
│
└── utils/
    └── logger.py            # Structlog структуровані логи
```

---

## Зовнішні API

| Сервіс | Навіщо | Вартість |
|--------|--------|----------|
| [Anthropic](https://console.anthropic.com) | Claude AI (Haiku спеціалісти + Opus майстер) | ~$0.50-2/день |
| [Birdeye](https://birdeye.so) | Security + on-chain дані | Безкоштовний план |
| CoinGecko | Ціна SOL/BTC, ринковий тренд | Безкоштовно |
| DexScreener | Ліквідність, обʼєм, пари | Безкоштовно |
| [GMGN](https://gmgn.ai) | Smart money, dev behavior | Безкоштовно (public API) |
| pump.fun WS | Нові токени в реальному часі | Безкоштовно |
| [Helius RPC](https://helius.dev) | Надійний Solana RPC (Phase 3) | $49+/міс |
| [Twitter/X API](https://developer.twitter.com) | KOL моніторинг | $100/міс |

**Мінімальний бюджет для старту (Phase 1-2):** ~$5/міс (тільки Anthropic API)

---

## Roadmap

- [x] **Phase 1** — pump.fun WebSocket + DexScreener + SQLite + structlog
- [x] **Phase 2** — Мультиагентний Claude AI + Birdeye + GMGN + Twitter + Python pre-filter
- [ ] **Phase 3** — Jupiter swap + Solana wallet + Position Manager + автоматичні продажі
- [ ] **Phase 4** — Trailing Stop, Telegram алерти, оптимізація промптів
- [ ] **Phase 5** — Whale tracking, масштабування

---

## Важливо

Це експериментальний проект. Торгівля meme-токенами надзвичайно ризикована.
Завжди починай з `PAPER_TRADING=true` і ніколи не торгуй грошима які не готовий втратити.
