import asyncio
import json
from datetime import datetime
from typing import Callable, Awaitable

import websockets

from sources.signal import TokenSignal
from utils.logger import get_logger

log = get_logger("pumpfun")

PUMPFUN_WS = "wss://pumpportal.fun/api/data"


class PumpFunListener:
    def __init__(self, on_token: Callable[[TokenSignal], Awaitable[None]]):
        self.on_token = on_token
        self._running = False

    async def start(self):
        self._running = True
        while self._running:
            try:
                await self._connect()
            except Exception as e:
                log.warning("pumpfun_disconnected", error=str(e))
                if self._running:
                    log.info("pumpfun_reconnecting", delay=5)
                    await asyncio.sleep(5)

    async def stop(self):
        self._running = False

    async def _connect(self):
        log.info("pumpfun_connecting", url=PUMPFUN_WS)
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
                        await self.on_token(signal)
                except Exception as e:
                    log.error("pumpfun_parse_error", error=str(e))

    def _parse(self, data: dict) -> TokenSignal | None:
        address = data.get("mint") or data.get("token_address")
        if not address:
            return None

        symbol = data.get("symbol", "???")
        name = data.get("name", symbol)
        market_cap = float(data.get("market_cap", 0) or 0)
        virt_sol = float(data.get("virtual_sol_reserves", 30) or 30)

        log.info(
            "new_token",
            symbol=symbol,
            address=address[:8] + "...",
            market_cap_usd=market_cap,
            liquidity_sol=virt_sol,
        )

        return TokenSignal(
            token_address=address,
            symbol=symbol,
            name=name,
            description=data.get("description", ""),
            source="pumpfun",
            liquidity_sol=virt_sol,
            market_cap_usd=market_cap,
            age_minutes=0,
            creator=data.get("creator", ""),
        )
