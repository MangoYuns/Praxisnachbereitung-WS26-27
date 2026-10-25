"""Migrationen verwenden dieselbe DB_DSN wie die Inventar-App."""

import logging
import os

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import make_url

load_dotenv()
logging.basicConfig(level=logging.INFO)
url = make_url(os.getenv("DB_DSN", "postgresql://appuser:apppass@db:5432/appdb"))
url = url.set(drivername="postgresql+psycopg")

# Die App nutzt SQL direkt; ihre Pydantic-Modelle sind keine SQLAlchemy-Metadaten.
# Migrationen deshalb manuell mit `alembic revision -m "..."` anlegen.
if context.is_offline_mode():
    context.configure(url=url, target_metadata=None, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
