import asyncio
from typing import Callable, Awaitable

from sources.dexscreener import fetch_new_pairs, fetch_top_gainers, enrich_signal
from sources.market_data import get_market_context
from sources.signal import TokenSignal
from utils.logger import get_logger

log = get_logger("poller")

MIN_MARKET_CAP_USD = 5_000


class Poller:
    """
    Every `interval_seconds`:
    1. Drain pump.fun queue + fetch DexScreener pairs
    2. Deduplicate, enrich with DexScreener (real mcap/liquidity)
    3. Filter: market cap > $5k
    4. Pass to Claude AI — Claude uses tools to investigate and decide
    """

    def __init__(
        self,
        pumpfun_queue: asyncio.Queue,
        on_token: Callable[[TokenSignal], Awaitable[None]],
        interval_seconds: int = 300,
    ):
        self.queue = pumpfun_queue
        self.on_token = on_token
        self.interval = interval_seconds
        self._seen: set[str] = set()
        self._running = False

    async def start(self):
        self._running = True
        log.info("poller_started", interval_sec=self.interval)
        while self._running:
            await asyncio.sleep(self.interval)
            try:
                await self._cycle()
            except Exception as e:
                log.error("poll_cycle_error", error=str(e))

    async def stop(self):
        self._running = False

    # ── Main cycle ────────────────────────────────────────────────────────────

    async def _cycle(self):
        log.info("poll_cycle_start")

        pumpfun_tokens = _drain_queue(self.queue)
        dex_tokens, top_gainers, market_ctx = await asyncio.gather(
            fetch_new_pairs(),
            fetch_top_gainers(limit=10),
            get_market_context(),
        )

        # pump.fun wins on duplicates (has richer metadata)
        merged: dict[str, TokenSignal] = {}
        for sig in pumpfun_tokens + dex_tokens + top_gainers:
            if sig.token_address not in merged:
                merged[sig.token_address] = sig

        new_tokens = [
            sig for addr, sig in merged.items()
            if addr not in self._seen
        ]

        log.info(
            "poll_cycle_collected",
            pumpfun=len(pumpfun_tokens),
            dexscreener=len(dex_tokens),
            top_gainers=len(top_gainers),
            new_unique=len(new_tokens),
        )

        if not new_tokens:
            return

        self._seen.update(sig.token_address for sig in new_tokens)
        if len(self._seen) > 2000:
            self._seen = set(list(self._seen)[-1000:])

        # Enrich all with DexScreener in parallel (get real mcap)
        enriched: list[TokenSignal] = list(
            await asyncio.gather(*[enrich_signal(sig) for sig in new_tokens])
        )

        for sig in enriched:
            sig.market = market_ctx

        for sig in enriched:
            await self._pipeline(sig)

        log.info("poll_cycle_done")

    # ── Per-token pipeline ────────────────────────────────────────────────────

    async def _pipeline(self, signal: TokenSignal):
        sym = signal.symbol

        # Only filter: market cap must be above minimum threshold
        if signal.market_cap_usd < MIN_MARKET_CAP_USD:
            log.info(
                "rejected_mcap",
                symbol=sym,
                market_cap_usd=round(signal.market_cap_usd),
            )
            return

        log.info(
            "pipeline_passed",
            symbol=sym,
            market_cap_usd=round(signal.market_cap_usd),
            liquidity_sol=round(signal.liquidity_sol, 1),
            age_minutes=signal.age_minutes,
        )
        await self.on_token(signal)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _drain_queue(q: asyncio.Queue) -> list[TokenSignal]:
    tokens = []
    while not q.empty():
        tokens.append(q.get_nowait())
    return tokens
