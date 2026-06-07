from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Solana
    solana_rpc_url: str = "https://api.mainnet-beta.solana.com"
    wallet_private_key: str = ""

    # AI
    anthropic_api_key: str = ""

    # Twitter
    twitter_bearer_token: str = ""
    twitter_api_key: str = ""
    twitter_api_secret: str = ""
    twitter_access_token: str = ""
    twitter_access_secret: str = ""

    # Strategy
    max_position_size_sol: float = 0.2
    min_liquidity_sol: float = 50.0
    ai_score_threshold: float = 7.0
    max_open_positions: int = 5
    stop_loss_pct: float = 50.0

    # Mode
    paper_trading: bool = True
    log_level: str = "INFO"

    class Config:
        env_file = ".env"


settings = Settings()
