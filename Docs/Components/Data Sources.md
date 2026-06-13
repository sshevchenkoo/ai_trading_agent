# Data Sources

Three independent signal sources running in parallel, feeding data into the [[Architecture#Signal Aggregator|Signal Aggregator]].

---

## 1. pump.fun WebSocket

**What it provides:** every new Solana token the moment it launches, before it appears on DexScreener.

**Endpoint:**
```
wss://pumpportal.fun/api/data
```

**Subscribing to new tokens:**
```python
import websockets
import json

async def listen_pumpfun():
    uri = "wss://pumpportal.fun/api/data"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({
            "method": "subscribeNewToken"
        }))
        async for message in ws:
            data = json.loads(message)
            await handle_new_token(data)
```

**Event structure:**
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

**Notes:**
- pump.fun tokens start with ~30 SOL virtual liquidity
- A token graduates to Raydium only after reaching ~$69k market cap
- Most tokens die before graduating — strong filters are essential

---

## 2. DexScreener API

**What it provides:** new trading pairs on Solana (beyond pump.fun), price, volume, liquidity, transactions.

**Endpoints:**
```
# New pairs (polled every 5 min)
GET https://api.dexscreener.com/token-profiles/latest/v1

# Data for a specific token
GET https://api.dexscreener.com/latest/dex/tokens/{address}

# Search by ticker
GET https://api.dexscreener.com/latest/dex/search?q={symbol}
```

**Example token response:**
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

**Key fields:**
- `liquidity.quote` — liquidity in SOL (minimum 50 SOL)
- `txns.h1.buys / sells` — buy-to-sell ratio
- `priceChange.h1` — hourly price change
- `pairCreatedAt` — pair age

---

## 3. Twitter / X API

**What it provides:** token mentions from real accounts and KOLs before the price moves.

**Used:** X API v2, Recent Search

```python
import tweepy

client = tweepy.Client(bearer_token=BEARER_TOKEN)

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

**Filtered Stream (for real-time monitoring):**
```python
rules = [
    {"value": "pump.fun lang:en", "tag": "pumpfun_mentions"},
    {"value": "$SOL new token lang:en", "tag": "new_tokens"},
]
```

**Tweet scoring metrics:**
```python
tweet_score = {
    "author_followers": tweet.author.public_metrics["followers_count"],
    "likes": tweet.public_metrics["like_count"],
    "retweets": tweet.public_metrics["retweet_count"],
    "is_kol": tweet.author_id in KOL_WHITELIST,
}
```

**KOL Whitelist** — list of known crypto influencers whose mentions carry high signal weight.

---

## Source Priority

| Source | Speed | Reliability | Early signal |
|--------|-------|-------------|--------------|
| pump.fun WS | instant | high | yes — best |
| DexScreener | ~30 sec | high | no |
| Twitter | 1–5 min | medium | sometimes |

**Best scenario:** Twitter signal → pump.fun launch → DexScreener confirmation

---

## Links

- [[Architecture]] — how sources fit into the overall system
- [[Components/AI Analyzer]] — what is analysed from these sources
- [[Strategy/Filters and Security]] — what is filtered before AI
