"""
/health — checks DB, stream connection, and source connector.
/scheduler/jobs — list scheduled jobs and next run times.
"""
from fastapi import APIRouter
from sqlalchemy import text

from services.backend.app.db.session import engine
from services.backend.app.stream.manager import stream_manager, StreamState

health_router = APIRouter(tags=["ops"])
scheduler_router = APIRouter(prefix="/scheduler", tags=["ops"])

# Scheduler instance injected at startup
_scheduler = None


def set_scheduler(scheduler) -> None:
    global _scheduler
    _scheduler = scheduler


@health_router.get("/health")
async def health():
    """
    Healthy: DB reachable, stream connected.
    Degraded: DB reachable, stream down (fetch still operational).
    Unhealthy: DB unreachable.
    """
    db_ok = False
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:
        return {
            "status": "unhealthy",
            "db": False,
            "stream": stream_manager.state.value,
            "error": str(exc),
        }

    stream_state = stream_manager.state
    stream_ok = stream_state == StreamState.CONNECTED

    return {
        "status": "healthy" if stream_ok else "degraded",
        "db": db_ok,
        "stream": stream_state.value,
        "stream_symbols": len(stream_manager.subscribed_symbols),
    }


@scheduler_router.get("/jobs")
async def list_jobs():
    """List scheduled fetch jobs and next run times."""
    if _scheduler is None:
        return {"jobs": [], "error": "Scheduler not initialised."}

    jobs = []
    for job in _scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger),
        })
    return {"jobs": jobs}
