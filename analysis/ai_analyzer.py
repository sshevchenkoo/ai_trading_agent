import json
import anthropic

from config import settings
from sources.signal import TokenSignal
from sources.birdeye import get_token_analysis
from utils.logger import get_logger

log = get_logger("ai_analyzer")

# ─── Tool definitions ────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "search_twitter",
        "description": (
            "Search Twitter/X for recent tweets about a Solana token. "
            "Use this to gauge social sentiment, find KOL mentions, detect "
            "coordinated shilling, or check if hype is organic. "
            "Call it with the token ticker (e.g. '$BONK2') or a broader query."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Twitter search query, e.g. '$BONK2 solana' or '#BONK2'",
                },
                "max_results": {
                    "type": "integer",
                    "description": "How many tweets to fetch (10–50). Default 20.",
                    "default": 20,
                },
            },
            "required": ["query"],
        },
    },
]

# ─── System prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a Solana meme token trading analyst. Evaluate tokens for short-term potential (2x-10x within hours/days).

The token has already passed: rule filters, Birdeye security check, and Rugcheck.
Twitter profile verification and mention search have also been done — results are in the prompt.

You have a tool: search_twitter — use it ONLY if you need additional Twitter data beyond what's provided.

Analysis steps:
1. Read all the token data including Twitter verification result and pre-fetched mentions.
2. If Twitter mentions are missing or you want to search a specific angle, call search_twitter.
3. Evaluate: organic hype vs bots, narrative strength, timing, red flags.
4. Return your JSON verdict.

Return ONLY valid JSON at the end. No markdown, no extra text."""

# ─── Tool execution ───────────────────────────────────────────────────────────

async def _execute_tool(name: str, inputs: dict) -> str:
    if name == "search_twitter":
        return await _twitter_search(inputs["query"], inputs.get("max_results", 20))
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


# ─── Prompt builder ───────────────────────────────────────────────────────────

def _build_prompt(signal: TokenSignal, birdeye: dict) -> str:
    creator_note = ""
    if signal.creator_rug_count > 0:
        creator_note = f"\n- ⚠️ Creator previous rug pulls: {signal.creator_rug_count}"

    # Birdeye section
    birdeye_lines = []
    if birdeye:
        if birdeye.get("is_mintable"):
            birdeye_lines.append("  ⚠️ Mint authority NOT revoked")
        if birdeye.get("is_freezable"):
            birdeye_lines.append("  ⚠️ Freeze authority exists")
        if birdeye.get("lp_locked_pct"):
            birdeye_lines.append(f"  LP locked: {birdeye['lp_locked_pct']:.1f}%")
        if birdeye.get("creator_pct"):
            birdeye_lines.append(f"  Creator holds: {birdeye['creator_pct']:.1f}%")
        if birdeye.get("top10_holder_pct"):
            birdeye_lines.append(f"  Top 10 holders: {birdeye['top10_holder_pct']:.1f}%")
        if birdeye.get("unique_wallets_24h"):
            birdeye_lines.append(f"  Unique wallets 24h: {birdeye['unique_wallets_24h']}")
        if birdeye.get("price_change_1h"):
            birdeye_lines.append(f"  Price change 1h: {birdeye['price_change_1h']:+.1f}%")
        if birdeye.get("buy_24h") and birdeye.get("sell_24h"):
            birdeye_lines.append(f"  Buys/Sells 24h: {birdeye['buy_24h']}/{birdeye['sell_24h']}")
    birdeye_section = "\n".join(birdeye_lines) if birdeye_lines else "  not available"

    # Market section
    m = signal.market
    if m and m.sol_price_usd:
        market_section = (
            f"- SOL price: ${m.sol_price_usd:,.2f} ({m.sol_change_24h_pct:+.1f}% 24h)\n"
            f"- BTC trend: {m.btc_change_24h_pct:+.1f}% 24h\n"
            f"- Market mood: {m.market_trend}"
        )
    else:
        market_section = "- Market data unavailable"

    # Twitter profile verification section
    if signal.twitter_url:
        verified_str = (
            "✅ YES — contract address confirmed in profile"
            if signal.twitter_verified
            else "❌ NO — contract address NOT found in bio/tweets"
        )
        twitter_profile = (
            f"- Token Twitter: @{signal.twitter_username} "
            f"({signal.twitter_followers:,} followers)\n"
            f"- Contract verified in profile: {verified_str}"
        )
    else:
        twitter_profile = "- Token has no Twitter linked on pump.fun"

    # Pre-fetched tweets section
    if signal.tweets:
        tweet_lines = []
        for i, t in enumerate(signal.tweets[:15], 1):
            kol_tag = " [KOL]" if t.is_kol else ""
            tweet_lines.append(
                f"  {i}. @{t.author_name}{kol_tag} ({t.author_followers:,} followers) "
                f"[{t.likes}♥ {t.retweets}🔁]: {t.text[:200]}"
            )
        tweets_section = "\n".join(tweet_lines)
    else:
        tweets_section = "  No tweets found (Twitter may not be configured or no recent mentions)"

    return f"""Analyze this Solana token. Twitter data is pre-fetched below — only call search_twitter if you need an additional angle not covered. Then return your JSON verdict.

TOKEN:
- Symbol: ${signal.symbol}
- Name: {signal.name}
- Description: {signal.description[:300] if signal.description else "none"}
- Age: {signal.age_minutes} minutes old
- Market Cap: ${signal.market_cap_usd:,.0f}
- Liquidity: {signal.liquidity_sol:.1f} SOL
- Holders: {signal.holder_count}
- Top 10 holders: {signal.top10_holder_pct:.1f}% of supply
- Dev wallet sold: {signal.dev_wallet_sold}{creator_note}
- Buy/Sell ratio (1h): {signal.buy_count_1h}/{signal.sell_count_1h}

SECURITY & ON-CHAIN (Birdeye):
{birdeye_section}

TWITTER PROFILE:
{twitter_profile}

TWITTER MENTIONS (pre-fetched, {len(signal.tweets)} total, sorted by follower count):
{tweets_section}

MARKET CONTEXT:
{market_section}

Respond with this exact JSON:
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
        birdeye_data = await get_token_analysis(signal.token_address)

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        messages = [{"role": "user", "content": _build_prompt(signal, birdeye_data)}]

        # ── Tool use loop ──────────────────────────────────────────────────
        tool_calls = 0
        while True:
            response = client.messages.create(
                model="claude-opus-4-8",
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )

            if response.stop_reason == "tool_use":
                # Claude wants to call a tool — execute it and continue
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
                # Claude is done — extract JSON from the last text block
                raw = next(
                    (b.text for b in response.content if hasattr(b, "text")), ""
                ).strip()
                break

            else:
                log.error("unexpected_stop_reason", reason=response.stop_reason)
                return None

        # ── Parse result ───────────────────────────────────────────────────
        result = json.loads(raw)
        final_score = round(signal.rule_score * 0.4 + result["score"] * 0.6, 2)
        result["final_score"] = final_score

        log.info(
            "ai_analysis_done",
            symbol=signal.symbol,
            ai_score=result["score"],
            final_score=final_score,
            confidence=result["confidence"],
            risk=result["risk_level"],
            tool_calls=tool_calls,
            reasoning=result["reasoning"][:80] + "...",
        )
        return result

    except json.JSONDecodeError as e:
        log.error("ai_bad_json", symbol=signal.symbol, error=str(e))
        return None
    except Exception as e:
        log.error("ai_analyzer_failed", symbol=signal.symbol, error=str(e))
        return None
