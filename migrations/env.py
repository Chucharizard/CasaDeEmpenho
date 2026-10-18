from alembic import context
from flask import current_app

config = context.config
database = current_app.extensions['migrate'].db

if context.is_offline_mode():
    context.configure(url=str(database.engine.url), target_metadata=database.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    with database.engine.connect() as connection:
        if connection.dialect.name == 'sqlite':
            connection.exec_driver_sql('BEGIN IMMEDIATE')
        context.configure(connection=connection, target_metadata=database.metadata, render_as_batch=True, transactional_ddl=True)
        with context.begin_transaction():
            context.run_migrations()
        connection.commit()
