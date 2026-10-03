# Database migrations

Alembic tracks schema changes as numbered Python files in `migrations/versions`.
The current database has been verified and adopted at `0001_initial` without
recreating tables or changing saved recordings, transcripts, notes, or jobs.

## New installation

From `backend`, configure `DATABASE_URL` in `.env`, then run:

```sh
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/alembic upgrade head
./.venv/bin/uvicorn app.main:app --reload
```

Database credentials are read from the backend `.env`, never stored in Alembic's
configuration. Existing shell environment values take precedence over `.env`.

## Future schema changes

1. Edit the SQLAlchemy models.
2. Generate a candidate migration:
   `./.venv/bin/alembic revision --autogenerate -m "describe the change"`
3. Review the migration: automatic generation does not safely infer every rename
   or data transformation. Back up important data before applying changes.
4. Apply it with `./.venv/bin/alembic upgrade head` before restarting the API.
5. Check with `./.venv/bin/alembic current` and `./.venv/bin/alembic check`.

The API refuses to start if the database revision is behind the migration files.
Migrations are explicit deployment steps; concurrent API workers do not migrate.
The initial migration refuses automatic downgrade because dropping the initial
tables would delete user data.

## Another existing unversioned database

Only while `0001_initial` is the sole migration, run
`./.venv/bin/python -m app.adopt_schema` to adopt an existing matching schema.
It compares the schema with the models and refuses mismatches or an already
versioned database. Do not blindly stamp a database to skip unapplied changes.
