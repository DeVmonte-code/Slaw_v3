"""APScheduler glue for the nightly benefit sweep.

Single-process: the scheduler runs in the same uvicorn worker as the
HTTP API. That's intentional for v1 — see ``backend/README.md``'s
"Scheduled sweep" section for the rationale and the Postgres-vs-SQLite
decision. When the project grows past one worker, swap this for an
external scheduler (Celery beat, dedicated cron pod) without touching
the orchestrator in :mod:`engine.sweep`.

Lifecycle:
* Started in the FastAPI lifespan iff ``settings.sweep_enabled``.
* Stopped (gracefully, ``wait=False`` so the lifespan shutdown isn't
  blocked by an in-flight scan) when the app shuts down.

Why ``BackgroundScheduler`` (not ``AsyncIOScheduler``):
* The sweep orchestrator is async, but APScheduler can call sync
  callables that drive their own event loop via :func:`asyncio.run`.
* Using a background-thread scheduler means the FastAPI event loop
  isn't responsible for the scheduler's tick — ``/scan`` latency stays
  unaffected by the nightly job.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .catalog import load_catalog
from .config import settings
from .engine.scan import run_benefit_scan
from .engine.sweep import sweep_all_users_sync

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _job() -> None:
    """Top-level scheduler callable. Catches every exception so a
    transient Anthropic / Qdrant outage doesn't crash the scheduler
    and skip every subsequent night."""
    try:
        summary = sweep_all_users_sync(load_catalog(), scan_fn=run_benefit_scan)
        logger.info("nightly_sweep_summary %s", summary)
    except Exception as exc:
        logger.exception("nightly_sweep_failed err=%s", type(exc).__name__)


def start() -> BackgroundScheduler | None:
    """Start the scheduler if enabled and not already running.

    Idempotent — calling :func:`start` twice returns the same instance.
    """
    global _scheduler
    if not settings.sweep_enabled:
        logger.info("sweep_disabled (set SWEEP_ENABLED=1 to enable)")
        return None
    if _scheduler is not None:
        return _scheduler
    sched = BackgroundScheduler(daemon=True)
    sched.add_job(
        _job,
        trigger=CronTrigger(
            hour=settings.sweep_cron_hour,
            minute=settings.sweep_cron_minute,
        ),
        id="nightly_benefit_sweep",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    sched.start()
    _scheduler = sched
    logger.info(
        "sweep_scheduler_started cron=%02d:%02d",
        settings.sweep_cron_hour, settings.sweep_cron_minute,
    )
    return sched


def stop() -> None:
    """Stop the scheduler if running. Non-blocking shutdown so the
    FastAPI lifespan teardown isn't held up by an in-flight job."""
    global _scheduler
    if _scheduler is None:
        return
    _scheduler.shutdown(wait=False)
    _scheduler = None
    logger.info("sweep_scheduler_stopped")
