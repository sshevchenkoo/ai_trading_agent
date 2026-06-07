import asyncio
from typing import Callable, Awaitable

from sources.dexscreener import fetch_new_pairs, enrich_signal
from sources.twitter import fetch_kol_mentions
from sources.signal import TokenSignal
from utils.logger import get_logger

log = get_logger("poller")


class Poller:
    """
    Every `interval_seconds`:
      1. Drain the pump.fun queue (tokens collected by WebSocket)
      2. Fetch new pairs from DexScreener
      3. Fetch Twitter KOL mentions
      4. Deduplicate, enrich, attach Twitter data
      5. Call on_token() for each new signal
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

    async def _cycle(self):
        log.info("poll_cycle_start")

        # 1. Drain pump.fun queue
        pumpfun_signals: list[TokenSignal] = []
        while not self.queue.empty():
            pumpfun_signals.append(self.queue.get_nowait())

        # 2. Fetch DexScreener + Twitter in parallel
        dex_signals, twitter_mentions = await asyncio.gather(
            fetch_new_pairs(),
            fetch_kol_mentions(),
        )

        # 3. Merge all sources, deduplicate by address
        merged: dict[str, TokenSignal] = {}
        for sig in pumpfun_signals + dex_signals:
            if sig.token_address not in merged:
                merged[sig.token_address] = sig

        # 4. Skip already-seen tokens
        new_tokens = {
            addr: sig
            for addr, sig in merged.items()
            if addr not in self._seen
        }

        log.info(
            "poll_cycle_collected",
            pumpfun=len(pumpfun_signals),
            dexscreener=len(dex_signals),
            new_unique=len(new_tokens),
        )

        if not new_tokens:
            return

        # 5. Enrich all new tokens with DexScreener metrics (in parallel)
        enriched = await asyncio.gather(
            *[enrich_signal(sig) for sig in new_tokens.values()]
        )

        # 6. Attach Twitter mentions
        for signal in enriched:
            tweets = twitter_mentions.get(signal.symbol.upper(), [])
            if tweets:
                signal.twitter_mentions_1h = len(tweets)
                signal.tweet_texts = tweets

        # 7. Mark all as seen
        self._seen.update(new_tokens.keys())
        if len(self._seen) > 2000:
            self._seen = set(list(self._seen)[-1000:])

        # 8. Send each to handler
        for signal in enriched:
            await self.on_token(signal)

        log.info("poll_cycle_done", processed=len(enriched))
