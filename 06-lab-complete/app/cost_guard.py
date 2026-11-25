"""Daily budget recorded in Redis as integer microdollars."""

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from redis.exceptions import RedisError

from app.config import settings
from app.redis_client import r


PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006


def _budget_key() -> tuple[str, int]:
    now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return "agent:cost:" + now.strftime("%Y-%m-%d"), max(1, int((tomorrow - now).total_seconds()))


def check_budget() -> None:
    key, _ = _budget_key()
    try:
        spent_micro_usd = int(r.get(key) or 0)
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="Budget store unavailable") from exc
    if spent_micro_usd >= settings.daily_budget_usd * 1_000_000:
        raise HTTPException(status_code=402, detail="Daily budget exhausted")


def record_cost(input_tokens: int, output_tokens: int) -> float:
    cost = (input_tokens * PRICE_INPUT_PER_1K + output_tokens * PRICE_OUTPUT_PER_1K) / 1000
    key, ttl = _budget_key()
    try:
        pipe = r.pipeline(transaction=True)
        pipe.incrby(key, max(1, round(cost * 1_000_000)))
        pipe.expire(key, ttl)
        pipe.execute()
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="Budget store unavailable") from exc
    return cost
