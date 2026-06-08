import asyncio

from db.models import Position
from positions.manager import ST_OPEN, ST_PARTIAL, ST_PARTIAL2
from sources.price import get_token_price_usd
from utils.logger import get_logger

log = get_logger("monitor")

POLL_INTERVAL_SEC = 10

# Sell triggers
X2_THRESHOLD = 2.0   # sell 50%
X4_THRESHOLD = 4.0   # sell 25%
X10_THRESHOLD = 10.0 # sell remaining 25%
STOP_LOSS = 0.5      # sell everything at -50%


class PositionMonitor:
    def __init__(self, executor, position_manager):
        self.executor = executor
        self.manager = position_manager
        self._running = False

    async def start(self):
        self._running = True
        log.info("monitor_started", interval_sec=POLL_INTERVAL_SEC)
        while self._running:
            await asyncio.sleep(POLL_INTERVAL_SEC)
            if not self.manager.get_open():
                continue
            try:
                await self._check_all()
            except Exception as e:
                log.error("monitor_cycle_error", error=str(e))

    async def stop(self):
        self._running = False

    async def _check_all(self):
        positions = self.manager.get_open()
        tasks = [self._check_position(pos) for pos in positions]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _check_position(self, pos: Position):
        price = await get_token_price_usd(pos.token_address)
        if price is None:
            return

        self.manager.update_highest_price(pos, price)
        multiplier = price / pos.buy_price_usd

        log.debug(
            "position_check",
            symbol=pos.symbol,
            multiplier=f"{multiplier:.2f}x",
            status=pos.status,
        )

        # ── Stop-loss ────────────────────────────────────────────────────────
        if multiplier <= STOP_LOSS:
            log.warning("stop_loss_triggered", symbol=pos.symbol,
                        multiplier=f"{multiplier:.2f}x")
            await self.executor.sell(pos, 1.0, "stop_loss")
            return

        # ── x10 → sell all remaining ─────────────────────────────────────────
        if multiplier >= X10_THRESHOLD and pos.status in (ST_PARTIAL, ST_PARTIAL2):
            await self.executor.sell(pos, 1.0, "x10_target")
            return

        # ── x4 → sell 25% (only after x2 sell) ──────────────────────────────
        if multiplier >= X4_THRESHOLD and pos.status == ST_PARTIAL:
            await self.executor.sell(pos, 0.25, "x4_target")
            return

        # ── x2 → sell 50% (first sell) ───────────────────────────────────────
        if multiplier >= X2_THRESHOLD and pos.status == ST_OPEN:
            await self.executor.sell(pos, 0.5, "x2_target")
            return
