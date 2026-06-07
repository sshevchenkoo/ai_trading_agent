import asyncio
import json

import websockets

from sources.signal import TokenSignal
from utils.logger import get_logger

log = get_logger("pumpfun")

PUMPFUN_WS = "wss://pumpportal.fun/api/data"


class PumpFunCollector:
    """
    Listens to pump.fun WebSocket and puts new tokens into a queue.
    Does NOT process them — the Poller drains the queue every N minutes.
    """

    def __init__(self, queue: asyncio.Queue):
        self.queue = queue
        self._running = False

    async def start(self):
        self._running = True
        while self._running:
            try:
                await self._connect()
            except Exception as e:
                log.warning("pumpfun_disconnected", error=str(e))
                if self._running:
                    await asyncio.sleep(5)

    async def stop(self):
        self._running = False

    async def _connect(self):
        log.info("pumpfun_connecting")
        async with websockets.connect(PUMPFUN_WS) as ws:
            await ws.send(json.dumps({"method": "subscribeNewToken"}))
            log.info("pumpfun_connected")
            async for message in ws:
                if not self._running:
                    break
                try:
                    data = json.loads(message)
                    signal = self._parse(data)
                    if signal:
                        await self.queue.put(signal)
                except Exception as e:
                    log.error("pumpfun_parse_error", error=str(e))

    def _parse(self, data: dict) -> TokenSignal | None:
        address = data.get("mint") or data.get("token_address")
        if not address:
            return None
        return TokenSignal(
            token_address=address,
            symbol=data.get("symbol", "???"),
            name=data.get("name", ""),
            description=data.get("description", ""),
            source="pumpfun",
            market_cap_usd=float(data.get("market_cap", 0) or 0),
            liquidity_sol=float(data.get("virtual_sol_reserves", 0) or 0) / 1e9,
            creator=data.get("creator", ""),
            twitter_url=data.get("twitter", ""),
            telegram_url=data.get("telegram", ""),
            website_url=data.get("website", ""),
        )
