"""One-time adoption of an existing, matching pre-migration database."""
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from .database import Base, engine
from . import models
from .schema import migration_config


def main():
    config = migration_config()
    if ScriptDirectory.from_config(config).get_heads() != ['0001_initial']:
        raise RuntimeError('This adoption command is only for the initial schema. Use normal migrations for later versions.')
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        if context.get_current_heads():
            raise RuntimeError('Database is already versioned. Use alembic upgrade head.')
        if compare_metadata(context, Base.metadata):
            raise RuntimeError('Existing schema differs from the initial models. Review the schema before adoption; no version was stamped.')
        config.attributes['connection'] = connection
        command.stamp(config, '0001_initial')
    print('Existing schema verified and adopted at 0001_initial. User data was not changed.')


if __name__ == '__main__':
    main()
