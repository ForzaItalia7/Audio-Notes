"""PostgreSQL-backed queue for the local app; one provider request at a time."""
import logging
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from fastapi import HTTPException
from .database import engine
from .models import Upload, ProcessingJob
from .processing import start_transcription, check_transcription, generate_upload_notes, UPLOADS_DIR
from .storage import exists
from pathlib import Path

ACTIVE = ("queued", "running")
LOCK_ID = 70184239
logger = logging.getLogger(__name__)


def now():
    return datetime.now(timezone.utc)


def enqueue_job(db, upload_id, kind, language_code="hi-IN"):
    # Serialize double clicks and deletion against this upload.
    upload = db.query(Upload).filter_by(id=upload_id).with_for_update().first()
    if upload is None:
        raise HTTPException(404, "Upload not found.")
    job = db.query(ProcessingJob).filter_by(upload_id=upload_id, kind=kind).first()
    if job and job.status in ACTIVE:
        return {"id": upload_id, "status": job.status}
    key = "GNANI_API_KEY" if kind == "transcription" else "GEMINI_API_KEY"
    if not os.getenv(key):
        raise HTTPException(503, f"{key} is not configured. Restart the backend after saving .env.")
    if kind == "notes" and not upload.transcript:
        raise HTTPException(409, "Transcribe this upload before generating notes.")
    if kind == "transcription":
        if upload.status == "completed" and upload.transcript:
            return {"id": upload_id, "status": "completed"}
        try:
            audio_exists = exists(upload.stored_at, UPLOADS_DIR)
        except Exception as error:
            raise HTTPException(503, "Could not reach audio storage. Check the bucket configuration.") from error
        if not audio_exists:
            raise HTTPException(404, "Audio file was not found.")
        if not upload.stored_at.startswith("s3://") and Path(upload.stored_at).stat().st_size > 10 * 1024 * 1024:
            raise HTTPException(413, "Gnani direct uploads must be 10 MB or smaller.")
        if upload.status == "failed":
            upload.gnani_job_id = None
        upload.status = "processing"
    if job is None:
        job = ProcessingJob(upload_id=upload_id, kind=kind)
        db.add(job)
    job.status = "queued"
    job.language_code = language_code
    job.error = None
    job.failures = 0
    job.next_run_at = now()
    db.commit()
    return {"id": upload_id, "status": "queued"}


def recover_jobs(db):
    # Never silently repeat an interrupted generative request or uncertain upload.
    for job in db.query(ProcessingJob).filter_by(status="running").all():
        upload = db.get(Upload, job.upload_id)
        if job.kind == "transcription" and upload and upload.gnani_job_id:
            job.next_run_at = now()
        else:
            job.status = "failed"
            job.error = "Processing was interrupted by a backend restart. Retry when ready."
            if upload and job.kind == "transcription":
                upload.status = "failed"
    # Pick up transcription work submitted before the queue was introduced.
    for upload in db.query(Upload).filter_by(status="processing").all():
        if not db.query(ProcessingJob).filter_by(upload_id=upload.id, kind="transcription").first():
            if upload.gnani_job_id:
                db.add(ProcessingJob(upload_id=upload.id, kind="transcription", status="running"))
            else:
                upload.status = "failed"
    db.commit()


def process_next(db):
    job = db.query(ProcessingJob).filter(
        ProcessingJob.status.in_(ACTIVE), ProcessingJob.next_run_at <= now()
    ).order_by(ProcessingJob.next_run_at, ProcessingJob.id).first()
    if job is None:
        return
    job_id = job.id
    upload = db.get(Upload, job.upload_id)
    job.status = "running"
    db.commit()
    try:
        if job.kind == "notes":
            generate_upload_notes(job.upload_id, db)
            job.status = "completed"
        else:
            if not upload.gnani_job_id:
                start_transcription(job.upload_id, SimpleNamespace(language_code=job.language_code), db)
                result = {"status": "processing"}
            else:
                result = check_transcription(job.upload_id, db)
            if result["status"] in ("completed", "failed"):
                job.status = result["status"]
                job.error = "Gnani could not transcribe this audio. Retry or choose another file." if job.status == "failed" else None
            else:
                job.next_run_at = now() + timedelta(seconds=10)
        job.failures = 0
        if job.status != "failed":
            job.error = None
        db.commit()
    except SQLAlchemyError:
        # Reacquire leadership before doing more work after a database failure.
        # A reconnect may have lost the session-level advisory lock.
        raise
    except Exception as error:
        db.rollback()
        job = db.get(ProcessingJob, job_id)
        upload = db.get(Upload, job.upload_id)
        detail = str(error.detail) if isinstance(error, HTTPException) else "Processing failed unexpectedly. Please retry."
        # Checking an existing remote job can safely be retried; creation cannot.
        if job.kind == "transcription" and upload and upload.gnani_job_id and job.failures < 5:
            job.failures += 1
            job.next_run_at = now() + timedelta(seconds=30)
            job.error = "Waiting to reconnect to the transcription service."
        else:
            job.status = "failed"
            job.error = detail
            if job.kind == "transcription" and upload:
                upload.status = "failed"
        db.commit()
        # Avoid logging credentials or transcript-bearing provider responses.
        logger.warning("Job %s encountered %s", job_id, type(error).__name__)


def worker_loop(stop):
    while not stop.is_set():
        try:
            # Session-level lock survives commits. Bind the worker to that same
            # connection so a lost DB connection cannot leave a second worker running.
            with engine.connect() as connection:
                acquired = connection.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": LOCK_ID}).scalar()
                connection.commit()
                if acquired:
                    try:
                        with Session(bind=connection) as db:
                            recover_jobs(db)
                        while not stop.is_set():
                            with Session(bind=connection) as db:
                                process_next(db)
                            stop.wait(2)
                    finally:
                        if not connection.invalidated:
                            connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": LOCK_ID})
                            connection.commit()
        except Exception as error:
            logger.warning("Background worker reconnecting after %s", type(error).__name__)
        stop.wait(3)
