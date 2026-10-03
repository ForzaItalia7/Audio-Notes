import os
from typing import Literal

from fastapi import FastAPI, File, UploadFile, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pathlib import Path
from .database import engine
from . import models
from sqlalchemy.orm import Session
from .database import get_db
from .models import Upload
from uuid import uuid4

from contextlib import asynccontextmanager
from threading import Event, Thread
import asyncio
from .jobs import enqueue_job, worker_loop, ACTIVE
from .models import ProcessingJob
from .schema import require_current_schema
from .storage import store_audio, remove_audio, remove_local_file


@asynccontextmanager
async def lifespan(app: FastAPI):
    require_current_schema(engine)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    stop = Event()
    worker = Thread(target=worker_loop, args=(stop,), daemon=True, name="audio-jobs")
    worker.start()
    try:
        yield
    finally:
        stop.set()
        await asyncio.to_thread(worker.join, 5)


app = FastAPI(lifespan=lifespan)


class TranscribeRequest(BaseModel):
    language_code: Literal[
        "bn-IN", "en-IN", "hi-IN", "kn-IN",
        "ml-IN", "mr-IN", "ta-IN", "te-IN",
    ] = "hi-IN"

UPLOADS_DIR = Path(__file__).resolve().parent.parent / "uploads"
MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE_BYTES", str(2 * 1024 * 1024 * 1024)))
UPLOAD_SIZE_LIMIT = MAX_UPLOAD_SIZE if os.getenv("AUDIO_BUCKET") else min(MAX_UPLOAD_SIZE, 10 * 1024 * 1024)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv(
        "FRONTEND_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
    ).split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers={"*"},
)

@app.get("/")
def read_root():
    return {"message": "Gnani Audio Notes API is running"}
@app.get("/uploads")
def list_uploads(db: Session = Depends(get_db)):
    jobs = {(job.upload_id, job.kind): job for job in db.query(ProcessingJob).all()}
    records = db.query(Upload).order_by(Upload.created_at.desc()).all()
    result = []
    for record in records:
        data = {column.name: getattr(record, column.name) for column in Upload.__table__.columns}
        for kind in ("transcription", "notes"):
            job = jobs.get((record.id, kind))
            data[f"{kind}_job_status"] = job.status if job else None
            data[f"{kind}_error"] = job.error if job else None
        result.append(data)
    return result


@app.post("/uploads/{upload_id}/transcribe", status_code=202)
def queue_transcription(upload_id: int, request: TranscribeRequest, db: Session = Depends(get_db)):
    return enqueue_job(db, upload_id, "transcription", request.language_code)


@app.post("/uploads/{upload_id}/notes", status_code=202)
def queue_notes(upload_id: int, db: Session = Depends(get_db)):
    return enqueue_job(db, upload_id, "notes")


@app.get("/uploads/{upload_id}/transcription")
def transcription_status(upload_id: int, db: Session = Depends(get_db)):
    record = db.get(Upload, upload_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Upload not found.")
    return {"id": record.id, "status": record.status, "transcript": record.transcript}


@app.delete("/uploads/{upload_id}")
def delete_upload(upload_id: int, db: Session = Depends(get_db)):
    upload_record = db.query(Upload).filter_by(id=upload_id).with_for_update().first()
    if upload_record is None:
        raise HTTPException(status_code=404, detail="Upload not found.")

    if db.query(ProcessingJob).filter(ProcessingJob.upload_id == upload_id, ProcessingJob.status.in_(ACTIVE)).first():
        raise HTTPException(status_code=409, detail="Wait for processing to finish before deleting this upload.")
    db.query(ProcessingJob).filter_by(upload_id=upload_id).delete()
    db.delete(upload_record)
    db.commit()
    remove_audio(upload_record.stored_at)
    return {"id": upload_id, "deleted": True}


@app.post("/uploads")
async def create_upload(audio: UploadFile = File(...),
                        db: Session = Depends(get_db),
                        ):
    if audio.content_type and not audio.content_type.startswith("audio/"):
        raise HTTPException(status_code=415, detail="Please upload an audio file.")

    filename = audio.filename or "uploaded-audio"
    safe_filename = Path(filename).name
    stored_filename = f"{uuid4().hex}_{safe_filename}"
    destination = UPLOADS_DIR / stored_filename

    try:
        total_size = 0
        with destination.open("wb") as file_buffer:
            while chunk := await audio.read(1024 * 1024):
                total_size += len(chunk)
                if total_size > UPLOAD_SIZE_LIMIT:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Audio files must be {UPLOAD_SIZE_LIMIT // (1024 * 1024)} MB or smaller with the current storage setup.",
                    )
                file_buffer.write(chunk)

        storage_path = store_audio(destination, stored_filename, audio.content_type)
        if str(storage_path).startswith("s3://"):
            destination.unlink(missing_ok=True)

        upload_record = Upload(
            filename=safe_filename,
            content_type=audio.content_type,
            stored_at=storage_path,
        )
        db.add(upload_record)
        db.commit()
        db.refresh(upload_record)
    except HTTPException:
        db.rollback()
        remove_local_file(destination)
        raise
    except Exception as error:
        db.rollback()
        remove_local_file(destination)
        raise HTTPException(
            status_code=500,
            detail="Upload could not be saved.",
        ) from error

    return {
        "id": upload_record.id,
        "filename": safe_filename,
        "content_type": audio.content_type,
        "stored_at": str(storage_path),
        "created_at": upload_record.created_at,
    }
