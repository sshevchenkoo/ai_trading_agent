import asyncio

from config import settings
from db.database import init_db, get_session
from db.models import Token
from sources.pumpfun import PumpFunCollector
from sources.poller import Poller
from sources.signal import TokenSignal
from analysis.ai_analyzer import analyze_token
from utils.logger import setup_logging, get_logger

log = get_logger("main")

POLL_INTERVAL_SEC = 300  # 5 minutes


async def handle_token(signal: TokenSignal):
    """
    Called only for tokens that passed the full filter pipeline:
    Rule Filters → Birdeye security → Rugcheck → Twitter verification
    """
    analysis = await analyze_token(signal)

    if analysis is None:
        log.info(
            "candidate_no_ai",
            symbol=signal.symbol,
            rule_score=signal.rule_score,
            liquidity_sol=round(signal.liquidity_sol, 1),
            twitter_verified=signal.twitter_verified,
        )
        _save_token(signal)
        return

    signal.ai_score = analysis["score"]
    signal.final_score = analysis["final_score"]
    _save_token(signal)

    if analysis["final_score"] < settings.ai_score_threshold:
        log.info(
            "ai_score_too_low",
            symbol=signal.symbol,
            final_score=analysis["final_score"],
            threshold=settings.ai_score_threshold,
        )
        return

    log.info(
        "BUY_SIGNAL",
        symbol=signal.symbol,
        final_score=analysis["final_score"],
        ai_score=analysis["score"],
        rule_score=signal.rule_score,
        confidence=analysis["confidence"],
        risk=analysis["risk_level"],
        suggested_sol=analysis["suggested_position_sol"],
        twitter_verified=signal.twitter_verified,
        twitter_mentions=signal.twitter_mentions_1h,
        reasoning=analysis["reasoning"],
    )

    # TODO Phase 3: Trade Executor → execute buy


def _save_token(signal: TokenSignal):
    try:
        with get_session() as session:
            if session.get(Token, signal.token_address):
                return
            session.add(Token(
                address=signal.token_address,
                symbol=signal.symbol,
                name=signal.name,
                description=signal.description,
                creator=signal.creator,
                source=signal.source,
                liquidity_sol=signal.liquidity_sol,
                market_cap_usd=signal.market_cap_usd,
                holder_count=signal.holder_count,
                age_minutes=signal.age_minutes,
                buy_count_1h=signal.buy_count_1h,
                sell_count_1h=signal.sell_count_1h,
                rule_score=signal.rule_score,
                ai_score=signal.ai_score or None,
                final_score=signal.final_score or None,
                passed_filters=True,
            ))
            session.commit()
    except Exception as e:
        log.error("db_save_error", error=str(e))


async def main():
    setup_logging()
    init_db()

    mode = "PAPER TRADING" if settings.paper_trading else "LIVE TRADING"
    log.info("bot_starting", mode=mode, poll_interval_sec=POLL_INTERVAL_SEC)

    pumpfun_queue: asyncio.Queue = asyncio.Queue()
    collector = PumpFunCollector(queue=pumpfun_queue)
    poller = Poller(
        pumpfun_queue=pumpfun_queue,
        on_token=handle_token,
        interval_seconds=POLL_INTERVAL_SEC,
    )

    try:
        await asyncio.gather(collector.start(), poller.start())
    except KeyboardInterrupt:
        log.info("bot_stopped")
        await collector.stop()
        await poller.stop()


if __name__ == "__main__":
    asyncio.run(main())
