"""Shared migration configuration and a read-only startup version check."""
from pathlib import Path
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory


def migration_config():
    return Config(str(Path(__file__).resolve().parent.parent / 'alembic.ini'))


def require_current_schema(engine):
    expected = set(ScriptDirectory.from_config(migration_config()).get_heads())
    with engine.connect() as connection:
        actual = set(MigrationContext.configure(connection).get_current_heads())
    if actual != expected:
        raise RuntimeError('Database migrations are pending. From backend, run ./.venv/bin/alembic upgrade head, then restart the backend.')
