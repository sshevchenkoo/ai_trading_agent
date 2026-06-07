import asyncio

from config import settings
from db.database import init_db, get_session
from db.models import Token
from sources.pumpfun import PumpFunCollector
from sources.poller import Poller
from sources.signal import TokenSignal
from analysis.filters import apply_filters
from analysis.rugcheck import check_token
from utils.logger import setup_logging, get_logger

log = get_logger("main")

POLL_INTERVAL_SEC = 300  # 5 minutes


async def handle_token(signal: TokenSignal):
    result = apply_filters(signal)
    signal.rule_score = result.score

    if not result.passed:
        log.info("filter_fail", symbol=signal.symbol, reason=result.reason)
        _save_token(signal, passed=False)
        return

    rug = await check_token(signal.token_address)
    if not rug["is_safe"] and rug["score"] != -1:
        log.info(
            "rugcheck_fail",
            symbol=signal.symbol,
            score=rug["score"],
            risks=rug["risks"][:3],
        )
        _save_token(signal, passed=False)
        return

    _save_token(signal, passed=True)

    log.info(
        "candidate_ready",
        symbol=signal.symbol,
        rule_score=signal.rule_score,
        liquidity_sol=round(signal.liquidity_sol, 1),
        age_min=signal.age_minutes,
        twitter_mentions=signal.twitter_mentions_1h,
        rugcheck_score=rug["score"],
    )

    # TODO Phase 2: AI Analyzer
    # TODO Phase 3: Trade Executor


def _save_token(signal: TokenSignal, passed: bool):
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
                passed_filters=passed,
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
        # Run WebSocket collector and 5-min poller concurrently
        await asyncio.gather(
            collector.start(),
            poller.start(),
        )
    except KeyboardInterrupt:
        log.info("bot_stopped")
        await collector.stop()
        await poller.stop()


if __name__ == "__main__":
    asyncio.run(main())
