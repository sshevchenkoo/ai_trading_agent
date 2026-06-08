from config import settings
from db.database import get_session
from db.models import Trade, Position
from sources.price import get_token_price_usd
from sources.signal import TokenSignal
from utils.logger import get_logger

log = get_logger("executor")

TOKEN_DECIMALS = 6  # pump.fun tokens have 6 decimals


class TradeExecutor:
    def __init__(self, position_manager):
        self.manager = position_manager
        self._selling: set[str] = set()  # prevent double-sells

    # ── Buy ───────────────────────────────────────────────────────────────────

    async def buy(self, signal: TokenSignal, sol_amount: float) -> bool:
        if self.manager.has_position(signal.token_address):
            log.info("buy_skipped_already_open", symbol=signal.symbol)
            return False

        if self.manager.count >= settings.max_open_positions:
            log.info("buy_skipped_max_positions", symbol=signal.symbol,
                     open=self.manager.count)
            return False

        price_usd = await get_token_price_usd(signal.token_address)
        if price_usd is None:
            log.warning("buy_skipped_no_price", symbol=signal.symbol)
            return False

        if settings.paper_trading:
            return self._paper_buy(signal, sol_amount, price_usd)
        return await self._live_buy(signal, sol_amount, price_usd)

    def _paper_buy(self, signal: TokenSignal, sol_amount: float, price_usd: float) -> bool:
        self.manager.open_position(
            token_address=signal.token_address,
            symbol=signal.symbol,
            buy_price_usd=price_usd,
            invested_sol=sol_amount,
            amount_tokens=0.0,
            tx_signature="paper",
            paper=True,
        )
        self._save_trade(signal.token_address, signal.symbol, "buy",
                         sol_amount, price_usd, "paper", "ai_signal", paper=True)
        log.info("PAPER_BUY", symbol=signal.symbol, sol=sol_amount,
                 price_usd=f"${price_usd:.8f}")
        return True

    async def _live_buy(self, signal: TokenSignal, sol_amount: float, price_usd: float) -> bool:
        from trading.jupiter import get_quote, execute_swap, SOL_MINT
        from trading.wallet import load_keypair

        lamports = int(sol_amount * 1e9)
        quote = await get_quote(SOL_MINT, signal.token_address, lamports)
        if not quote:
            return False

        token_amount = float(quote.get("outAmount", 0))
        keypair = load_keypair()
        sig = await execute_swap(quote, keypair)
        if not sig:
            return False

        self.manager.open_position(
            token_address=signal.token_address,
            symbol=signal.symbol,
            buy_price_usd=price_usd,
            invested_sol=sol_amount,
            amount_tokens=token_amount,
            tx_signature=sig,
            paper=False,
        )
        self._save_trade(signal.token_address, signal.symbol, "buy",
                         sol_amount, price_usd, sig, "ai_signal", paper=False)
        log.info("LIVE_BUY", symbol=signal.symbol, sol=sol_amount,
                 sig=sig[:12] + "...", price_usd=f"${price_usd:.8f}")
        return True

    # ── Sell ──────────────────────────────────────────────────────────────────

    async def sell(self, position: Position, pct: float, reason: str) -> bool:
        addr = position.token_address
        if addr in self._selling:
            return False  # already selling this position

        self._selling.add(addr)
        try:
            price_usd = await get_token_price_usd(addr)
            if price_usd is None:
                log.warning("sell_skipped_no_price", symbol=position.symbol)
                return False

            if settings.paper_trading:
                return self._paper_sell(position, pct, price_usd, reason)
            return await self._live_sell(position, pct, price_usd, reason)
        finally:
            self._selling.discard(addr)

    def _paper_sell(self, position: Position, pct: float,
                    price_usd: float, reason: str) -> bool:
        multiplier = price_usd / position.buy_price_usd
        sol_received = position.invested_sol * pct * multiplier
        pnl_sol = sol_received - position.invested_sol * pct

        self.manager.record_sell(position, pct, pnl_sol)
        self._save_trade(position.token_address, position.symbol, "sell",
                         sol_received, price_usd, "paper", reason, paper=True)
        log.info(
            "PAPER_SELL",
            symbol=position.symbol,
            pct=f"{pct*100:.0f}%",
            reason=reason,
            multiplier=f"{multiplier:.2f}x",
            pnl_sol=f"{pnl_sol:+.4f}",
        )
        return True

    async def _live_sell(self, position: Position, pct: float,
                         price_usd: float, reason: str) -> bool:
        from trading.jupiter import get_quote, execute_swap, SOL_MINT
        from trading.wallet import load_keypair

        raw_amount = int(position.amount_tokens * pct)
        if raw_amount == 0:
            log.warning("sell_skipped_zero_amount", symbol=position.symbol)
            return False

        quote = await get_quote(position.token_address, SOL_MINT, raw_amount)
        if not quote:
            return False

        sol_received = int(quote.get("outAmount", 0)) / 1e9
        keypair = load_keypair()
        sig = await execute_swap(quote, keypair)
        if not sig:
            return False

        pnl_sol = sol_received - position.invested_sol * pct
        self.manager.record_sell(position, pct, pnl_sol)
        self._save_trade(position.token_address, position.symbol, "sell",
                         sol_received, price_usd, sig, reason, paper=False)
        multiplier = price_usd / position.buy_price_usd
        log.info(
            "LIVE_SELL",
            symbol=position.symbol,
            pct=f"{pct*100:.0f}%",
            reason=reason,
            multiplier=f"{multiplier:.2f}x",
            pnl_sol=f"{pnl_sol:+.4f}",
            sig=sig[:12] + "...",
        )
        return True

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _save_trade(self, token_address, symbol, side, amount_sol,
                    price_usd, tx_sig, reason, paper):
        try:
            with get_session() as session:
                session.add(Trade(
                    token_address=token_address,
                    symbol=symbol,
                    side=side,
                    amount_sol=amount_sol,
                    price_usd=price_usd,
                    tx_signature=tx_sig,
                    reason=reason,
                    paper=paper,
                ))
                session.commit()
        except Exception as e:
            log.error("trade_save_failed", symbol=symbol, error=str(e))
