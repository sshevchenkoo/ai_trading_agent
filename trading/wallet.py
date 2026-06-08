import base58
from solders.keypair import Keypair

from config import settings
from utils.logger import get_logger

log = get_logger("wallet")

_keypair: Keypair | None = None


def load_keypair() -> Keypair:
    """Load Solana keypair from WALLET_PRIVATE_KEY env var (base58-encoded)."""
    global _keypair
    if _keypair is not None:
        return _keypair

    raw = settings.wallet_private_key
    if not raw:
        raise ValueError("WALLET_PRIVATE_KEY not set in .env")

    _keypair = Keypair.from_bytes(base58.b58decode(raw))
    log.info("wallet_loaded", pubkey=str(_keypair.pubkey())[:8] + "...")
    return _keypair
