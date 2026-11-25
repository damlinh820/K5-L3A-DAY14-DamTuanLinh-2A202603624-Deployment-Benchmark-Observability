"""Atomic sliding-window rate limit shared by every worker."""

import hashlib
import time
import uuid

from fastapi import HTTPException
from redis.exceptions import RedisError

from app.config import settings
from app.redis_client import r


_CHECK_AND_ADD = r.register_script("""
local key = KEYS[1]
local now = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
redis.call('ZREMRANGEBYSCORE', key, '-inf', now - 60)
local count = redis.call('ZCARD', key)
if count >= limit then
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    return math.max(1, math.ceil(60 - (now - tonumber(oldest[2]))))
end
redis.call('ZADD', key, now, ARGV[3])
redis.call('EXPIRE', key, 61)
return 0
""")


def check_rate_limit(key: str) -> None:
    redis_key = "agent:rate:" + hashlib.sha256(key.encode()).hexdigest()
    try:
        retry_after = int(_CHECK_AND_ADD(keys=[redis_key], args=[time.time(), settings.rate_limit_per_minute, uuid.uuid4().hex]))
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="Rate limiter unavailable") from exc
    if retry_after:
        raise HTTPException(status_code=429, detail="Rate limit exceeded", headers={"Retry-After": str(retry_after)})
