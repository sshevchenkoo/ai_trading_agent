# Технический стек

## Язык: Python 3.11+

Python выбран потому что:
- Нативный `anthropic` SDK
- Лучшая экосистема для async I/O (asyncio)
- Solana SDK (`solders`) имеет Python биндинги
- Быстрее прототипировать

---

## Зависимости

```toml
# pyproject.toml

[tool.poetry.dependencies]
python = "^3.11"

# Solana
solders = "^0.21.0"          # Solana SDK (Rust-based, быстрый)
solana = "^0.35.0"           # RPC клиент

# AI
anthropic = "^0.40.0"        # Claude API

# HTTP / WebSocket
httpx = "^0.27.0"            # async HTTP клиент
websockets = "^12.0"         # WebSocket клиент

# Twitter
tweepy = "^4.14.0"           # X API v2

# База данных
sqlmodel = "^0.0.21"         # ORM (SQLAlchemy + Pydantic)
aiosqlite = "^0.20.0"        # async SQLite

# Утилиты
pydantic = "^2.8.0"          # валидация данных
pydantic-settings = "^2.4.0" # конфиг из .env
structlog = "^24.4.0"        # структурированные логи
python-dotenv = "^1.0.1"     # .env файлы
base58 = "^2.1.1"            # кодировка кошелька

# Мониторинг (опционально)
prometheus-client = "^0.21.0" # метрики
```

---

## Структура проекта

```
solana_trader/
├── pyproject.toml
├── .env                    # секреты (в .gitignore!)
├── .env.example            # шаблон без секретов
├── .gitignore
│
├── main.py                 # точка входа, оркестратор
│
├── config.py               # настройки из .env
│
├── sources/
│   ├── __init__.py
│   ├── pumpfun.py          # WebSocket listener pump.fun
│   ├── dexscreener.py      # REST API poller
│   └── twitter.py          # X API stream
│
├── analysis/
│   ├── __init__.py
│   ├── filters.py          # Rule-based фильтры
│   ├── rugcheck.py         # Rugcheck API интеграция
│   └── ai_analyzer.py      # Claude API анализ
│
├── trading/
│   ├── __init__.py
│   ├── wallet.py           # Solana wallet управление
│   ├── jupiter.py          # Jupiter swap API
│   └── executor.py         # Trade Executor
│
├── positions/
│   ├── __init__.py
│   ├── manager.py          # Position Manager
│   └── monitor.py          # Price monitoring loop
│
├── db/
│   ├── __init__.py
│   ├── models.py           # SQLModel таблицы
│   └── database.py         # подключение к БД
│
└── utils/
    ├── __init__.py
    └── logger.py           # настройка логов
```

---

## Конфигурация (.env)

```bash
# .env.example — копировать в .env, заполнить значениями

# Solana
SOLANA_RPC_URL=https://mainnet.helius-rpc.com/?api-key=YOUR_KEY
WALLET_PRIVATE_KEY=your_base58_private_key_here

# AI
ANTHROPIC_API_KEY=sk-ant-...

# Twitter/X API
TWITTER_BEARER_TOKEN=...
TWITTER_API_KEY=...
TWITTER_API_SECRET=...
TWITTER_ACCESS_TOKEN=...
TWITTER_ACCESS_SECRET=...

# Стратегия
MAX_POSITION_SIZE_SOL=0.2
MIN_LIQUIDITY_SOL=50
AI_SCORE_THRESHOLD=7.0
MAX_OPEN_POSITIONS=5
STOP_LOSS_PCT=50

# Режим
PAPER_TRADING=true          # true = не исполнять реальных сделок
LOG_LEVEL=INFO
```

---

## Запуск

```bash
# Установка зависимостей
pip install poetry
poetry install

# Запуск (paper trading режим)
poetry run python main.py

# Запуск в боевом режиме
PAPER_TRADING=false poetry run python main.py

# Запуск как сервис (systemd / screen)
screen -S trader
poetry run python main.py
# Ctrl+A, D — отсоединиться
```

---

## Внешние сервисы и API-ключи

| Сервис | Зачем | Стоимость |
|--------|-------|-----------|
| Anthropic API | Claude анализ | pay-per-use (~$3-10/день) |
| Helius RPC | Solana RPC | $49-499/мес |
| Twitter/X API | Мониторинг твитов | $100/мес (Basic) |
| Rugcheck | Проверка контрактов | бесплатно |
| DexScreener | Цены и пары | бесплатно |
| pump.fun WS | Новые токены | бесплатно |

**Минимальный бюджет для старта:** ~$150/мес + торговый депозит (1-5 SOL)

---

## Ссылки

- [[Development/Roadmap]] — когда что добавляем
- [[Components/Trade Executor]] — детали Jupiter интеграции
- [[Components/AI Analyzer]] — детали Claude API
