"""Job engine service: submit / claim / ack / nack + worker loop.

A single JobService instance runs one worker loop (asyncio background task in
the web process) that polls the `derisk_serve_job` table, claims pending jobs
(via JobDao's SKIP LOCKED / SQLite-fallback claim), dispatches to registered
handlers by `job_type`, and ack/nacks on completion. Handlers register
themselves at boot (e.g. knowledge serve's `after_init`).
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional

from derisk.component import SystemApp
from derisk.storage.metadata._base_dao import REQ, RES
from derisk_serve.core import BaseService

from ..api.schemas import ServeRequest, ServeResponse
from ..config import SERVE_SERVICE_COMPONENT_NAME, ServeConfig
from ..models.models import JobDao, JobEntity

logger = logging.getLogger(__name__)

# A handler takes the job row and returns an optional result dict (stored on
# the job row by ack). Raise to trigger nack.
JobHandler = Callable[[JobEntity], Awaitable[Optional[Dict[str, Any]]]]


class Service(BaseService[JobEntity, ServeRequest, ServeResponse]):
    """Persistent job engine service."""

    name = SERVE_SERVICE_COMPONENT_NAME

    def __init__(
        self,
        system_app: SystemApp,
        config: Optional[ServeConfig] = None,
        dao: Optional[JobDao] = None,
    ):
        super().__init__(system_app)
        self._config: Optional[ServeConfig] = config
        self._dao: Optional[JobDao] = dao
        self._handlers: Dict[str, JobHandler] = {}
        self._worker_id = f"{socket.gethostname()}:{os.getpid()}"
        self._running = False
        self._worker_task: Optional[asyncio.Task] = None
        self._in_flight: Dict[str, asyncio.Task] = {}

    # ---- BaseService plumbing ----
    def init_app(self, system_app: SystemApp):
        super().init_app(system_app)
        if self._dao is None:
            self._dao = JobDao(self._config)

    @property
    def dao(self) -> JobDao:
        if self._dao is None:
            self._dao = JobDao(self._config)
        return self._dao

    @property
    def config(self) -> ServeConfig:
        if self._config is None:
            self._config = ServeConfig()
        return self._config

    # ---- handler registry ----
    def register_handler(self, job_type: str, handler: JobHandler) -> None:
        if job_type in self._handlers and self._handlers[job_type] is not handler:
            logger.warning("overwriting existing handler for job_type=%s", job_type)
        self._handlers[job_type] = handler
        logger.info("registered job handler: %s", job_type)

    def handler_types(self) -> List[str]:
        return list(self._handlers.keys())

    # ---- submit / state transitions (thin async wrappers over sync DAO) ----
    async def submit(
        self,
        job_type: str,
        payload: Dict[str, Any],
        *,
        space_slug: Optional[str] = None,
        priority: int = 5,
        max_attempts: Optional[int] = None,
    ) -> str:
        ma = max_attempts if max_attempts is not None else self.config.max_attempts_default
        req = ServeRequest(
            job_type=job_type,
            space_slug=space_slug,
            payload=payload,
            priority=priority,
            max_attempts=ma,
        )
        entity = await asyncio.to_thread(self.dao.submit, req)
        return entity.id

    async def update_result(self, job_id: str, result: Dict[str, Any]) -> None:
        await asyncio.to_thread(self.dao.update_result, job_id, result)

    async def ack(self, job_id: str, result: Optional[Dict[str, Any]]) -> bool:
        return await asyncio.to_thread(self.dao.ack, job_id, result)

    async def nack(self, job_id: str, error: str) -> str:
        return await asyncio.to_thread(self.dao.nack, job_id, error)

    async def renew_lease(self, job_id: str, extend_seconds: int) -> bool:
        return await asyncio.to_thread(
            self.dao.renew_lease, job_id, self._worker_id, extend_seconds
        )

    # ---- listing (sync, for callers already in thread) ----
    def list_jobs(self, **kw) -> List[JobEntity]:
        return self.dao.list_jobs(**kw)

    def list_for_space(self, space_slug: str, limit: int = 50) -> List[JobEntity]:
        return self.dao.list_for_space(space_slug, limit)

    def get(self, job_id: str) -> Optional[JobEntity]:
        return self.dao.get(job_id)

    # ---- worker loop ----
    async def start(self) -> None:
        if self._running:
            return
        if not self._config or not self._config.enabled:
            logger.info("Job engine disabled; worker loop not started")
            return
        if not self._handlers:
            logger.error(
                "Job engine starting with NO handlers registered; "
                "jobs will be nacked. Register handlers before start()."
            )
        self._running = True
        # Reclaim stalled jobs from a previous/crashed run before polling.
        try:
            await asyncio.to_thread(
                self.dao.reclaim_stalled, list(self._handlers.keys()) or ["__none__"],
                datetime.utcnow(),
            )
        except Exception:
            logger.exception("initial reclaim_stalled failed")
        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info(
            "Job engine started (worker=%s, concurrency=%d, poll=%.1fs, lease=%ds, handlers=%s)",
            self._worker_id, self._config.concurrency, self._config.poll_interval_seconds,
            self._config.lease_seconds, list(self._handlers.keys()),
        )

    async def stop(self) -> None:
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except (asyncio.CancelledError, Exception):
                pass
            self._worker_task = None
        # In-flight handler tasks are cancelled; their leases will expire and
        # be reclaimed by another instance or on next start.
        for t in list(self._in_flight.values()):
            t.cancel()
        self._in_flight.clear()
        logger.info("Job engine stopped")

    async def _worker_loop(self) -> None:
        sem = asyncio.Semaphore(self._config.concurrency)
        while self._running:
            # 1. reap finished
            for jid, t in list(self._in_flight.items()):
                if t.done():
                    self._in_flight.pop(jid, None)
            try:
                # 2. reclaim stalled every tick
                if self._handlers:
                    await asyncio.to_thread(
                        self.dao.reclaim_stalled,
                        list(self._handlers.keys()),
                        datetime.utcnow(),
                    )
                # 3. fill up to concurrency
                while (
                    self._running
                    and len(self._in_flight) < self._config.concurrency
                    and self._handlers
                ):
                    job = await asyncio.to_thread(
                        self.dao.claim_next,
                        list(self._handlers.keys()),
                        self._worker_id,
                        self._config.lease_seconds,
                    )
                    if job is None:
                        break
                    await sem.acquire()
                    t = asyncio.create_task(self._run_one(job, sem))
                    self._in_flight[job.id] = t
            except Exception:
                logger.exception("worker loop iteration failed")
            try:
                await asyncio.sleep(self._config.poll_interval_seconds)
            except asyncio.CancelledError:
                break

    async def _run_one(self, job: JobEntity, sem: asyncio.Semaphore) -> None:
        try:
            handler = self._handlers.get(job.job_type)
            if handler is None:
                await self.nack(job.id, f"no handler registered for {job.job_type}")
                return
            renewer = asyncio.create_task(self._renew_loop(job.id))
            try:
                result = await handler(job)
                renewer.cancel()
                await self.ack(job.id, result if isinstance(result, dict) else None)
            except Exception as e:
                renewer.cancel()
                err = f"{type(e).__name__}: {e}"
                logger.exception("job %s (%s) failed", job.id, job.job_type)
                await self.nack(job.id, err)
        finally:
            sem.release()

    async def _renew_loop(self, job_id: str) -> None:
        lease = self._config.lease_seconds
        try:
            while True:
                await asyncio.sleep(max(1.0, lease * 0.4))
                await self.renew_lease(job_id, int(lease * 0.8))
        except asyncio.CancelledError:
            return
        except Exception:
            logger.debug("renew_lease failed for %s", job_id)