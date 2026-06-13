# Tech Stack

## Language: Python 3.11+

Python was chosen because:
- Native `anthropic` SDK
- Best ecosystem for async I/O (asyncio)
- Solana SDK (`solders`) has Python bindings
- Fastest to prototype

---

## Dependencies

```toml
# pyproject.toml

[tool.poetry.dependencies]
python = "^3.11"

# Solana
solders = "^0.21.0"          # Solana SDK (Rust-based, fast)
solana = "^0.35.0"           # RPC client

# AI
anthropic = "^0.40.0"        # Claude API

# HTTP / WebSocket
httpx = "^0.27.0"            # async HTTP client
websockets = "^12.0"         # WebSocket client

# Twitter
tweepy = "^4.14.0"           # X API v2

# Database
sqlmodel = "^0.0.21"         # ORM (SQLAlchemy + Pydantic)
aiosqlite = "^0.20.0"        # async SQLite

# Utilities
pydantic = "^2.8.0"          # data validation
pydantic-settings = "^2.4.0" # config from .env
structlog = "^24.4.0"        # structured logging
python-dotenv = "^1.0.1"     # .env files
base58 = "^2.1.1"            # wallet key encoding

# Monitoring (optional)
prometheus-client = "^0.21.0" # metrics
```

---

## Project structure

```
solana_trader/
├── pyproject.toml
├── .env                    # secrets (in .gitignore!)
├── .env.example            # template without secrets
├── .gitignore
│
├── main.py                 # entry point, orchestrator
│
├── config.py               # settings from .env
│
├── sources/
│   ├── __init__.py
│   ├── pumpfun.py          # WebSocket listener for pump.fun
│   ├── dexscreener.py      # REST API poller
│   └── twitter.py          # X API stream
│
├── analysis/
│   ├── __init__.py
│   ├── filters.py          # Rule-based filters
│   ├── rugcheck.py         # Rugcheck API integration
│   └── ai_analyzer.py      # Claude API analysis
│
├── trading/
│   ├── __init__.py
│   ├── wallet.py           # Solana wallet management
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
│   ├── models.py           # SQLModel tables
│   └── database.py         # database connection
│
└── utils/
    ├── __init__.py
    └── logger.py           # log configuration
```

---

## Configuration (.env)

```bash
# .env.example — copy to .env and fill in your values

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

# Strategy
MAX_POSITION_SIZE_SOL=0.2
MIN_LIQUIDITY_SOL=50
AI_SCORE_THRESHOLD=7.0
MAX_OPEN_POSITIONS=5
STOP_LOSS_PCT=50

# Mode
PAPER_TRADING=true          # true = no real trades executed
LOG_LEVEL=INFO
```

---

## Running

```bash
# Install dependencies
pip install poetry
poetry install

# Run in paper trading mode
poetry run python main.py

# Run in live mode
PAPER_TRADING=false poetry run python main.py

# Run as a service (systemd / screen)
screen -S trader
poetry run python main.py
# Ctrl+A, D — detach
```

---

## External services and API keys

| Service | Purpose | Cost |
|---------|---------|------|
| Anthropic API | Claude analysis | pay-per-use (~$3–10/day) |
| Helius RPC | Solana RPC | $49–499/mo |
| Twitter/X API | Tweet monitoring | $100/mo (Basic) |
| Rugcheck | Contract verification | free |
| DexScreener | Prices and pairs | free |
| pump.fun WS | New tokens | free |

**Minimum budget to start:** ~$150/mo + trading deposit (1–5 SOL)

---

## Links

- [[Development/Roadmap]] — what we add and when
- [[Components/Trade Executor]] — Jupiter integration details
- [[Components/AI Analyzer]] — Claude API details
