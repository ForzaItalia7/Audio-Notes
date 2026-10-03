# Background processing

Run the backend as usual: `./.venv/bin/uvicorn app.main:app --reload`.
Apply database migrations first with `./.venv/bin/alembic upgrade head`.
Startup checks that the schema is current; it does not modify tables.
See `MIGRATIONS.md` for setup and schema changes.

The transcription and notes POST endpoints now return HTTP 202 with a queued
status. A worker started by FastAPI reads the PostgreSQL queue, contacts the
provider, and saves results. The browser refreshes saved history every four
seconds; it does not drive processing. Closing the tab does not stop a job.

- One worker owns a PostgreSQL advisory lock and processes one step at a time.
- Repeated clicks reuse an active job for that upload and operation.
- Deletion is blocked while either operation is queued or running.
- Existing notes remain available during regeneration and after failures.
- Queued jobs survive backend restarts. Transcription with a saved Gnani job ID
  resumes checking that job. Interrupted notes requests and transcription uploads
  with no saved provider ID require an explicit retry: the provider might already
  have accepted the request, so replaying automatically could duplicate charges.
- The backend and database must remain running for work to progress. This is a
  local-app worker, not a separately deployed worker service. Abrupt process
  termination can interrupt an in-flight provider request.

Implementation: `jobs.py` owns queue/recovery; `processing.py` owns provider
requests; `main.py` owns HTTP endpoints and worker startup/shutdown.

Run queue checks from this directory with:
`./.venv/bin/python -m unittest discover -s tests -v`.
These checks use a temporary in-memory database and mocked providers.
