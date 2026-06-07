import json
import anthropic

from config import settings
from sources.signal import TokenSignal
from utils.logger import get_logger

log = get_logger("ai_analyzer")

SYSTEM_PROMPT = """You are a Solana meme token analyst. Your job is to evaluate tokens for short-term trading potential (2x-10x within hours/days).

Your analysis criteria:
1. Tweet quality — real organic interest or bots/fake hype?
2. Narrative strength — does the token have a clear story or meme?
3. Timing — early hype (good) or already peaked (bad)?
4. Red flags — scam signs in name, description, creator history
5. Potential — similarity to past successful tokens

Return ONLY valid JSON. No markdown, no extra text, no explanation outside JSON."""


def _build_prompt(signal: TokenSignal) -> str:
    tweets_section = "none"
    if signal.tweet_texts:
        tweets_section = "\n".join(
            f"  - {t[:200]}" for t in signal.tweet_texts[:5]
        )

    kol_section = ", ".join(signal.kol_mentions) if signal.kol_mentions else "none"

    return f"""Analyze this Solana token for short-term trading potential:

TOKEN:
- Symbol: ${signal.symbol}
- Name: {signal.name}
- Description: {signal.description[:300] if signal.description else "none"}
- Age: {signal.age_minutes} minutes old
- Market Cap: ${signal.market_cap_usd:,.0f}
- Liquidity: {signal.liquidity_sol:.1f} SOL
- Holders: {signal.holder_count}
- Top 10 holders: {signal.top10_holder_pct:.1f}% of supply
- Dev wallet sold: {signal.dev_wallet_sold}
- Buy/Sell ratio (1h): {signal.buy_count_1h}/{signal.sell_count_1h}
- Source: {signal.source}

SOCIAL:
- Twitter mentions (1h): {signal.twitter_mentions_1h}
- KOL mentions: {kol_section}
- Top tweets:
{tweets_section}

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


async def analyze_token(signal: TokenSignal) -> dict | None:
    if not settings.anthropic_api_key:
        log.warning("ai_analyzer_skipped", reason="ANTHROPIC_API_KEY not set")
        return None

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

        response = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=512,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _build_prompt(signal)}],
        )

        raw = response.content[0].text.strip()
        result = json.loads(raw)

        # Final score: 40% rule filters + 60% AI
        final_score = round(signal.rule_score * 0.4 + result["score"] * 0.6, 2)
        result["final_score"] = final_score

        log.info(
            "ai_analysis_done",
            symbol=signal.symbol,
            ai_score=result["score"],
            final_score=final_score,
            confidence=result["confidence"],
            risk=result["risk_level"],
            reasoning=result["reasoning"][:80] + "...",
        )

        return result

    except json.JSONDecodeError as e:
        log.error("ai_bad_json", symbol=signal.symbol, error=str(e), raw=raw[:200])
        return None
    except Exception as e:
        log.error("ai_analyzer_failed", symbol=signal.symbol, error=str(e))
        return None
