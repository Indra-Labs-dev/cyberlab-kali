import json

from app.jobs.queue import get_redis_connection


def channel_for_job(job_id: str) -> str:
    return f"cyberlab:job:{job_id}"


def publish_job_update(job_id: str, payload: dict) -> None:
    connection = get_redis_connection()
    connection.publish(channel_for_job(job_id), json.dumps(payload, default=str))
