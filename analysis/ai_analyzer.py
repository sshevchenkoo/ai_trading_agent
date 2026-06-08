import asyncio
import json
import httpx
import anthropic

from config import settings
from sources.signal import TokenSignal
from utils.logger import get_logger

log = get_logger("ai_analyzer")

# ─── Models ──────────────────────────────────────────────────────────────────

SPECIALIST_MODEL = "claude-haiku-4-5-20251001"  # fast + cheap per specialist
MASTER_MODEL = "claude-opus-4-8"                 # best model for final verdict

# ─── Tool definitions (one per specialist) ───────────────────────────────────

TWITTER_TOOL = {
    "name": "search_twitter",
    "description": (
        "Search Twitter/X for recent tweets. Use it twice: "
        "1) search '$SYMBOL' to find token mentions and KOLs; "
        "2) if token name looks like a celebrity/meme/event, search that topic "
        "to find organic hype that existed BEFORE the token was created."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "max_results": {"type": "integer", "default": 20},
        },
        "required": ["query"],
    },
}

DEXSCREENER_TOOL = {
    "name": "get_dexscreener",
    "description": "Fetch DexScreener trading data for a Solana token: price, volume, liquidity, buy/sell counts.",
    "input_schema": {
        "type": "object",
        "properties": {
            "token_address": {"type": "string", "description": "Solana token contract address"},
        },
        "required": ["token_address"],
    },
}

BIRDEYE_TOOL = {
    "name": "get_birdeye",
    "description": "Fetch Birdeye security and holder analytics: mint/freeze authority, LP locked %, holder concentration.",
    "input_schema": {
        "type": "object",
        "properties": {
            "token_address": {"type": "string", "description": "Solana token contract address"},
        },
        "required": ["token_address"],
    },
}

GMGN_TOOL = {
    "name": "get_gmgn",
    "description": "Fetch GMGN smart money data: smart wallet holders, dev behavior, rat traders, rug ratio.",
    "input_schema": {
        "type": "object",
        "properties": {
            "token_address": {"type": "string", "description": "Solana token contract address"},
        },
        "required": ["token_address"],
    },
}

# ─── Specialist system prompts ────────────────────────────────────────────────

TWITTER_SYSTEM = """You are a Twitter/social sentiment analyst for Solana meme tokens.

Search for the token by ticker AND by name (if the name hints at a celebrity, meme, or event — search that topic to find organic pre-existing hype, the strongest buy signal).

Return ONLY valid JSON:
{
  "sentiment": "bullish|bearish|neutral|mixed",
  "organic_score": <1-10, 1=all bots, 10=real community>,
  "kol_count": <number of accounts with >10k followers mentioning it>,
  "bot_likelihood": "low|medium|high",
  "narrative": "<key narrative or topic driving interest, or null>",
  "top_accounts": ["@handle (Xk followers): short quote"],
  "pre_existing_hype": <true if the topic was trending BEFORE the token>,
  "summary": "<2-3 sentences with your analysis>"
}"""

DEXSCREENER_SYSTEM = """You are a DexScreener trading analyst for Solana meme tokens.

Fetch trading data and assess whether real buying pressure exists. Zero volume = ghost token = reject.

Return ONLY valid JSON:
{
  "has_trading": <true/false>,
  "volume_1h_usd": <number or null>,
  "buy_sell_ratio_1h": <buys/sells, null if no data>,
  "price_change_1h_pct": <float or null>,
  "liquidity_usd": <number or null>,
  "market_cap_usd": <number or null>,
  "red_flags": ["<flag>"],
  "summary": "<2-3 sentences with your analysis>"
}"""

BIRDEYE_SYSTEM = """You are a Birdeye security analyst for Solana meme tokens.

Check ALL security flags and holder distribution. Be strict — any single hard flag = fail.

Hard fail (security_pass=false) if ANY of:
- Mint authority not revoked
- Freeze authority exists
- Creator holds >20%
- Top 10 holders own >70%
- LP locked <10%

Return ONLY valid JSON:
{
  "security_pass": <true/false>,
  "mint_revoked": <true/false>,
  "freeze_revoked": <true/false>,
  "lp_locked_pct": <float or null>,
  "creator_pct": <float or null>,
  "top10_pct": <float or null>,
  "holder_count": <number or null>,
  "red_flags": ["<flag>"],
  "summary": "<2-3 sentences with your analysis>"
}"""

GMGN_SYSTEM = """You are a GMGN smart money analyst for Solana meme tokens.

Check for smart wallet accumulation, dev behavior, and insider activity.

Return ONLY valid JSON:
{
  "smart_money_count": <number or null>,
  "dev_behavior": "healthy|suspicious|dumping|unknown",
  "rat_traders": "low|medium|high|unknown",
  "rug_risk": "low|medium|high|unknown",
  "top10_holder_rate": <float 0-1 or null>,
  "red_flags": ["<flag>"],
  "summary": "<2-3 sentences with your analysis>"
}"""

MASTER_SYSTEM = """You are the final decision-maker for Solana meme token trading. You receive reports from 4 specialist agents.

Decision rules:
- If Birdeye security_pass=false → ALWAYS reject (score 1-3)
- If DexScreener has_trading=false → reject (score 1-3)
- Strong buy (8-10): clean security + real volume + organic Twitter hype + smart money present
- Good buy (7): 3 of 4 signals positive
- Neutral (5-6): mixed signals, wait or small position
- Reject (1-4): any hard fail OR more than 2 red flags across reports

Return ONLY valid JSON:
{
  "score": <integer 1-10, 7+ = buy>,
  "confidence": "low|medium|high",
  "reasoning": "<2-3 sentences synthesizing all 4 reports>",
  "risk_level": "low|medium|high|extreme",
  "suggested_position_sol": <float 0.05-0.5>,
  "red_flags": ["<combined critical flags>"],
  "narrative_strength": <1-10>,
  "estimated_timeframe": "hours|1-3 days|week+"
}"""

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
        return json.dumps({"error": "TWITTER_BEARER_TOKEN not set", "tweets": []})
    try:
        import tweepy
        client = tweepy.Client(bearer_token=settings.twitter_bearer_token, wait_on_rate_limit=False)
        response = client.search_recent_tweets(
            query=f"{query} lang:en -is:retweet",
            max_results=min(max(max_results, 10), 50),
            tweet_fields=["text", "public_metrics", "author_id"],
            expansions=["author_id"],
            user_fields=["username", "public_metrics"],
        )
        users = {}
        if response.includes and response.includes.get("users"):
            for u in response.includes["users"]:
                users[u.id] = {"username": u.username, "followers": u.public_metrics["followers_count"]}
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
        return json.dumps({"tweets": tweets, "total": len(tweets)})
    except Exception as e:
        return json.dumps({"error": str(e), "tweets": []})


async def _dexscreener_fetch(token_address: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"https://api.dexscreener.com/latest/dex/tokens/{token_address}")
            resp.raise_for_status()
            data = resp.json()
        pairs = data.get("pairs") or []
        if not pairs:
            return json.dumps({"error": "no trading pairs found", "pairs": 0})
        pair = max(pairs, key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0))
        return json.dumps({
            "pairs_count": len(pairs),
            "price_usd": pair.get("priceUsd"),
            "market_cap_usd": pair.get("marketCap"),
            "liquidity_usd": pair.get("liquidity", {}).get("usd"),
            "volume_5m": pair.get("volume", {}).get("m5"),
            "volume_1h": pair.get("volume", {}).get("h1"),
            "volume_24h": pair.get("volume", {}).get("h24"),
            "price_change_5m_pct": pair.get("priceChange", {}).get("m5"),
            "price_change_1h_pct": pair.get("priceChange", {}).get("h1"),
            "buys_5m": pair.get("txns", {}).get("m5", {}).get("buys"),
            "sells_5m": pair.get("txns", {}).get("m5", {}).get("sells"),
            "buys_1h": pair.get("txns", {}).get("h1", {}).get("buys"),
            "sells_1h": pair.get("txns", {}).get("h1", {}).get("sells"),
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


async def _birdeye_fetch(token_address: str) -> str:
    from sources.birdeye import get_token_analysis
    try:
        data = await get_token_analysis(token_address)
        if not data:
            return json.dumps({"error": "Birdeye not available (BIRDEYE_API_KEY not set)"})
        return json.dumps(data)
    except Exception as e:
        return json.dumps({"error": str(e)})


async def _gmgn_fetch(token_address: str) -> str:
    try:
        headers = {
            "referer": "https://gmgn.ai/",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        }
        async with httpx.AsyncClient(timeout=10, headers=headers) as client:
            resp = await client.get(f"https://gmgn.ai/defi/quotation/v1/tokens/sol/{token_address}")
            resp.raise_for_status()
            data = resp.json()
        token = (data.get("data") or {}).get("token") or {}
        if not token:
            return json.dumps({"error": "GMGN returned empty data"})
        return json.dumps({
            "smart_money": token.get("smart_money"),
            "dev_token_burn_ratio": token.get("dev_token_burn_ratio"),
            "dev_close_ratio": token.get("dev_close_ratio"),
            "rat_trader_amount_rate": token.get("rat_trader_amount_rate"),
            "holder_count": token.get("holder_count"),
            "top_10_holder_rate": token.get("top_10_holder_rate"),
            "rug_ratio": token.get("rug_ratio"),
            "is_show_alert": token.get("is_show_alert"),
            "alert_reason": token.get("alert_reason"),
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


# ─── Specialist agent runner ──────────────────────────────────────────────────

async def _run_specialist(
    name: str,
    system: str,
    tool: dict,
    token_address: str,
    symbol: str,
    token_name: str,
    description: str,
) -> dict:
    """Run one specialist Claude agent with a single tool. Returns its JSON report."""
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    user_msg = (
        f"Token: ${symbol} ({token_name})\n"
        f"Address: {token_address}\n"
        f"Description: {description[:200] if description else 'none'}\n\n"
        f"Use your tool to investigate this token and return your JSON report."
    )

    messages = [{"role": "user", "content": user_msg}]
    max_loops = 4
    raw = ""

    for _ in range(max_loops):
        response = client.messages.create(
            model=SPECIALIST_MODEL,
            max_tokens=512,
            system=system,
            tools=[tool],
            messages=messages,
        )

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    log.info("specialist_tool_call", agent=name, tool=block.name, symbol=symbol)
                    result = await _execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

        elif response.stop_reason == "end_turn":
            raw = next((b.text for b in response.content if hasattr(b, "text")), "").strip()
            break
        else:
            break

    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        log.warning("specialist_bad_json", agent=name, symbol=symbol, raw=raw[:100])
        return {"error": f"{name} returned invalid JSON", "summary": "data unavailable"}


# ─── Master agent ─────────────────────────────────────────────────────────────

async def _master_agent(signal: TokenSignal, reports: dict) -> dict:
    """Receives all 4 specialist reports and makes the final buy/no-buy verdict."""
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    m = signal.market
    market_line = (
        f"SOL ${m.sol_price_usd:,.2f} ({m.sol_change_24h_pct:+.1f}% 24h), "
        f"BTC {m.btc_change_24h_pct:+.1f}% 24h — {m.market_trend}"
        if m and m.sol_price_usd else "unavailable"
    )

    user_msg = f"""Make a final verdict on this Solana token based on the 4 specialist reports below.

TOKEN: ${signal.symbol} ({signal.name}) — mcap ${signal.market_cap_usd:,.0f} — age {signal.age_minutes} min
Source: {signal.source} | Twitter: {signal.twitter_url or "none"} | Market: {market_line}

━━━ TWITTER REPORT ━━━
{json.dumps(reports.get("twitter", {"error": "unavailable"}), indent=2)}

━━━ DEXSCREENER REPORT ━━━
{json.dumps(reports.get("dexscreener", {"error": "unavailable"}), indent=2)}

━━━ BIRDEYE REPORT ━━━
{json.dumps(reports.get("birdeye", {"error": "unavailable"}), indent=2)}

━━━ GMGN REPORT ━━━
{json.dumps(reports.get("gmgn", {"error": "unavailable"}), indent=2)}

Return your JSON verdict."""

    response = client.messages.create(
        model=MASTER_MODEL,
        max_tokens=1024,
        system=MASTER_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )

    raw = next((b.text for b in response.content if hasattr(b, "text")), "").strip()
    return json.loads(raw)


# ─── Main entry point ─────────────────────────────────────────────────────────

async def analyze_token(signal: TokenSignal) -> dict | None:
    if not settings.anthropic_api_key:
        log.warning("ai_analyzer_skipped", reason="ANTHROPIC_API_KEY not set")
        return None

    try:
        # ── Run all 4 specialist agents in parallel ────────────────────────
        log.info("multi_agent_start", symbol=signal.symbol, address=signal.token_address[:8])

        twitter_task = _run_specialist(
            "twitter", TWITTER_SYSTEM, TWITTER_TOOL,
            signal.token_address, signal.symbol, signal.name, signal.description,
        )
        dex_task = _run_specialist(
            "dexscreener", DEXSCREENER_SYSTEM, DEXSCREENER_TOOL,
            signal.token_address, signal.symbol, signal.name, signal.description,
        )
        birdeye_task = _run_specialist(
            "birdeye", BIRDEYE_SYSTEM, BIRDEYE_TOOL,
            signal.token_address, signal.symbol, signal.name, signal.description,
        )
        gmgn_task = _run_specialist(
            "gmgn", GMGN_SYSTEM, GMGN_TOOL,
            signal.token_address, signal.symbol, signal.name, signal.description,
        )

        twitter_r, dex_r, birdeye_r, gmgn_r = await asyncio.gather(
            twitter_task, dex_task, birdeye_task, gmgn_task,
            return_exceptions=True,
        )

        # Replace exceptions with error placeholders
        def _safe(r, name):
            if isinstance(r, Exception):
                log.warning("specialist_failed", agent=name, error=str(r))
                return {"error": str(r), "summary": "agent failed"}
            return r

        reports = {
            "twitter": _safe(twitter_r, "twitter"),
            "dexscreener": _safe(dex_r, "dexscreener"),
            "birdeye": _safe(birdeye_r, "birdeye"),
            "gmgn": _safe(gmgn_r, "gmgn"),
        }

        log.info(
            "specialists_done",
            symbol=signal.symbol,
            twitter_ok="error" not in reports["twitter"],
            dex_ok="error" not in reports["dexscreener"],
            birdeye_ok="error" not in reports["birdeye"],
            gmgn_ok="error" not in reports["gmgn"],
        )

        # ── Master agent makes final verdict ───────────────────────────────
        result = await _master_agent(signal, reports)
        result["final_score"] = result["score"]

        log.info(
            "ai_analysis_done",
            symbol=signal.symbol,
            score=result["score"],
            confidence=result["confidence"],
            risk=result["risk_level"],
            reasoning=result["reasoning"][:80] + "...",
        )
        return result

    except json.JSONDecodeError as e:
        log.error("master_bad_json", symbol=signal.symbol, error=str(e))
        return None
    except Exception as e:
        log.error("ai_analyzer_failed", symbol=signal.symbol, error=str(e))
        return None
