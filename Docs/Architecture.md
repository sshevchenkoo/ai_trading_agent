# Архитектура системы

## Общая схема потока данных

```
┌─────────────────────────────────────────────────────────┐
│                    DATA LAYER                           │
│                                                         │
│  [pump.fun WS] ──┐                                      │
│  [DexScreener]  ──┼──► [Signal Aggregator]              │
│  [Twitter API]  ──┘           │                         │
└───────────────────────────────┼─────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────┐
│                  ANALYSIS LAYER                         │
│                                                         │
│              [Rule Filters] ──► [AI Analyzer]           │
│               (быстро, дёшево)  (Claude API)            │
│                                      │                  │
└──────────────────────────────────────┼──────────────────┘
                                       │
                              score ≥ threshold?
                                       │
                    NO ─── discard     YES ──► proceed
                                       │
┌──────────────────────────────────────┼──────────────────┐
│                  TRADING LAYER       ▼                  │
│                                                         │
│              [Trade Executor] ──► [Solana Wallet]       │
│                    │              (Jupiter swap)        │
│                    │                                    │
│              [Position Manager]                         │
│                    │                                    │
│         ┌──────────┼──────────┐                        │
│         ▼          ▼          ▼                        │
│      [+100%]    [+300%]    [+900%]   [-50%]            │
│      sell 50%  sell 25%  sell rest  stop-loss          │
└─────────────────────────────────────────────────────────┘
```

---

## Компоненты и их роли

### Signal Aggregator
Центральная шина. Получает события от всех источников данных, нормализует их в единый формат `TokenSignal`, дедуплицирует (один токен может прийти из нескольких источников).

```
TokenSignal {
  token_address: str
  symbol: str
  source: "pumpfun" | "dexscreener" | "twitter"
  triggered_at: timestamp
  
  # метрики токена
  liquidity_sol: float
  market_cap_usd: float
  holder_count: int
  top10_holder_pct: float
  dev_wallet_sold: bool
  age_minutes: int
  
  # социальные сигналы
  twitter_mentions_1h: int
  kol_mentions: list[str]
  tweet_texts: list[str]
  
  # расчётный скор
  rule_score: float   # от фильтров
  ai_score: float     # от Claude
  final_score: float  # итог
}
```

### Rule Filters (быстрые фильтры)
Первая линия защиты — дешёвые проверки без AI, отсеивают ~80% токенов за миллисекунды.

### AI Analyzer
Вызывается только для токенов, прошедших фильтры. Claude анализирует твиты, оценивает контекст, возвращает скор и reasoning.

### Trade Executor
Вызывает Jupiter API для получения котировки и исполнения свопа. Подписывает транзакцию ключом кошелька.

### Position Manager
Хранит все открытые позиции. Каждые N секунд запрашивает текущую цену и проверяет триггеры продажи.

---

## Взаимодействие в реальном времени

```
t=0ms   pump.fun WS → новый токен создан
t=5ms   Signal Aggregator получает событие
t=10ms  Rule Filters → быстрая проверка (pass/fail)
t=15ms  Twitter API → ищем упоминания за последний час
t=500ms AI Analyzer → Claude API вызов
t=1500ms final_score рассчитан
t=1501ms если score ≥ 7.0 → Trade Executor
t=2000ms транзакция отправлена на Solana
t=2500ms подтверждение, Position Manager добавляет позицию
```

---

## Хранение данных

```
SQLite / PostgreSQL:
├── tokens          — все виденные токены и их метрики
├── signals         — все сигналы от источников
├── positions       — открытые и закрытые позиции
├── trades          — история всех сделок (buy/sell)
└── ai_analyses     — ответы Claude (для аудита и обучения)
```

---

## Ссылки

- [[Components/Data Sources]] — детали по каждому источнику
- [[Components/AI Analyzer]] — промпты и логика анализа
- [[Components/Trade Executor]] — Jupiter интеграция
- [[Components/Position Manager]] — логика выходов
- [[Strategy/Filters and Security]] — правила фильтров
