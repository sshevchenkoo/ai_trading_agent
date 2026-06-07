# Solana AI Trading Agent

Автоматический бот для торговли meme-токенами на Solana.

Мониторит **pump.fun**, **DexScreener** и **Twitter** каждые 5 минут, анализирует токены с помощью **Claude AI** (с данными Birdeye + CoinGecko), исполняет сделки через **Jupiter**.

---

## Как это работает

```
┌─────────────────────────────────────────────────────┐
│  pump.fun WebSocket (пассивный, всегда жив)          │
│  → складывает новые токены в очередь                 │
└──────────────────────┬──────────────────────────────┘
                       │
              каждые 5 минут
                       ▼
┌─────────────────────────────────────────────────────┐
│                 POLLER CYCLE                        │
│                                                     │
│  Параллельно:                                       │
│  ├── Забирает токены из очереди pump.fun            │
│  ├── DexScreener → новые пары на Solana             │
│  ├── Twitter → упоминания от KOL-аккаунтов          │
│  └── CoinGecko → цена SOL/BTC, тренд рынка         │
│                                                     │
│  Для каждого нового токена:                         │
│  ├── DexScreener → ликвидность, объём, возраст      │
│  ├── Birdeye     → безопасность, холдеры, топ трейд.│
│  ├── Rule Filters → отсеять ~90% (быстро, бесплатно)│
│  ├── Rugcheck    → проверка контракта               │
│  └── Claude AI   → score 1-10 + решение             │
│                          │                          │
│              final_score ≥ 7.0?                     │
│              YES → BUY_SIGNAL                       │
│              (Phase 3: реальная сделка)             │
└─────────────────────────────────────────────────────┘
```

**Стратегия выхода:** x2 → продать 50% | x4 → продать 25% | x10 → продать всё | -50% стоп-лосс

---

## Быстрый старт

### Требования

- Python 3.11+
- [Poetry](https://python-poetry.org/docs/#installation)

### Установка

```bash
git clone https://github.com/sshevchenkoo/ai_trading_agent.git
cd ai_trading_agent
poetry install
cp .env.example .env
```

### Конфигурация

Открой `.env` и заполни нужные ключи:

```bash
# Обязательно для Phase 1 — мониторинг токенов
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com

# Обязательно для Phase 2 — AI анализ
ANTHROPIC_API_KEY=sk-ant-...

# Рекомендуется — безопасность и on-chain данные (бесплатный план)
BIRDEYE_API_KEY=...

# Опционально — Twitter KOL сигналы
TWITTER_BEARER_TOKEN=...

# Обязательно для Phase 3 — реальные сделки
WALLET_PRIVATE_KEY=your_base58_private_key_here
```

> ⚠️ Никогда не коммить `.env` и `wallet.json` — они в `.gitignore`

### Запуск

```bash
# Paper trading (без реальных сделок, по умолчанию)
poetry run python main.py

# Боевой режим (только после проверки на paper trading!)
PAPER_TRADING=false poetry run python main.py
```

---

## Что видит Claude при анализе

Каждый токен прошедший фильтры отправляется Claude со всеми данными:

```
TOKEN:
- Symbol: $BONK2 | Age: 3 min | Market Cap: $85,000
- Liquidity: 134 SOL | Dev wallet sold: False
- Buy/Sell ratio (1h): 300/45

SOCIAL:
- Twitter mentions (1h): 12
- [cryptoKing, 820,000 followers, KOL] 340L 89RT — $BONK2 early gem!

SECURITY & ON-CHAIN (Birdeye):
- LP locked: 85% | Creator holds: 2.1%
- Top 10 holders: 31.4% | Unique wallets 24h: 423
- Price change 1h: +34.2% | Buys/Sells 24h: 890/210

MARKET CONTEXT:
- SOL price: $185.40 (+4.2% 24h) | Market mood: bullish
```

Claude возвращает `score 1-10`. Итоговый `final_score = rule_score×0.4 + ai_score×0.6`.

---

## Настройки стратегии (.env)

| Переменная | По умолчанию | Описание |
|------------|-------------|----------|
| `MIN_LIQUIDITY_SOL` | 50 | Минимальная ликвидность токена |
| `AI_SCORE_THRESHOLD` | 7.0 | Минимальный score для покупки |
| `MAX_POSITION_SIZE_SOL` | 0.2 | Максимум SOL на одну позицию |
| `MAX_OPEN_POSITIONS` | 5 | Максимум одновременных позиций |
| `STOP_LOSS_PCT` | 50 | Стоп-лосс в % |
| `PAPER_TRADING` | true | Режим без реальных сделок |

---

## Структура проекта

```
├── main.py                  # Точка входа, оркестратор
├── config.py                # Все настройки из .env
│
├── sources/
│   ├── signal.py            # Модели TokenSignal, TweetInfo, MarketContext
│   ├── pumpfun.py           # WebSocket — собирает токены в очередь
│   ├── poller.py            # Планировщик — запускает цикл каждые 5 мин
│   ├── dexscreener.py       # Новые пары + обогащение метриками
│   ├── birdeye.py           # Security, holders, on-chain данные
│   ├── twitter.py           # KOL упоминания токенов
│   └── market_data.py       # Цена SOL/BTC, тренд рынка (CoinGecko)
│
├── analysis/
│   ├── filters.py           # Rule-based фильтры (быстро, без API)
│   ├── rugcheck.py          # Проверка контракта через rugcheck.xyz
│   └── ai_analyzer.py       # Claude API — финальное решение
│
├── trading/                 # Phase 3 (в разработке)
│   ├── wallet.py            # Solana wallet
│   ├── jupiter.py           # Jupiter swap API
│   └── executor.py          # Trade Executor
│
├── positions/               # Phase 3 (в разработке)
│   ├── manager.py           # Управление позициями
│   └── monitor.py           # Мониторинг цен каждые 10 сек
│
├── db/
│   ├── models.py            # Token, Signal, Trade, Position таблицы
│   └── database.py          # SQLite подключение
│
└── utils/
    └── logger.py            # Structlog структурированные логи
```

---

## Внешние API

| Сервис | Зачем | Стоимость |
|--------|-------|-----------|
| [Anthropic](https://console.anthropic.com) | Claude AI анализ | ~$3-10/день |
| [Birdeye](https://birdeye.so) | Security + on-chain данные | Бесплатный план |
| CoinGecko | Цена SOL/BTC, рыночный тренд | Бесплатно |
| Rugcheck | Проверка контрактов | Бесплатно |
| DexScreener | Ликвидность, объём, пары | Бесплатно |
| pump.fun WS | Новые токены в реальном времени | Бесплатно |
| [Helius RPC](https://helius.dev) | Надёжный Solana RPC (Phase 3) | $49+/мес |
| [Twitter/X API](https://developer.twitter.com) | KOL мониторинг | $100/мес |

**Минимальный бюджет для старта (Phase 1-2):** ~$10/мес (только Anthropic API)

---

## Roadmap

- [x] **Phase 1** — pump.fun WebSocket + DexScreener + Rule Filters + Rugcheck + SQLite
- [x] **Phase 2** — Claude AI анализ + Birdeye on-chain data + CoinGecko market context + Twitter KOL
- [ ] **Phase 3** — Jupiter swap + Solana wallet + Position Manager + автоматические продажи
- [ ] **Phase 4** — Trailing Stop, Telegram алерты, оптимизация промптов
- [ ] **Phase 5** — Birdeye smart money tracking, whale wallets, масштабирование

---

## Важно

Это экспериментальный проект. Торговля meme-токенами крайне рискованна.
Всегда начинай с `PAPER_TRADING=true` и никогда не торгуй деньгами которые не готов потерять.
