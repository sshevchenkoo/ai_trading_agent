# Solana AI Trading Agent

Автоматический бот для торговли meme-токенами на Solana.

Мониторит **pump.fun**, **Twitter** и **DexScreener**, анализирует токены с помощью **Claude AI**, исполняет сделки через **Jupiter**.

## Как это работает

```
pump.fun WebSocket ──┐
DexScreener API    ──┼──► Rule Filters ──► Claude AI ──► Jupiter Swap
Twitter API        ──┘         ↓ (fail)
                           пропустить
```

1. Видим новый токен на pump.fun в момент запуска
2. Обогащаем данными с DexScreener (ликвидность, объём, транзакции)
3. Быстрые Rule Filters отсеивают ~90% (скамы, низкая ликвидность, blacklist)
4. Rugcheck проверяет контракт
5. Claude анализирует нарратив, твиты, красные флаги — ставит score 1-10
6. Если score ≥ 7.0 → покупка через Jupiter
7. Автоматические продажи при x2 / x4 / x10, стоп-лосс -50%

## Быстрый старт

### 1. Требования

- Python 3.11+
- [Poetry](https://python-poetry.org/docs/#installation)

### 2. Установка

```bash
git clone https://github.com/YOUR_USERNAME/solana-ai-trader.git
cd solana-ai-trader
poetry install
```

### 3. Конфигурация

```bash
cp .env.example .env
```

Открой `.env` и заполни:

```bash
# Обязательно для Phase 1 (мониторинг без сделок)
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com  # или Helius

# Обязательно для Phase 2 (AI анализ)
ANTHROPIC_API_KEY=sk-ant-...

# Обязательно для Phase 3 (реальные сделки)
WALLET_PRIVATE_KEY=your_base58_private_key_here

# Опционально (Twitter сигналы)
TWITTER_BEARER_TOKEN=...
```

> ⚠️ Никогда не коммить `.env` и `wallet.json` — они в `.gitignore`

### 4. Запуск

```bash
# Paper trading (без реальных сделок, по умолчанию)
poetry run python main.py

# Боевой режим (только после paper trading!)
PAPER_TRADING=false poetry run python main.py
```

## Настройки стратегии (.env)

| Переменная | По умолчанию | Описание |
|-----------|-------------|----------|
| `MIN_LIQUIDITY_SOL` | 50 | Минимальная ликвидность токена |
| `AI_SCORE_THRESHOLD` | 7.0 | Минимальный AI score для покупки |
| `MAX_POSITION_SIZE_SOL` | 0.2 | Максимум SOL на одну позицию |
| `MAX_OPEN_POSITIONS` | 5 | Максимум одновременных позиций |
| `STOP_LOSS_PCT` | 50 | Стоп-лосс в процентах |
| `PAPER_TRADING` | true | Режим без реальных сделок |

## Структура проекта

```
├── main.py              # Точка входа, оркестратор
├── config.py            # Настройки из .env
│
├── sources/
│   ├── signal.py        # Модель TokenSignal
│   ├── pumpfun.py       # WebSocket listener
│   ├── dexscreener.py   # Обогащение данных
│   └── twitter.py       # Twitter мониторинг (Phase 2)
│
├── analysis/
│   ├── filters.py       # Rule-based фильтры
│   ├── rugcheck.py      # Проверка контрактов
│   └── ai_analyzer.py   # Claude API анализ (Phase 2)
│
├── trading/
│   ├── wallet.py        # Solana wallet (Phase 3)
│   ├── jupiter.py       # Jupiter swap API (Phase 3)
│   └── executor.py      # Trade Executor (Phase 3)
│
├── positions/
│   ├── manager.py       # Position Manager (Phase 3)
│   └── monitor.py       # Price monitoring (Phase 3)
│
├── db/
│   ├── models.py        # SQLModel таблицы
│   └── database.py      # SQLite подключение
│
└── utils/
    └── logger.py        # Structlog логирование
```

## Roadmap

- [x] **Phase 1** — pump.fun listener + Rule Filters + Rugcheck + SQLite
- [ ] **Phase 2** — Twitter API + Claude AI анализ + paper trading
- [ ] **Phase 3** — Jupiter swap + Position Manager + автоматические продажи
- [ ] **Phase 4** — Оптимизация, Trailing Stop, Telegram алерты
- [ ] **Phase 5** — Масштабирование депозита

## Внешние API

| Сервис | Зачем | Стоимость |
|--------|-------|-----------|
| [Anthropic](https://console.anthropic.com) | Claude AI анализ | ~$3-10/день |
| [Helius](https://helius.dev) | Надёжный Solana RPC | $49+/мес |
| [Twitter/X API](https://developer.twitter.com) | Мониторинг KOL | $100/мес |
| Rugcheck | Проверка контрактов | Бесплатно |
| DexScreener | Цены и метрики | Бесплатно |
| pump.fun WS | Новые токены | Бесплатно |

**Минимальный бюджет для старта:** ~$150/мес + торговый депозит (0.5-5 SOL)

## Важно

Это экспериментальный проект. Торговля meme-токенами очень рискованна. Начинай с `PAPER_TRADING=true` и малого депозита.
