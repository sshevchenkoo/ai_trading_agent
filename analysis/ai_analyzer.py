import asyncio
import json
import httpx
import anthropic

from config import settings
from sources.signal import TokenSignal
from utils.logger import get_logger

log = get_logger("ai_analyzer")

# ─── Models ──────────────────────────────────────────────────────────────────

SPECIALIST_MODEL = "claude-haiku-4-5-20251001"
MASTER_MODEL = "claude-opus-4-8"

# Pre-filter thresholds (deterministic — no Claude needed)
MIN_BUYS_1H = 5          # at least 5 buy txns in last hour
MIN_VOLUME_1H_USD = 500  # at least $500 volume in last hour

# ─── Tool definitions ────────────────────────────────────────────────────────

TWITTER_TOOL = {
    "name": "search_twitter",
    "description": (
        "Search Twitter/X for recent tweets. Use it twice: "
        "1) search '$SYMBOL' for token mentions and KOLs; "
        "2) if token name hints at a celebrity/meme/event, search that topic "
        "to find organic hype that existed BEFORE the token was created."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 20},
        },
        "required": ["query"],
    },
}

GMGN_TOOL = {
    "name": "get_gmgn",
    "description": "Fetch GMGN smart money data: smart wallet holders, dev behavior, rat traders, rug ratio.",
    "input_schema": {
        "type": "object",
        "properties": {
            "token_address": {"type": "string"},
        },
        "required": ["token_address"],
    },
}

# ─── Specialist system prompts ────────────────────────────────────────────────

TWITTER_SYSTEM = """You are a Twitter/social sentiment analyst for Solana meme tokens.

Search by ticker AND by name. If the name hints at a celebrity, meme, or event — search that topic to find organic pre-existing hype (strongest buy signal).

Return ONLY valid JSON:
{
  "sentiment": "bullish|bearish|neutral|mixed",
  "organic_score": <1-10, 1=all bots, 10=real community>,
  "kol_count": <accounts with >10k followers mentioning it>,
  "bot_likelihood": "low|medium|high",
  "narrative": "<key real-world topic driving interest, or null>",
  "pre_existing_hype": <true if topic was trending BEFORE the token>,
  "top_accounts": ["@handle (Xk): short quote"],
  "summary": "<2-3 sentences>"
}"""

GMGN_SYSTEM = """You are a GMGN smart money analyst for Solana meme tokens.

Fetch and interpret smart wallet data. Flag suspicious dev behavior and insider activity.

Return ONLY valid JSON:
{
  "smart_money_count": <number or null>,
  "dev_behavior": "healthy|suspicious|dumping|unknown",
  "rat_traders": "low|medium|high|unknown",
  "rug_risk": "low|medium|high|unknown",
  "top_10_holder_rate": <float 0-1 or null>,
  "red_flags": ["<flag>"],
  "summary": "<2-3 sentences>"
}"""

MASTER_SYSTEM = """You are the final decision-maker for Solana meme token trading.

You receive:
- DexScreener data: raw trading metrics (already passed: buys_1h >= 5, volume >= $500)
- Birdeye data: raw security data (already passed: no mint/freeze authority, creator <20%, top10 <70%)
- Twitter report: analyzed by specialist agent
- GMGN report: analyzed by specialist agent

The token already cleared hard security and activity filters. Your job: judge upside potential.

Score guide:
- 8-10 (strong buy): real volume + organic Twitter narrative + smart money present
- 7 (buy): 3 of 4 signals positive, manageable risk
- 5-6 (skip): mixed signals, not confident
- 1-4 (no): GMGN shows high rug risk OR dev dumping OR Twitter all bots

Return ONLY valid JSON:
{
  "score": <integer 1-10>,
  "confidence": "low|medium|high",
  "reasoning": "<2-3 sentences synthesizing all 4 data sources>",
  "risk_level": "low|medium|high|extreme",
  "suggested_position_sol": <float 0.05-0.5>,
  "red_flags": ["<flag>"],
  "narrative_strength": <integer 1-10>,
  "estimated_timeframe": "hours|1-3 days|week+"
}"""

# ─── Raw API fetchers (used by pre-filter and as tool backends) ───────────────

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
            return json.dumps({"error": "no trading pairs found", "pairs_count": 0})
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
            resp = await client.get(
                f"https://gmgn.ai/defi/quotation/v1/tokens/sol/{token_address}"
            )
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


async def _execute_tool(name: str, inputs: dict) -> str:
    if name == "search_twitter":
        return await _twitter_search(inputs["query"], inputs.get("max_results", 20))
    if name == "get_gmgn":
        return await _gmgn_fetch(inputs["token_address"])
    return json.dumps({"error": f"unknown tool: {name}"})


# ─── Stage 1: Python pre-filter (no Claude) ──────────────────────────────────

async def _prefilter(signal: TokenSignal) -> tuple[bool, dict, dict]:
    """
    Fetch DexScreener + Birdeye in parallel, apply hard deterministic rules.
    Rejects ~90% of tokens without spending a single Claude API call.
    Returns (passes, dex_data, birdeye_data).
    """
    dex_json, birdeye_json = await asyncio.gather(
        _dexscreener_fetch(signal.token_address),
        _birdeye_fetch(signal.token_address),
    )

    dex = json.loads(dex_json)
    birdeye = json.loads(birdeye_json)
    sym = signal.symbol

    # ── DexScreener checks ────────────────────────────────────────────────
    if dex.get("error") or not dex.get("pairs_count"):
        log.info("prefilter_reject", symbol=sym, reason="no_dex_pairs")
        return False, dex, birdeye

    buys_1h = int(dex.get("buys_1h") or 0)
    if buys_1h < MIN_BUYS_1H:
        log.info("prefilter_reject", symbol=sym, reason=f"buys_1h={buys_1h} < {MIN_BUYS_1H}")
        return False, dex, birdeye

    vol_1h = float(dex.get("volume_1h") or 0)
    if vol_1h < MIN_VOLUME_1H_USD:
        log.info("prefilter_reject", symbol=sym, reason=f"volume_1h=${vol_1h:.0f} < ${MIN_VOLUME_1H_USD}")
        return False, dex, birdeye

    # ── Birdeye security checks ───────────────────────────────────────────
    if birdeye.get("is_mintable"):
        log.info("prefilter_reject", symbol=sym, reason="mint_authority_not_revoked")
        return False, dex, birdeye

    if birdeye.get("is_freezable"):
        log.info("prefilter_reject", symbol=sym, reason="freeze_authority_exists")
        return False, dex, birdeye

    creator_pct = float(birdeye.get("creator_pct") or 0)
    if creator_pct > 20:
        log.info("prefilter_reject", symbol=sym, reason=f"creator_{creator_pct:.0f}pct")
        return False, dex, birdeye

    top10_pct = float(birdeye.get("top10_holder_pct") or 0)
    if top10_pct > 70:
        log.info("prefilter_reject", symbol=sym, reason=f"top10_{top10_pct:.0f}pct")
        return False, dex, birdeye

    lp_pct = birdeye.get("lp_locked_pct")
    if lp_pct is not None and float(lp_pct) < 10:
        log.info("prefilter_reject", symbol=sym, reason=f"lp_locked_{lp_pct:.0f}pct")
        return False, dex, birdeye

    log.info(
        "prefilter_pass",
        symbol=sym,
        buys_1h=buys_1h,
        volume_1h=round(vol_1h),
        creator_pct=creator_pct,
        top10_pct=top10_pct,
    )
    return True, dex, birdeye


# ─── Stage 2: Specialist agents (Haiku, parallel) ────────────────────────────

async def _run_specialist(
    name: str,
    system: str,
    tool: dict,
    token_address: str,
    symbol: str,
    token_name: str,
    description: str,
) -> dict:
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    user_msg = (
        f"Token: ${symbol} ({token_name})\n"
        f"Address: {token_address}\n"
        f"Description: {description[:200] if description else 'none'}\n\n"
        f"Use your tool to investigate and return your JSON report."
    )

    messages = [{"role": "user", "content": user_msg}]
    raw = ""

    for _ in range(4):  # max 4 tool calls per specialist
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
                    log.info("specialist_tool_call", agent=name, symbol=symbol)
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


# ─── Stage 3: Master agent (Opus) ────────────────────────────────────────────

async def _master_agent(signal: TokenSignal, reports: dict) -> dict:
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    m = signal.market
    market_line = (
        f"SOL ${m.sol_price_usd:,.2f} ({m.sol_change_24h_pct:+.1f}% 24h), "
        f"BTC {m.btc_change_24h_pct:+.1f}% 24h — {m.market_trend}"
        if m and m.sol_price_usd else "unavailable"
    )

    user_msg = f"""Make a final verdict on this Solana token.

TOKEN: ${signal.symbol} ({signal.name})
Address: {signal.token_address}
Age: {signal.age_minutes} min | Market Cap: ${signal.market_cap_usd:,.0f}
Twitter: {signal.twitter_url or "none"} | Market: {market_line}

━━━ DEXSCREENER (raw data, already passed volume filter) ━━━
{json.dumps(reports["dexscreener"], indent=2)}

━━━ BIRDEYE (raw data, already passed security filter) ━━━
{json.dumps(reports["birdeye"], indent=2)}

━━━ TWITTER REPORT (specialist analysis) ━━━
{json.dumps(reports["twitter"], indent=2)}

━━━ GMGN REPORT (specialist analysis) ━━━
{json.dumps(reports["gmgn"], indent=2)}

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
        # ── Stage 1: Python pre-filter (DexScreener + Birdeye, no Claude) ──
        passes, dex_data, birdeye_data = await _prefilter(signal)
        if not passes:
            return None  # rejected — 0 Claude API calls spent

        # ── Stage 2: Specialist agents in parallel (Haiku) ─────────────────
        log.info("specialists_start", symbol=signal.symbol)

        twitter_r, gmgn_r = await asyncio.gather(
            _run_specialist(
                "twitter", TWITTER_SYSTEM, TWITTER_TOOL,
                signal.token_address, signal.symbol, signal.name, signal.description,
            ),
            _run_specialist(
                "gmgn", GMGN_SYSTEM, GMGN_TOOL,
                signal.token_address, signal.symbol, signal.name, signal.description,
            ),
            return_exceptions=True,
        )

        def _safe(r, name):
            if isinstance(r, Exception):
                log.warning("specialist_exception", agent=name, error=str(r))
                return {"error": str(r), "summary": "agent failed"}
            return r

        reports = {
            "dexscreener": dex_data,
            "birdeye": birdeye_data,
            "twitter": _safe(twitter_r, "twitter"),
            "gmgn": _safe(gmgn_r, "gmgn"),
        }

        log.info(
            "specialists_done",
            symbol=signal.symbol,
            twitter_ok="error" not in reports["twitter"],
            gmgn_ok="error" not in reports["gmgn"],
        )

        # ── Stage 3: Master agent (Opus) makes final verdict ────────────────
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
