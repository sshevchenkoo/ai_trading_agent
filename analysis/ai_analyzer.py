import json
import httpx
import anthropic

from config import settings
from sources.signal import TokenSignal
from utils.logger import get_logger

log = get_logger("ai_analyzer")

# ─── Tool definitions ────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "search_twitter",
        "description": (
            "Search Twitter/X for recent tweets about a topic or token. "
            "Use to gauge social sentiment, find KOL mentions, detect organic hype. "
            "If the token name looks like a celebrity/meme/trending topic, search that "
            "topic to find hype that existed BEFORE the token was created — strongest buy signal."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query, e.g. '$BONK solana' or 'barron trump dog'",
                },
                "max_results": {
                    "type": "integer",
                    "description": "10–50, default 20",
                    "default": 20,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_dexscreener",
        "description": (
            "Fetch DexScreener trading data for a Solana token: price, 24h/1h volume, "
            "liquidity, buy/sell counts, price change %. "
            "Call this FIRST to check if real trading is happening."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "token_address": {
                    "type": "string",
                    "description": "Solana token contract address",
                },
            },
            "required": ["token_address"],
        },
    },
    {
        "name": "get_birdeye",
        "description": (
            "Fetch Birdeye security and holder analytics: mint/freeze authority status, "
            "LP locked %, creator holdings %, top-10 holder concentration, unique wallets, "
            "buy/sell counts. Essential for rug detection."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "token_address": {
                    "type": "string",
                    "description": "Solana token contract address",
                },
            },
            "required": ["token_address"],
        },
    },
    {
        "name": "get_gmgn",
        "description": (
            "Fetch GMGN smart money analytics: smart wallet holder count, dev behavior "
            "(burn ratio, close ratio), rat trader rate, rug ratio, top-10 holder rate. "
            "Use to detect whale accumulation, insider activity, or dev dumps."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "token_address": {
                    "type": "string",
                    "description": "Solana token contract address",
                },
            },
            "required": ["token_address"],
        },
    },
]

# ─── System prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a Solana meme token trading analyst. Find tokens with 2x-10x potential within hours/days.

You receive basic token info (address, name, symbol, description, age, market cap).
Investigate using your tools, then return a buy/no-buy verdict.

TOOL USAGE STRATEGY:
1. get_dexscreener — call ALWAYS first. If volume is zero or no pairs exist → reject immediately, skip other tools.
2. get_birdeye — call ALWAYS second. Hard reject if: mint authority not revoked, freeze authority exists, creator >20%, top-10 >70%.
3. search_twitter — call if: token has social links OR name hints at a celebrity/meme/trending topic.
   For meme names: search the TOPIC (not the ticker) to find organic pre-existing hype.
   Example: token "BarronDog" → search "barron trump dog"; "GrokAI" → search "grok ai announcement"
4. get_gmgn — call if DexScreener + Birdeye look promising. Confirms smart money is in.

HARD REJECT (score 1-2, no buy):
- No trading pairs or zero volume on DexScreener
- Mint authority not revoked OR freeze authority exists
- Creator holds >20% OR top-10 holders own >70%
- GMGN shows high rug_ratio or dev immediately closed position

STRONG BUY signals (score 8-10):
- Real volume, healthy buy/sell ratio, organic buys
- LP locked, security clean
- Strong Twitter narrative + organic community (not bots)
- Smart money wallets holding according to GMGN
- Token name tied to trending real-world event

Return ONLY valid JSON at the end. No markdown, no extra text."""

# ─── Tool execution ───────────────────────────────────────────────────────────

async def _execute_tool(name: str, inputs: dict) -> str:
    if name == "search_twitter":
        return await _twitter_search(inputs["query"], inputs.get("max_results", 20))
    if name == "get_dexscreener":
        return await _dexscreener_fetch(inputs["token_address"])
    if name == "get_birdeye":
        return await _birdeye_fetch(inputs["token_address"])
    if name == "get_gmgn":
        return await _gmgn_fetch(inputs["token_address"])
    return json.dumps({"error": f"unknown tool: {name}"})


async def _twitter_search(query: str, max_results: int) -> str:
    if not settings.twitter_bearer_token:
        return json.dumps({
            "error": "Twitter API not configured (TWITTER_BEARER_TOKEN not set)",
            "tweets": [],
        })

    try:
        import tweepy

        client = tweepy.Client(
            bearer_token=settings.twitter_bearer_token,
            wait_on_rate_limit=False,
        )
        safe_query = f"{query} lang:en -is:retweet"
        response = client.search_recent_tweets(
            query=safe_query,
            max_results=min(max(max_results, 10), 50),
            tweet_fields=["text", "public_metrics", "author_id", "created_at"],
            expansions=["author_id"],
            user_fields=["username", "public_metrics"],
        )

        users = {}
        if response.includes and response.includes.get("users"):
            for u in response.includes["users"]:
                users[u.id] = {
                    "username": u.username,
                    "followers": u.public_metrics["followers_count"],
                }

        tweets = []
        for tweet in response.data or []:
            author = users.get(tweet.author_id, {})
            tweets.append({
                "text": tweet.text[:280],
                "author": author.get("username", "unknown"),
                "followers": author.get("followers", 0),
                "likes": tweet.public_metrics["like_count"],
                "retweets": tweet.public_metrics["retweet_count"],
            })

        log.info("twitter_tool_called", query=query, results=len(tweets))
        return json.dumps({"tweets": tweets, "total": len(tweets)})

    except Exception as e:
        log.warning("twitter_tool_failed", query=query, error=str(e))
        return json.dumps({"error": str(e), "tweets": []})


async def _dexscreener_fetch(token_address: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
            )
            resp.raise_for_status()
            data = resp.json()

        pairs = data.get("pairs") or []
        if not pairs:
            return json.dumps({"error": "no trading pairs found on DexScreener", "pairs": 0})

        pair = max(pairs, key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0))

        result = {
            "pairs_count": len(pairs),
            "dex": pair.get("dexId"),
            "price_usd": pair.get("priceUsd"),
            "market_cap_usd": pair.get("marketCap"),
            "liquidity_usd": pair.get("liquidity", {}).get("usd"),
            "volume_5m": pair.get("volume", {}).get("m5"),
            "volume_1h": pair.get("volume", {}).get("h1"),
            "volume_24h": pair.get("volume", {}).get("h24"),
            "price_change_5m_pct": pair.get("priceChange", {}).get("m5"),
            "price_change_1h_pct": pair.get("priceChange", {}).get("h1"),
            "price_change_24h_pct": pair.get("priceChange", {}).get("h24"),
            "buys_5m": pair.get("txns", {}).get("m5", {}).get("buys"),
            "sells_5m": pair.get("txns", {}).get("m5", {}).get("sells"),
            "buys_1h": pair.get("txns", {}).get("h1", {}).get("buys"),
            "sells_1h": pair.get("txns", {}).get("h1", {}).get("sells"),
            "pair_age_ms": pair.get("pairCreatedAt"),
        }

        log.info("dexscreener_tool_called", token=token_address[:8], pairs=len(pairs))
        return json.dumps(result)

    except Exception as e:
        log.warning("dexscreener_tool_failed", token=token_address[:8], error=str(e))
        return json.dumps({"error": str(e)})


async def _birdeye_fetch(token_address: str) -> str:
    from sources.birdeye import get_token_analysis
    try:
        data = await get_token_analysis(token_address)
        if not data:
            return json.dumps({
                "error": "Birdeye not available (BIRDEYE_API_KEY not set or request failed)"
            })
        log.info("birdeye_tool_called", token=token_address[:8])
        return json.dumps(data)
    except Exception as e:
        log.warning("birdeye_tool_failed", token=token_address[:8], error=str(e))
        return json.dumps({"error": str(e)})


async def _gmgn_fetch(token_address: str) -> str:
    try:
        headers = {
            "referer": "https://gmgn.ai/",
            "user-agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        }
        async with httpx.AsyncClient(timeout=10, headers=headers) as client:
            resp = await client.get(
                f"https://gmgn.ai/defi/quotation/v1/tokens/sol/{token_address}"
            )
            resp.raise_for_status()
            data = resp.json()

        token = (data.get("data") or {}).get("token") or {}
        if not token:
            return json.dumps({"error": "GMGN returned empty token data"})

        result = {
            "smart_money_holders": token.get("smart_money"),
            "dev_token_burn_ratio": token.get("dev_token_burn_ratio"),
            "dev_close_ratio": token.get("dev_close_ratio"),
            "rat_trader_amount_rate": token.get("rat_trader_amount_rate"),
            "holder_count": token.get("holder_count"),
            "top_10_holder_rate": token.get("top_10_holder_rate"),
            "rug_ratio": token.get("rug_ratio"),
            "is_show_alert": token.get("is_show_alert"),
            "alert_reason": token.get("alert_reason"),
            "launchpad": token.get("launchpad"),
        }

        log.info("gmgn_tool_called", token=token_address[:8])
        return json.dumps(result)

    except Exception as e:
        log.warning("gmgn_tool_failed", token=token_address[:8], error=str(e))
        return json.dumps({"error": str(e)})


# ─── Prompt builder ───────────────────────────────────────────────────────────

def _build_prompt(signal: TokenSignal) -> str:
    m = signal.market
    market_section = (
        f"SOL ${m.sol_price_usd:,.2f} ({m.sol_change_24h_pct:+.1f}% 24h), "
        f"BTC {m.btc_change_24h_pct:+.1f}% 24h — {m.market_trend}"
        if m and m.sol_price_usd else "unavailable"
    )

    return f"""Analyze this Solana token. Use your tools to investigate, then return a JSON verdict.

TOKEN:
- Address: {signal.token_address}
- Symbol: ${signal.symbol}
- Name: {signal.name}
- Description: {signal.description[:300] if signal.description else "none"}
- Age: {signal.age_minutes} min since pair creation
- Market Cap: ${signal.market_cap_usd:,.0f}
- Source: {signal.source}
- Twitter: {signal.twitter_url or "none"}
- Telegram: {signal.telegram_url or "none"}
- Website: {signal.website_url or "none"}

MARKET: {market_section}

Start with get_dexscreener, then get_birdeye, then Twitter if the name suggests a meme/narrative or social links exist, then GMGN if everything looks promising.

Return this exact JSON:
{{
  "score": <integer 1-10, where 7+ means buy>,
  "confidence": <"low" | "medium" | "high">,
  "reasoning": "<2-3 sentences explaining your decision>",
  "risk_level": <"low" | "medium" | "high" | "extreme">,
  "suggested_position_sol": <float 0.05-0.5>,
  "red_flags": ["<flag1>", "<flag2>"],
  "narrative_strength": <integer 1-10>,
  "estimated_timeframe": <"hours" | "1-3 days" | "week+">
}}"""


# ─── Main entry point ─────────────────────────────────────────────────────────

async def analyze_token(signal: TokenSignal) -> dict | None:
    if not settings.anthropic_api_key:
        log.warning("ai_analyzer_skipped", reason="ANTHROPIC_API_KEY not set")
        return None

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        messages = [{"role": "user", "content": _build_prompt(signal)}]

        # ── Tool use loop ──────────────────────────────────────────────────
        tool_calls = 0
        raw = ""
        while True:
            response = client.messages.create(
                model="claude-opus-4-8",
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        tool_calls += 1
                        log.info(
                            "claude_tool_call",
                            tool=block.name,
                            inputs=block.input,
                            symbol=signal.symbol,
                        )
                        result = await _execute_tool(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })

                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})

            elif response.stop_reason == "end_turn":
                raw = next(
                    (b.text for b in response.content if hasattr(b, "text")), ""
                ).strip()
                break

            else:
                log.error("unexpected_stop_reason", reason=response.stop_reason)
                return None

        # ── Parse result ───────────────────────────────────────────────────
        result = json.loads(raw)
        result["final_score"] = result["score"]

        log.info(
            "ai_analysis_done",
            symbol=signal.symbol,
            score=result["score"],
            confidence=result["confidence"],
            risk=result["risk_level"],
            tool_calls=tool_calls,
            reasoning=result["reasoning"][:80] + "...",
        )
        return result

    except json.JSONDecodeError as e:
        log.error("ai_bad_json", symbol=signal.symbol, error=str(e), raw=raw[:200])
        return None
    except Exception as e:
        log.error("ai_analyzer_failed", symbol=signal.symbol, error=str(e))
        return None
