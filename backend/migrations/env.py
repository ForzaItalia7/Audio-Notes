from alembic import context
from app.database import Base, engine
from app import models  # Register tables without starting the API or worker.


def run(connection):
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(url=engine.url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    connection = context.config.attributes.get('connection')
    if connection is not None:
        run(connection)
    else:
        with engine.connect() as connection:
            run(connection)
