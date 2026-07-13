"""Job engine database entity + DAO.

Generic persistent-job table shared across all job_types. The DAO implements
claim/consume:
- PG/MySQL: SELECT ... FOR UPDATE SKIP LOCKED (multi-instance safe)
- SQLite:   atomic conditional UPDATE (single-writer, race-free via
            `AND status='pending'` guard), since SQLite has no SKIP LOCKED
            and FOR UPDATE is a no-op there.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import Column, DateTime, Integer, String, Text, JSON, and_, func

from derisk.storage.metadata import BaseDao, Model

from ..api.schemas import ServeRequest, ServeResponse
from ..config import SERVER_APP_TABLE_NAME, ServeConfig

logger = logging.getLogger(__name__)


class JobEntity(Model):
    """Database entity for persistent jobs (table `derisk_serve_job`)."""

    __tablename__ = SERVER_APP_TABLE_NAME

    id = Column(String(64), primary_key=True)
    job_type = Column(String(64), nullable=False, index=True)
    space_slug = Column(String(128), nullable=True, index=True)
    payload = Column(JSON, nullable=False, default=dict)
    status = Column(
        String(16), nullable=False, default="pending", index=True
    )  # pending | running | done | failed
    priority = Column(Integer, nullable=False, default=5)
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    claimed_by = Column(String(128), nullable=True)
    claimed_at = Column(DateTime, nullable=True)
    lease_until = Column(DateTime, nullable=True, index=True)
    last_error = Column(Text, nullable=True)
    result = Column(JSON, nullable=True)
    gmt_created = Column(
        DateTime, nullable=False, default=datetime.now, name="gmt_create"
    )
    gmt_modified = Column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now,
        name="gmt_modified",
    )


class JobDao(BaseDao[JobEntity, ServeRequest, ServeResponse]):
    """DAO with claim/consume primitives."""

    def __init__(self, serve_config: Optional[ServeConfig] = None):
        super().__init__()
        self._serve_config = serve_config
        # Detect SKIP LOCKED support once. SQLite has no row locks; the global
        # `db` singleton's dialect is what matters here.
        self._supports_skip_locked = self._detect_skip_locked()

    def _detect_skip_locked(self) -> bool:
        try:
            sess = self.get_raw_session()
            dialect = sess.bind.dialect.name if hasattr(sess, "bind") and sess.bind else None
            sess.close()
        except Exception:
            dialect = None
        return dialect in ("postgresql", "mysql")

    # ---- BaseDao plumbing -------------------------------------------------

    def from_request(self, request: ServeRequest) -> JobEntity:
        return JobEntity(
            id=f"job_{uuid.uuid4().hex[:16]}",
            job_type=request.job_type,
            space_slug=request.space_slug,
            payload=request.payload,
            status="pending",
            priority=request.priority,
            attempts=0,
            max_attempts=request.max_attempts,
        )

    def to_request(self, entity: JobEntity) -> ServeRequest:
        return ServeRequest(
            job_type=entity.job_type,
            space_slug=entity.space_slug,
            payload=entity.payload or {},
            priority=entity.priority,
            max_attempts=entity.max_attempts,
        )

    def to_response(self, entity: JobEntity) -> ServeResponse:
        def _dt(v):
            return v.strftime("%Y-%m-%d %H:%M:%S") if v else None

        return ServeResponse(
            id=entity.id,
            job_type=entity.job_type,
            space_slug=entity.space_slug,
            payload=entity.payload or {},
            status=entity.status,
            priority=entity.priority,
            attempts=entity.attempts,
            max_attempts=entity.max_attempts,
            claimed_by=entity.claimed_by,
            claimed_at=_dt(entity.claimed_at),
            lease_until=_dt(entity.lease_until),
            last_error=entity.last_error,
            result=entity.result,
            gmt_created=_dt(entity.gmt_created),
            gmt_modified=_dt(entity.gmt_modified),
        )

    # ---- claim / consume --------------------------------------------------

    def submit(self, request: ServeRequest) -> JobEntity:
        """Insert a new pending job row and return it."""
        entity = self.from_request(request)
        with self.session() as session:
            session.add(entity)
            session.flush()
            session.refresh(entity)
            session.expunge(entity)
        return entity

    def claim_next(
        self,
        job_types: List[str],
        worker_id: str,
        lease_seconds: int,
    ) -> Optional[JobEntity]:
        """Atomically claim one pending job of the given types.

        PG/MySQL: SELECT ... FOR UPDATE SKIP LOCKED + UPDATE.
        SQLite:   atomic conditional UPDATE (no SKIP LOCKED support).
        Returns the claimed entity (status=running) or None.
        """
        if not job_types:
            return None
        now = datetime.utcnow()
        lease = now + timedelta(seconds=lease_seconds)
        if self._supports_skip_locked:
            return self._claim_skip_locked(job_types, worker_id, now, lease)
        return self._claim_sqlite(job_types, worker_id, now, lease)

    def _claim_skip_locked(
        self, job_types, worker_id, now, lease,
    ) -> Optional[JobEntity]:
        with self.session(commit=False) as session:
            row = (
                session.query(JobEntity)
                .filter(
                    JobEntity.job_type.in_(job_types),
                    JobEntity.status == "pending",
                )
                .order_by(JobEntity.priority.asc(), JobEntity.gmt_created.asc())
                .limit(1)
                .with_for_update(skip_locked=True)
                .first()
            )
            if row is None:
                return None
            row.status = "running"
            row.claimed_by = worker_id
            row.claimed_at = now
            row.lease_until = lease
            row.attempts = (row.attempts or 0) + 1
            session.commit()
            session.expunge(row)
            return row

    def _claim_sqlite(
        self, job_types, worker_id, now, lease,
    ) -> Optional[JobEntity]:
        """Atomic conditional UPDATE — race-free under SQLite's single writer.

        The `AND status='pending'` guard in the WHERE ensures that if two
        coroutines both selected the same candidate, only the first UPDATE
        flips it (rowcount=1); the second affects 0 rows and returns None.
        """
        with self.session() as session:
            # Pick a candidate id first (read).
            candidate = (
                session.query(JobEntity.id)
                .filter(
                    JobEntity.job_type.in_(job_types),
                    JobEntity.status == "pending",
                )
                .order_by(JobEntity.priority.asc(), JobEntity.gmt_created.asc())
                .limit(1)
                .first()
            )
            if candidate is None:
                return None
            candidate_id = candidate[0]
            updated = (
                session.query(JobEntity)
                .filter(
                    JobEntity.id == candidate_id,
                    JobEntity.status == "pending",  # race guard
                )
                .update(
                    {
                        "status": "running",
                        "claimed_by": worker_id,
                        "claimed_at": now,
                        "lease_until": lease,
                        "attempts": JobEntity.attempts + 1,
                    },
                    synchronize_session=False,
                )
            )
            if not updated:
                return None
            row = session.query(JobEntity).filter(JobEntity.id == candidate_id).first()
            session.expunge(row) if row else None
            return row

    def reclaim_stalled(self, job_types: List[str], now: datetime) -> int:
        """Flip running jobs whose lease expired back to pending."""
        if not job_types:
            return 0
        with self.session() as session:
            updated = (
                session.query(JobEntity)
                .filter(
                    JobEntity.job_type.in_(job_types),
                    JobEntity.status == "running",
                    JobEntity.lease_until.isnot(None),
                    JobEntity.lease_until < now,
                )
                .update(
                    {
                        "status": "pending",
                        "claimed_by": None,
                        "claimed_at": None,
                        "lease_until": None,
                    },
                    synchronize_session=False,
                )
            )
            return updated

    def ack(self, job_id: str, result: Optional[Dict[str, Any]]) -> bool:
        with self.session() as session:
            updated = (
                session.query(JobEntity)
                .filter(JobEntity.id == job_id, JobEntity.status == "running")
                .update(
                    {
                        "status": "done",
                        "claimed_by": None,
                        "claimed_at": None,
                        "lease_until": None,
                        "result": result,
                    },
                    synchronize_session=False,
                )
            )
            return updated > 0

    def nack(self, job_id: str, error: str) -> str:
        """On failure: increment already done at claim time; flip to pending
        if attempts < max_attempts else failed. Returns 'pending' or 'failed'."""
        with self.session(commit=False) as session:
            row = (
                session.query(JobEntity)
                .filter(JobEntity.id == job_id)
                .with_for_update()
                .first()
            )
            if row is None:
                return "failed"
            next_status = "failed" if row.attempts >= row.max_attempts else "pending"
            row.status = next_status
            row.claimed_by = None
            row.claimed_at = None
            row.lease_until = None
            row.last_error = (error or "")[:4000]
            session.commit()
            return next_status

    def renew_lease(self, job_id: str, worker_id: str, extend_seconds: int) -> bool:
        with self.session() as session:
            updated = (
                session.query(JobEntity)
                .filter(
                    JobEntity.id == job_id,
                    JobEntity.status == "running",
                    JobEntity.claimed_by == worker_id,
                )
                .update(
                    {"lease_until": datetime.utcnow() + timedelta(seconds=extend_seconds)},
                    synchronize_session=False,
                )
            )
            return updated > 0

    def update_result(self, job_id: str, result: Dict[str, Any]) -> None:
        """Write intermediate progress (e.g. phase) into result without
        changing status. Used by handlers to report sub-state."""
        with self.session() as session:
            row = session.query(JobEntity).filter(JobEntity.id == job_id).first()
            if row is None:
                return
            merged = dict(row.result or {})
            merged.update(result)
            row.result = merged

    def retry(self, job_id: str) -> Optional[JobEntity]:
        """Admin retry: reset a failed/done job back to pending."""
        with self.session(commit=False) as session:
            row = (
                session.query(JobEntity)
                .filter(JobEntity.id == job_id)
                .with_for_update()
                .first()
            )
            if row is None:
                return None
            row.status = "pending"
            row.claimed_by = None
            row.claimed_at = None
            row.lease_until = None
            row.last_error = None
            session.commit()
            session.expunge(row)
            return row

    def cancel(self, job_id: str) -> bool:
        """Admin cancel: mark a pending job failed so the worker skips it.
        Running jobs are left alone (let lease expire)."""
        with self.session() as session:
            updated = (
                session.query(JobEntity)
                .filter(JobEntity.id == job_id, JobEntity.status == "pending")
                .update(
                    {"status": "failed", "last_error": "cancelled by admin"},
                    synchronize_session=False,
                )
            )
            return updated > 0

    def delete(self, job_id: str) -> bool:
        with self.session() as session:
            deleted = (
                session.query(JobEntity)
                .filter(JobEntity.id == job_id)
                .delete(synchronize_session=False)
            )
            return deleted > 0

    # ---- queries (admin / listing) ---------------------------------------

    def get(self, job_id: str) -> Optional[JobEntity]:
        with self.session(commit=False) as session:
            row = session.query(JobEntity).filter(JobEntity.id == job_id).first()
            if row:
                session.expunge(row)
            return row

    def list_jobs(
        self,
        *,
        job_type: Optional[str] = None,
        space_slug: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[JobEntity]:
        with self.session(commit=False) as session:
            q = session.query(JobEntity)
            if job_type:
                q = q.filter(JobEntity.job_type == job_type)
            if space_slug:
                q = q.filter(JobEntity.space_slug == space_slug)
            if status:
                q = q.filter(JobEntity.status == status)
            q = q.order_by(JobEntity.gmt_created.desc()).limit(limit).offset(offset)
            rows = q.all()
            for r in rows:
                session.expunge(r)
            return rows

    def count(
        self,
        *,
        job_type: Optional[str] = None,
        space_slug: Optional[str] = None,
        status: Optional[str] = None,
    ) -> int:
        with self.session(commit=False) as session:
            q = session.query(func.count(JobEntity.id))
            if job_type:
                q = q.filter(JobEntity.job_type == job_type)
            if space_slug:
                q = q.filter(JobEntity.space_slug == space_slug)
            if status:
                q = q.filter(JobEntity.status == status)
            return int(q.scalar() or 0)

    def list_for_space(self, space_slug: str, limit: int = 50) -> List[JobEntity]:
        return self.list_jobs(space_slug=space_slug, limit=limit)

    def stats(self) -> Dict[str, Any]:
        with self.session(commit=False) as session:
            rows = (
                session.query(
                    JobEntity.job_type,
                    JobEntity.status,
                    func.count(JobEntity.id),
                )
                .group_by(JobEntity.job_type, JobEntity.status)
                .all()
            )
        by_status: Dict[str, int] = {}
        by_type: Dict[str, int] = {}
        by_type_status: Dict[str, Dict[str, int]] = {}
        total = 0
        for job_type, status, cnt in rows:
            cnt = int(cnt)
            total += cnt
            by_status[status] = by_status.get(status, 0) + cnt
            by_type[job_type] = by_type.get(job_type, 0) + cnt
            by_type_status.setdefault(job_type, {})[status] = cnt
        return {
            "total": total,
            "by_status": by_status,
            "by_type": by_type,
            "by_type_status": by_type_status,
        }