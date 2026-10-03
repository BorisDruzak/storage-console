from alembic import context

from packages.shared.database import make_engine
from packages.shared.models import metadata
from packages.shared.settings import Settings

engine = make_engine(Settings().database_url)
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=metadata)
    with context.begin_transaction():
        context.run_migrations()
engine.dispose()
