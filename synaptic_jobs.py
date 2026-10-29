"""Durable job journal for syntheses dispatched by Synaptic Model Manager.

Problem: the Manager reserves the shared GPU/unified memory, then calls `/tts`
over an SSH tunnel. If that transport dies (timeout, tunnel restart, Manager
restart) the synthesis keeps running in an executor thread here, and the
Manager cannot tell whether it finished, so it must keep the reservation
"uncertain" forever.

Fix: the Manager sends `X-Synaptic-Job-Id`. This module records the job on
disk *before* synthesis starts and records the result from the worker
thread's completion callback, independent of the HTTP connection. The
Manager can then ask `GET /api/jobs/{id}`:

- `running` with the current `boot_id`: still computing, keep the reservation.
- `succeeded`: fetch `/api/jobs/{id}/audio`, release the reservation.
- `failed`: release and fail.
- 404 or a `running` record from another `boot_id`: the server restarted, so the
  computation is gone; release safely.

`SYNAPTIC_REQUIRE_JOB_ID=1` (env) refuses synthesis without that header, so
nothing (e.g. the bundled Web UI) can generate outside the shared reservation.
"""

import concurrent.futures
import hashlib
import json
import os
import re
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

JOB_ID_HEADER = "X-Synaptic-Job-Id"
BOOT_ID = uuid.uuid4().hex
BOOTED_AT = time.time()
RETENTION_S = float(os.environ.get("SYNAPTIC_JOBS_RETENTION_H", "48")) * 3600
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_LOCK = threading.Lock()
# Own executor: a running synthesis must outlive a cancelled request
# (asyncio.wrap_future cannot cancel a thread that already started).
_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="synaptic-tts")


def jobs_dir() -> Path:
    path = Path(os.environ.get("SYNAPTIC_JOBS_DIR", Path(__file__).resolve().parent / "synaptic_jobs"))
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def require_job_id() -> bool:
    return os.environ.get("SYNAPTIC_REQUIRE_JOB_ID", "0").lower() in ("1", "true", "yes")


def valid_job_id(job_id: str | None) -> bool:
    return bool(job_id and _ID_RE.match(job_id))


def _meta_path(job_id: str) -> Path:
    return jobs_dir() / f"{job_id}.json"


def _audio_path(job_id: str, ext: str) -> Path:
    return jobs_dir() / f"{job_id}.{ext}"


def _write_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _save(record: dict[str, Any]) -> None:
    _write_atomic(_meta_path(record["job_id"]), json.dumps(record).encode())


def get(job_id: str) -> dict[str, Any] | None:
    try:
        record = json.loads(_meta_path(job_id).read_text())
    except (FileNotFoundError, ValueError):
        return None
    if record.get("status") == "running" and record.get("boot_id") != BOOT_ID:
        # The process that owned it is gone: the computation cannot finish.
        record["status"] = "lost"
    return record


def begin(job_id: str, output_format: str) -> dict[str, Any] | None:
    """Claim `job_id`. Returns None when claimed, or the existing record when
    it already succeeded or is still running in this process."""
    with _LOCK:
        existing = get(job_id)
        if existing and existing["status"] in ("succeeded", "running"):
            return existing
        _save({"job_id": job_id, "status": "running", "boot_id": BOOT_ID, "format": output_format,
                "started_at": time.time()})
    return None


def finish(job_id: str, audio: bytes, output_format: str) -> None:
    _write_atomic(_audio_path(job_id, output_format), audio)
    with _LOCK:
        record = get(job_id) or {"job_id": job_id, "boot_id": BOOT_ID}
        record.update(status="succeeded", format=output_format, bytes=len(audio),
                      sha256=hashlib.sha256(audio).hexdigest(), finished_at=time.time())
        _save(record)


def fail(job_id: str, error: str) -> None:
    with _LOCK:
        record = get(job_id) or {"job_id": job_id, "boot_id": BOOT_ID}
        record.update(status="failed", error=error[:500], finished_at=time.time())
        _save(record)


def audio(job_id: str) -> bytes | None:
    record = get(job_id)
    if not record or record.get("status") != "succeeded":
        return None
    path = _audio_path(job_id, record.get("format", "wav"))
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return None
    if hashlib.sha256(data).hexdigest() != record.get("sha256"):
        return None
    return data


def submit(job_id: str | None, output_format: str, work: Callable[[], bytes]) -> concurrent.futures.Future:
    """Run `work` on the journal executor; record the outcome when it ends,
    whether or not anyone is still awaiting the HTTP response."""
    future = _EXECUTOR.submit(work)
    if job_id:
        def _record(done: concurrent.futures.Future) -> None:
            exc = done.exception()
            if exc is None:
                finish(job_id, done.result(), output_format)
            else:
                detail = getattr(exc, "detail", None) or str(exc)
                fail(job_id, f"{type(exc).__name__}: {detail}")
        future.add_done_callback(_record)
    return future


def cleanup(now: float | None = None) -> int:
    cutoff = (now or time.time()) - RETENTION_S
    removed = 0
    for path in jobs_dir().iterdir():
        try:
            if path.stat().st_mtime < cutoff and not path.name.startswith("."):
                path.unlink()
                removed += 1
        except OSError:
            pass
    return removed
