import unittest
from alembic import command
from sqlalchemy import create_engine, inspect
from app.schema import migration_config, require_current_schema


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')

    def tearDown(self):
        self.engine.dispose()

    def test_empty_database_requires_migrations(self):
        with self.assertRaisesRegex(RuntimeError, 'migrations are pending'):
            require_current_schema(self.engine)

    def test_fresh_install_and_repeat_upgrade(self):
        config = migration_config()
        with self.engine.begin() as connection:
            config.attributes['connection'] = connection
            command.upgrade(config, 'head')
            command.upgrade(config, 'head')
            self.assertEqual(set(inspect(connection).get_table_names()),
                             {'uploads', 'processing_jobs', 'alembic_version'})
        require_current_schema(self.engine)

    def test_unknown_revision_is_rejected(self):
        with self.engine.begin() as connection:
            connection.exec_driver_sql('CREATE TABLE alembic_version (version_num VARCHAR(32))')
            connection.exec_driver_sql("INSERT INTO alembic_version VALUES ('unknown')")
        with self.assertRaises(RuntimeError):
            require_current_schema(self.engine)
