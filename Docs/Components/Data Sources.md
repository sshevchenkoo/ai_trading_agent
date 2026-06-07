# Data Sources — Источники данных

Три независимых источника сигналов, которые работают параллельно и скармливают данные в [[Architecture#Signal Aggregator|Signal Aggregator]].

---

## 1. pump.fun WebSocket

**Что даёт:** каждый новый токен на Solane в момент запуска, ещё до того как он попадёт на DexScreener.

**Endpoint:**
```
wss://pumpportal.fun/api/data
```

**Подписка на новые токены:**
```python
import websockets
import json

async def listen_pumpfun():
    uri = "wss://pumpportal.fun/api/data"
    async with websockets.connect(uri) as ws:
        # подписываемся на новые токены
        await ws.send(json.dumps({
            "method": "subscribeNewToken"
        }))
        async for message in ws:
            data = json.loads(message)
            await handle_new_token(data)
```

**Структура события:**
```json
{
  "mint": "TokenAddressHere",
  "name": "Token Name",
  "symbol": "TICKER",
  "description": "...",
  "image_uri": "...",
  "creator": "CreatorWalletAddress",
  "market_cap": 8500,
  "virtual_sol_reserves": 30.5,
  "timestamp": 1717776000
}
```

**Важно:**
- pump.fun токены начинают с ~30 SOL ликвидности (виртуальной)
- Только при достижении market cap ~$69k токен листится на Raydium
- Большинство токенов умирают раньше — нужны хорошие фильтры

---

## 2. DexScreener API

**Что даёт:** новые торговые пары на Solane (не только pump.fun), цену, объём, ликвидность, транзакции.

**Endpoints:**
```
# Новые пары (polling каждые 30 сек)
GET https://api.dexscreener.com/token-profiles/latest/v1

# Данные по конкретному токену
GET https://api.dexscreener.com/latest/dex/tokens/{address}

# Поиск по тикеру
GET https://api.dexscreener.com/latest/dex/search?q={symbol}
```

**Пример ответа по токену:**
```json
{
  "pairs": [{
    "chainId": "solana",
    "dexId": "raydium",
    "baseToken": {
      "address": "...",
      "name": "...",
      "symbol": "..."
    },
    "priceUsd": "0.00002341",
    "liquidity": { "usd": 45000, "base": 1000000000, "quote": 150 },
    "volume": { "h1": 12000, "h24": 89000 },
    "priceChange": { "m5": 12.3, "h1": 45.2, "h24": 234.1 },
    "txns": {
      "h1": { "buys": 234, "sells": 45 }
    },
    "pairCreatedAt": 1717776000000
  }]
}
```

**Что смотрим:**
- `liquidity.quote` — ликвидность в SOL (мин. 50 SOL)
- `txns.h1.buys / sells` — соотношение покупок к продажам
- `priceChange.h1` — рост за час
- `pairCreatedAt` — возраст пары

---

## 3. Twitter / X API

**Что даёт:** упоминания токенов от реальных людей и KOL-аккаунтов до того, как цена улетела.

**Используем:** X API v2, Filtered Stream или Recent Search

```python
import tweepy

client = tweepy.Client(bearer_token=BEARER_TOKEN)

# Поиск свежих твитов по тикеру
def search_token_tweets(symbol: str, hours: int = 1) -> list:
    query = f"${symbol} OR #{symbol} lang:en -is:retweet"
    tweets = client.search_recent_tweets(
        query=query,
        max_results=100,
        tweet_fields=["created_at", "public_metrics", "author_id"],
        expansions=["author_id"],
        user_fields=["public_metrics"]
    )
    return tweets.data or []
```

**Filtered Stream (для мониторинга в реальном времени):**
```python
# Слушаем твиты с упоминанием Solana токенов
rules = [
    {"value": "pump.fun lang:en", "tag": "pumpfun_mentions"},
    {"value": "$SOL new token lang:en", "tag": "new_tokens"},
]
```

**Метрики для оценки твита:**
```python
tweet_score = {
    "author_followers": tweet.author.public_metrics["followers_count"],
    "likes": tweet.public_metrics["like_count"],
    "retweets": tweet.public_metrics["retweet_count"],
    "is_kol": tweet.author_id in KOL_WHITELIST,
}
```

**KOL Whitelist** — список известных крипто-инфлюенсеров, чьи упоминания дают высокий вес сигналу.

---

## Приоритет источников

| Источник | Скорость | Надёжность | Ранний сигнал |
|----------|----------|------------|---------------|
| pump.fun WS | мгновенно | высокая | да — лучший |
| DexScreener | ~30 сек | высокая | нет |
| Twitter | 1-5 мин | средняя | иногда |

**Лучший сценарий:** Twitter сигнал → pump.fun запуск → DexScreener подтверждение

---

## Ссылки

- [[Architecture]] — как источники встроены в общую схему
- [[Components/AI Analyzer]] — что анализируем из этих данных
- [[Strategy/Filters and Security]] — что фильтруем до AI
