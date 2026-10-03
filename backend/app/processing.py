import os
import json
from pathlib import Path
from types import SimpleNamespace
from fastapi import HTTPException
from sqlalchemy.orm import Session
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from .models import Upload
from .prompts import NOTES_PROMPT
from .storage import transcription_url

UPLOADS_DIR = Path(__file__).resolve().parent.parent / "uploads"
TranscribeRequest = SimpleNamespace

def start_transcription(
    upload_id: int,
    request: TranscribeRequest,
    db: Session,
):
    upload_record = db.get(Upload, upload_id)
    if upload_record is None:
        raise HTTPException(status_code=404, detail="Upload not found.")

    api_key = os.getenv("GNANI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="Gnani API key is not configured.")

    if upload_record.gnani_job_id and upload_record.status != "failed":
        return {
            "id": upload_record.id,
            "status": upload_record.status,
            "job_id": upload_record.gnani_job_id,
        }
    if upload_record.status == "failed":
        upload_record.gnani_job_id = None
        upload_record.transcript = None

    audio_path = Path(upload_record.stored_at).resolve()
    cloud_url = transcription_url(upload_record.stored_at)
    is_cloud = cloud_url is not None
    if not is_cloud:
        try:
            audio_path.relative_to(UPLOADS_DIR.resolve())
        except ValueError as error:
            raise HTTPException(status_code=400, detail="Upload path is invalid.") from error
    if not is_cloud and not audio_path.is_file():
        raise HTTPException(status_code=404, detail="Audio file was not found.")
    if not is_cloud and audio_path.stat().st_size > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail="Gnani Batch STT direct uploads must be 10 MB or smaller.",
        )

    upload_record.status = "processing"
    try:
        batch_url = "https://api.vachana.ai/stt/v3/batch/jobs"
        headers = {"X-API-Key-ID": api_key}
        config = {
            "model": "gnani-prisma-v2.5",
            "language_code": request.language_code,
            "mode": "transcribe",
            "with_diarization": False,
            "is_multi_channel": False,
        }
        if is_cloud:
            create_response = requests.post(
                batch_url,
                headers=headers,
                json={"config": config, "source": {
                    "type": "cloud_storage", "auth": {"mode": "public"}, "paths": [cloud_url],
                }},
                timeout=60,
            )
        else:
            with audio_path.open("rb") as audio_file:
                create_response = requests.post(
                    batch_url,
                    headers=headers,
                    files={
                        "config": (None, json.dumps(config), "application/json"),
                        "files": (
                            audio_path.name,
                            audio_file,
                            upload_record.content_type or "application/octet-stream",
                        ),
                    },
                    timeout=120,
                )
        create_response.raise_for_status()
        job_id = create_response.json()["job_id"]
        upload_record.gnani_job_id = job_id
        db.commit()
    except (requests.RequestException, KeyError, ValueError) as error:
        db.rollback()
        upload_record = db.get(Upload, upload_id)
        if upload_record is not None:
            upload_record.status = "failed"
            db.commit()
        raise HTTPException(
            status_code=502,
            detail="Could not create a Gnani batch transcription job.",
        ) from error

    try:
        start_response = requests.post(
            f"{batch_url}/{job_id}/start",
            headers=headers,
            timeout=30,
        )
        start_response.raise_for_status()
    except requests.RequestException as error:
        raise HTTPException(
            status_code=502,
            detail="Gnani created the job, but starting it failed. Try checking status again.",
        ) from error

    return {
        "id": upload_record.id,
        "status": "processing",
        "job_id": job_id,
        "language_code": request.language_code,
    }


def check_transcription(upload_id: int, db: Session):
    upload_record = db.get(Upload, upload_id)
    if upload_record is None:
        raise HTTPException(status_code=404, detail="Upload not found.")
    if upload_record.status == "completed" and upload_record.transcript:
        return {"id": upload_id, "status": "completed", "transcript": upload_record.transcript}
    if not upload_record.gnani_job_id:
        raise HTTPException(status_code=409, detail="No Gnani transcription job exists.")

    api_key = os.getenv("GNANI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="Gnani API key is not configured.")

    batch_url = "https://api.vachana.ai/stt/v3/batch/jobs"
    headers = {"X-API-Key-ID": api_key}
    try:
        # Gnani can rate-limit consecutive status/files reads. Retry only GETs;
        # retrying job-creation POSTs could create duplicate paid jobs.
        with requests.Session() as gnani_client:
            gnani_client.mount("https://api.vachana.ai/", HTTPAdapter(max_retries=Retry(
                total=3,
                backoff_factor=1,
                status_forcelist=[429, 502, 503, 504],
                allowed_methods={"GET"},
                raise_on_status=False,
            )))
            return fetch_transcription_result(upload_id, upload_record, db, batch_url, headers, gnani_client)
    except (requests.RequestException, KeyError, ValueError) as error:
        if isinstance(error, requests.HTTPError) and error.response is not None and error.response.status_code == 429:
            return {"id": upload_id, "status": "processing", "provider_status": "RATE_LIMITED"}
        raise HTTPException(
            status_code=502,
            detail="Could not fetch the transcription result. Try checking status again.",
        ) from error


def fetch_transcription_result(upload_id, upload_record, db, batch_url, headers, gnani_client):
    status_response = gnani_client.get(
        f"{batch_url}/{upload_record.gnani_job_id}",
        headers=headers,
        timeout=30,
    )
    status_response.raise_for_status()
    job_status = status_response.json()["status"]

    if job_status == "CREATED":
        start_response = requests.post(
            f"{batch_url}/{upload_record.gnani_job_id}/start",
            headers=headers,
            timeout=30,
        )
        start_response.raise_for_status()
        return {"id": upload_id, "status": "processing", "provider_status": "STARTING"}

    if job_status in {"COMPLETED", "PARTIAL_FAILURE"}:
        files_response = gnani_client.get(
            f"{batch_url}/{upload_record.gnani_job_id}/files",
            headers=headers,
            params={"status": "COMPLETED"},
            timeout=30,
        )
        files_response.raise_for_status()
        files = files_response.json().get("data", [])
        if not files:
            upload_record.status = "failed"
            db.commit()
            return {"id": upload_id, "status": "failed"}

        transcript_response = requests.get(files[0]["transcript_url"], timeout=30)
        transcript_response.raise_for_status()
        upload_record.transcript = transcript_response.json()["full_transcript"]
        upload_record.status = "completed"
        db.commit()
        return {
            "id": upload_id,
            "status": "completed",
            "transcript": upload_record.transcript,
        }

    if job_status in {"FAILED", "START_FAILED", "CANCELLED"}:
        upload_record.status = "failed"
        db.commit()
        return {"id": upload_id, "status": "failed"}

    return {"id": upload_id, "status": "processing", "provider_status": job_status}


def generate_upload_notes(upload_id: int, db: Session):
    upload_record = db.get(Upload, upload_id)
    if upload_record is None:
        raise HTTPException(status_code=404, detail="Upload not found.")
    if not upload_record.transcript:
        raise HTTPException(status_code=409, detail="Transcribe this upload before generating notes.")

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="Gemini API key is not configured. Restart the backend after saving backend/.env.")

    try:
        # Retry explicit temporary service failures, not timeouts where the
        # provider may already have generated (and billed for) a response.
        with requests.Session() as gemini_client:
            gemini_client.mount("https://generativelanguage.googleapis.com/", HTTPAdapter(max_retries=Retry(
                total=2,
                connect=0,
                read=0,
                other=0,
                backoff_factor=2,
                status_forcelist=[502, 503, 504],
                allowed_methods={"POST"},
                raise_on_status=False,
            )))
            response = gemini_client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{os.getenv('GEMINI_MODEL', 'gemini-3.8-flash')}:generateContent",
                headers={"x-goog-api-key": api_key},
                json={
                    "systemInstruction": {"parts": [{"text": NOTES_PROMPT}]},
                    "contents": [{"role": "user", "parts": [{"text": upload_record.transcript}]}],
                },
                timeout=90,
            )
        response.raise_for_status()
        response_data = response.json()
        candidates = response_data.get("candidates", [])
        if not candidates or candidates[0].get("finishReason") != "STOP":
            raise HTTPException(status_code=502, detail="Gemini did not return complete notes. Try again; previous notes were preserved.")
        note_parts = [
            content["text"]
            for content in candidates[0].get("content", {}).get("parts", [])
            if content.get("text") and not content.get("thought")
        ]
        notes = "\n".join(note_parts).strip()
        if not notes:
            raise ValueError("Gemini returned no notes.")

        upload_record.notes = notes
        db.commit()
        return {"id": upload_id, "notes": notes}
    except (requests.RequestException, KeyError, ValueError) as error:
        db.rollback()
        detail = "Could not retrieve notes from Gemini. Try again shortly."
        if isinstance(error, requests.HTTPError) and error.response is not None:
            detail = {
                400: "Gemini rejected the request. Check the API key and model configuration.",
                401: "Gemini API key is invalid. Check backend/.env and restart the backend.",
                403: "Gemini denied access. Check the key's permissions and project access.",
                404: "The configured Gemini model is unavailable for this key.",
                429: "Gemini quota or rate limit reached. Wait and retry, or check your quota in Google AI Studio.",
                503: "Gemini is temporarily unavailable. Automatic retries failed; try again in a minute. Your saved notes are unchanged.",
            }.get(error.response.status_code, f"Gemini returned HTTP {error.response.status_code}. Try again shortly.")
        elif isinstance(error, requests.Timeout):
            detail = "Gemini took too long to respond. Try generating notes again."
        elif isinstance(error, requests.exceptions.SSLError):
            detail = "The backend could not verify Gemini's HTTPS certificate. Check the backend's certificate configuration."
        elif isinstance(error, requests.ConnectionError):
            detail = "The backend could not connect to Gemini. Check its network or proxy configuration."
        elif isinstance(error, ValueError):
            detail = "Gemini returned an unreadable or empty notes response. Try again shortly."
        raise HTTPException(
            status_code=502,
            detail=detail,
        ) from error

