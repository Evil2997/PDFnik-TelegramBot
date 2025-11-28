from faststream.redis import Redis
from main_app.core.constants import REDIS_URL

redis = Redis.from_url(REDIS_URL)
