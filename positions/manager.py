from datetime import datetime

from db.database import get_session
from db.models import Position
from utils.logger import get_logger

log = get_logger("position_manager")

# Position status values
ST_OPEN = "open"          # 100% remaining
ST_PARTIAL = "partial"    # sold 50% at x2, 50% remaining
ST_PARTIAL2 = "partial2"  # sold 50%+25%, 25% remaining
ST_CLOSED = "closed"      # fully out


class PositionManager:
    def __init__(self):
        # token_address → Position (in-memory for fast iteration)
        self._positions: dict[str, Position] = {}
        self._load_open_from_db()

    def _load_open_from_db(self):
        """Restore open positions from DB on startup (survives restarts)."""
        try:
            with get_session() as session:
                rows = session.query(Position).filter(
                    Position.status.in_([ST_OPEN, ST_PARTIAL, ST_PARTIAL2])
                ).all()
                for p in rows:
                    self._positions[p.token_address] = p
            if self._positions:
                log.info("positions_restored", count=len(self._positions))
        except Exception as e:
            log.warning("positions_load_failed", error=str(e))

    def open_position(
        self,
        token_address: str,
        symbol: str,
        buy_price_usd: float,
        invested_sol: float,
        amount_tokens: float,
        tx_signature: str,
        paper: bool,
    ) -> Position:
        pos = Position(
            token_address=token_address,
            symbol=symbol,
            buy_price_usd=buy_price_usd,
            invested_sol=invested_sol,
            amount_tokens=amount_tokens,
            buy_tx_signature=tx_signature,
            highest_price_usd=buy_price_usd,
            status=ST_OPEN,
            paper=paper,
        )
        try:
            with get_session() as session:
                session.add(pos)
                session.commit()
                session.refresh(pos)
        except Exception as e:
            log.error("position_save_failed", symbol=symbol, error=str(e))

        self._positions[token_address] = pos
        log.info("position_opened", symbol=symbol, invested_sol=invested_sol,
                 price_usd=buy_price_usd, paper=paper)
        return pos

    def record_sell(self, position: Position, sold_pct: float, pnl_sol: float):
        """Update position after a partial or full sell."""
        position.realized_pnl_sol += pnl_sol

        if sold_pct >= 0.99:
            position.status = ST_CLOSED
            self._positions.pop(position.token_address, None)
        elif position.status == ST_OPEN:
            position.status = ST_PARTIAL    # sold 50%
        elif position.status == ST_PARTIAL:
            position.status = ST_PARTIAL2   # sold another 25%

        try:
            with get_session() as session:
                session.merge(position)
                session.commit()
        except Exception as e:
            log.error("position_update_failed", symbol=position.symbol, error=str(e))

    def update_highest_price(self, position: Position, price: float):
        if price > position.highest_price_usd:
            position.highest_price_usd = price
            try:
                with get_session() as session:
                    session.merge(position)
                    session.commit()
            except Exception:
                pass

    def get_open(self) -> list[Position]:
        return list(self._positions.values())

    def has_position(self, token_address: str) -> bool:
        return token_address in self._positions

    @property
    def count(self) -> int:
        return len(self._positions)
