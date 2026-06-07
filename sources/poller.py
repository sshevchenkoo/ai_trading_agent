import asyncio
from typing import Callable, Awaitable

from sources.dexscreener import fetch_new_pairs, enrich_signal
from sources.market_data import get_market_context
from sources.birdeye import get_token_analysis
from sources.twitter import verify_token_profile, search_mentions
from sources.signal import TokenSignal
from analysis.filters import apply_filters
from analysis.rugcheck import check_token
from utils.logger import get_logger

log = get_logger("poller")


class Poller:
    """
    Every `interval_seconds` runs the full pipeline:

    1.  Collect new tokens from pump.fun queue + DexScreener
    2.  Deduplicate (skip already-seen addresses)
    3.  Enrich each token with DexScreener metrics
    4.  Rule Filters  — reject ~60% (fast, free)
    5.  Birdeye       — reject another ~20% (security check)
    6.  Rugcheck      — reject obvious scam contracts
    7.  Twitter       — verify token's own Twitter profile
                        search for $TICKER + contract mentions
    8.  Pass enriched signal to on_token() for AI analysis
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

        # Step 1 — collect from all sources + market context in parallel
        pumpfun_tokens = _drain_queue(self.queue)
        dex_tokens, market_ctx = await asyncio.gather(
            fetch_new_pairs(),
            get_market_context(),
        )

        # Step 2 — merge and deduplicate
        merged: dict[str, TokenSignal] = {}
        for sig in pumpfun_tokens + dex_tokens:
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
            new_unique=len(new_tokens),
        )

        if not new_tokens:
            return

        # Mark seen before processing (avoid re-processing next cycle)
        self._seen.update(sig.token_address for sig in new_tokens)
        if len(self._seen) > 2000:
            self._seen = set(list(self._seen)[-1000:])

        # Step 3 — enrich all with DexScreener (parallel)
        enriched: list[TokenSignal] = list(
            await asyncio.gather(*[enrich_signal(sig) for sig in new_tokens])
        )

        # Attach market context to all
        for sig in enriched:
            sig.market = market_ctx

        # Steps 4-8 — full pipeline per token (sequential checks, fail fast)
        for sig in enriched:
            await self._pipeline(sig)

        log.info("poll_cycle_done")

    # ── Per-token pipeline ────────────────────────────────────────────────────

    async def _pipeline(self, signal: TokenSignal):
        sym = signal.symbol
        addr = signal.token_address

        # ── Step 4: Rule Filters (free, instant) ─────────────────────────────
        rule = apply_filters(signal)
        signal.rule_score = rule.score
        if not rule.passed:
            log.info("rejected_rule", symbol=sym, reason=rule.reason)
            return

        # ── Step 5: Birdeye security check ───────────────────────────────────
        birdeye = await get_token_analysis(addr)
        signal._birdeye = birdeye

        if birdeye:
            reject_reason = _birdeye_reject(birdeye)
            if reject_reason:
                log.info("rejected_birdeye", symbol=sym, reason=reject_reason)
                return

        # ── Step 6: Rugcheck ─────────────────────────────────────────────────
        rug = await check_token(addr)
        if not rug["is_safe"] and rug["score"] != -1:
            log.info("rejected_rugcheck", symbol=sym, score=rug["score"], risks=rug["risks"][:3])
            return

        # ── Step 7: Twitter verification ─────────────────────────────────────
        if signal.twitter_url:
            profile = await verify_token_profile(signal.twitter_url, addr)
            signal.twitter_verified = profile["verified"]
            signal.twitter_username = profile["username"]
            signal.twitter_followers = profile["followers"]

            if not profile["verified"]:
                log.info(
                    "twitter_unverified",
                    symbol=sym,
                    username=profile["username"],
                    reason=profile["reason"],
                )
                # Don't hard-reject — unverified Twitter is a red flag but not instant kill
                # Claude will weigh it in the analysis

        # Search $TICKER + contract mentions in Twitter feed
        if signal.twitter_username or signal.twitter_url:
            signal.tweets = await search_mentions(sym, addr, max_results=50)
            signal.twitter_mentions_1h = len(signal.tweets)

        # ── Step 8: Pass to AI analysis ───────────────────────────────────────
        log.info(
            "pipeline_passed",
            symbol=sym,
            rule_score=signal.rule_score,
            liquidity_sol=round(signal.liquidity_sol, 1),
            twitter_verified=signal.twitter_verified,
            twitter_mentions=signal.twitter_mentions_1h,
        )
        await self.on_token(signal)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _drain_queue(q: asyncio.Queue) -> list[TokenSignal]:
    tokens = []
    while not q.empty():
        tokens.append(q.get_nowait())
    return tokens


def _birdeye_reject(b: dict) -> str:
    """Return a rejection reason if Birdeye data indicates a scam, else empty string."""
    if b.get("is_mintable"):
        return "mint_authority_not_revoked"
    if b.get("is_freezable"):
        return "freeze_authority_exists"
    if b.get("creator_pct", 0) > 20:
        return f"creator_holds_{b['creator_pct']:.0f}pct"
    if b.get("top10_holder_pct", 0) > 70:
        return f"top10_holds_{b['top10_holder_pct']:.0f}pct"
    if b.get("lp_locked_pct", 100) < 10:
        return "lp_not_locked"
    return ""
