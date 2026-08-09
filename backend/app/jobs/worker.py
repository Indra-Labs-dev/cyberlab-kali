from rq import Worker

from app.jobs.queue import get_redis_connection

if __name__ == "__main__":
    connection = get_redis_connection()
    worker = Worker(["default"], connection=connection)
    worker.work()
