import re
from config import settings
from sources.signal import TweetInfo
from utils.logger import get_logger

log = get_logger("twitter")


def _username_from_url(url: str) -> str:
    """Extract @username from a Twitter/X URL."""
    match = re.search(r"(?:twitter\.com|x\.com)/([A-Za-z0-9_]+)", url)
    return match.group(1) if match else ""


def _get_client():
    if not settings.twitter_bearer_token:
        return None
    import tweepy
    return tweepy.Client(bearer_token=settings.twitter_bearer_token, wait_on_rate_limit=False)


async def verify_token_profile(twitter_url: str, contract_address: str) -> dict:
    """
    Check the token's own Twitter account:
    - Extract username from URL
    - Fetch bio + recent pinned tweets
    - Confirm contract address appears (authenticity signal)
    Returns dict: {verified, username, followers, reason}
    """
    result = {"verified": False, "username": "", "followers": 0, "reason": ""}

    username = _username_from_url(twitter_url)
    if not username:
        result["reason"] = "no_twitter_url"
        return result

    result["username"] = username

    client = _get_client()
    if not client:
        result["reason"] = "no_twitter_api_key"
        return result

    try:
        user_resp = client.get_user(
            username=username,
            user_fields=["description", "public_metrics", "created_at"],
        )
        if not user_resp.data:
            result["reason"] = "account_not_found"
            return result

        user = user_resp.data
        followers = user.public_metrics["followers_count"]
        bio = (user.description or "").lower()
        result["followers"] = followers

        # Fetch last 10 tweets to search for contract address
        tweets_resp = client.get_users_tweets(
            user.id,
            max_results=10,
            tweet_fields=["text"],
        )
        tweet_texts = [t.text for t in (tweets_resp.data or [])]
        all_text = bio + " " + " ".join(tweet_texts)

        contract_lower = contract_address.lower()
        if contract_lower in all_text.lower():
            result["verified"] = True
            result["reason"] = "contract_found_in_profile"
            log.info("twitter_verified", username=username, followers=followers)
        else:
            result["reason"] = "contract_not_in_profile"
            log.info(
                "twitter_not_verified",
                username=username,
                followers=followers,
                reason="contract address not found in bio or recent tweets",
            )

    except Exception as e:
        result["reason"] = f"api_error: {e}"
        log.warning("twitter_verify_failed", username=username, error=str(e))

    return result


async def search_mentions(
    symbol: str,
    contract_address: str,
    max_results: int = 50,
) -> list[TweetInfo]:
    """
    Search Twitter for:
    1. $SYMBOL mentions
    2. Contract address mentions
    Returns merged, deduplicated list of TweetInfo sorted by followers desc.
    """
    client = _get_client()
    if not client:
        return []

    seen_ids: set = set()
    results: list[TweetInfo] = []

    queries = [
        f"${symbol} lang:en -is:retweet",
        f"{contract_address} -is:retweet",
    ]

    for query in queries:
        try:
            resp = client.search_recent_tweets(
                query=query,
                max_results=min(max_results, 50),
                tweet_fields=["text", "public_metrics", "author_id"],
                expansions=["author_id"],
                user_fields=["username", "public_metrics"],
            )

            users = {}
            if resp.includes and resp.includes.get("users"):
                for u in resp.includes["users"]:
                    users[u.id] = {
                        "username": u.username,
                        "followers": u.public_metrics["followers_count"],
                    }

            for tweet in resp.data or []:
                if tweet.id in seen_ids:
                    continue
                seen_ids.add(tweet.id)

                author = users.get(tweet.author_id, {})
                results.append(TweetInfo(
                    text=tweet.text[:280],
                    author_name=author.get("username", "unknown"),
                    author_followers=author.get("followers", 0),
                    likes=tweet.public_metrics["like_count"],
                    retweets=tweet.public_metrics["retweet_count"],
                ))

        except Exception as e:
            log.warning("twitter_search_failed", query=query, error=str(e))

    # Sort by follower count so Claude sees the most influential first
    results.sort(key=lambda t: t.author_followers, reverse=True)
    log.info("twitter_mentions_fetched", symbol=symbol, count=len(results))
    return results
