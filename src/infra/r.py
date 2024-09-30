from redis import Redis
from urllib.parse import urlparse
from config import REDIS_URL

parsed_url = urlparse(REDIS_URL)


r = Redis(
    host=parsed_url.hostname or "0.0.0.0",
    port=int(parsed_url.port or 6345),
    password=parsed_url.password or "mercury",
    db=0,
)
