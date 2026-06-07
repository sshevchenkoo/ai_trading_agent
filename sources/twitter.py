from config import settings
from utils.logger import get_logger

log = get_logger("twitter")


async def fetch_kol_mentions() -> dict[str, list[str]]:
    """
    Poll Twitter for recent token mentions from KOL accounts.
    Returns dict: {token_symbol: [tweet_text, ...]}
    Skipped if TWITTER_BEARER_TOKEN is not set.
    """
    if not settings.twitter_bearer_token:
        return {}

    try:
        import tweepy

        client = tweepy.Client(
            bearer_token=settings.twitter_bearer_token,
            wait_on_rate_limit=False,
        )

        query = "pump.fun OR (solana new token) lang:en -is:retweet"
        response = client.search_recent_tweets(
            query=query,
            max_results=100,
            tweet_fields=["text", "author_id", "public_metrics"],
        )

        mentions: dict[str, list[str]] = {}
        tweets = response.data or []

        for tweet in tweets:
            text = tweet.text
            # Extract $TICKER mentions
            words = text.split()
            for word in words:
                if word.startswith("$") and len(word) > 1:
                    ticker = word[1:].upper().rstrip(".,!?")
                    if 2 <= len(ticker) <= 10:
                        mentions.setdefault(ticker, []).append(text[:200])

        log.info("twitter_polled", tweet_count=len(tweets), tickers_found=len(mentions))
        return mentions

    except Exception as e:
        log.warning("twitter_poll_failed", error=str(e))
        return {}
