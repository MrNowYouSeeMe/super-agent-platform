import json
import uuid

from redis.asyncio import Redis

from app.config import get_settings
from app.schemas import (
    AnalysisEvent,
    AnalysisRequest,
    AnalysisResult,
    AnalysisSnapshot,
    JobStatus,
)

settings = get_settings()


class RedisJobStore:
    def __init__(self, redis: Redis):
        self.redis = redis

    @staticmethod
    def job_key(analysis_id: str) -> str:
        return f"superagent:analysis:{analysis_id}"

    @staticmethod
    def events_key(analysis_id: str) -> str:
        return f"superagent:analysis:{analysis_id}:events"

    async def create_and_enqueue(self, payload: AnalysisRequest) -> str:
        analysis_id = f"analysis_{uuid.uuid4().hex[:16]}"
        key = self.job_key(analysis_id)
        await self.redis.hset(
            key,
            mapping={
                "analysis_id": analysis_id,
                "status": JobStatus.queued.value,
                "payload": payload.model_dump_json(),
                "result": "",
                "error": "",
            },
        )
        await self.redis.expire(key, settings.job_ttl_seconds)
        await self.redis.expire(self.events_key(analysis_id), settings.job_ttl_seconds)
        await self.redis.lpush(settings.analysis_queue, analysis_id)
        return analysis_id

    async def pop_job(self, timeout: int = 5) -> str | None:
        item = await self.redis.brpop(settings.analysis_queue, timeout=timeout)
        if item is None:
            return None
        return item[1]

    async def get_payload(self, analysis_id: str) -> AnalysisRequest | None:
        value = await self.redis.hget(self.job_key(analysis_id), "payload")
        if not value:
            return None
        return AnalysisRequest.model_validate_json(value)

    async def set_status(self, analysis_id: str, status: JobStatus) -> None:
        await self.redis.hset(
            self.job_key(analysis_id),
            mapping={"status": status.value},
        )

    async def append_event(self, analysis_id: str, event: AnalysisEvent) -> None:
        key = self.events_key(analysis_id)
        await self.redis.rpush(key, event.model_dump_json())
        await self.redis.expire(key, settings.job_ttl_seconds)

    async def complete(self, analysis_id: str, result: AnalysisResult) -> None:
        await self.redis.hset(
            self.job_key(analysis_id),
            mapping={
                "status": JobStatus.completed.value,
                "result": result.model_dump_json(),
                "error": "",
            },
        )

    async def fail(self, analysis_id: str, message: str) -> None:
        await self.redis.hset(
            self.job_key(analysis_id),
            mapping={
                "status": JobStatus.failed.value,
                "error": message,
            },
        )

    async def get_snapshot(self, analysis_id: str) -> AnalysisSnapshot | None:
        values = await self.redis.hgetall(self.job_key(analysis_id))
        if not values:
            return None
        raw_events = await self.redis.lrange(self.events_key(analysis_id), 0, -1)
        events = [AnalysisEvent.model_validate_json(value) for value in raw_events]
        result = (
            AnalysisResult.model_validate_json(values["result"])
            if values.get("result")
            else None
        )
        return AnalysisSnapshot(
            analysis_id=analysis_id,
            status=JobStatus(values["status"]),
            events=events,
            result=result,
            error=values.get("error") or None,
        )
