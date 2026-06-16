from procrastinate import App, PsycopgConnector

from app.config import settings


def _to_dsn() -> str:
    # Procrastinate talks to Postgres via psycopg directly; drop SQLAlchemy's
    # "+psycopg" driver tag from the URL.
    return settings.database_url.replace("+psycopg", "")


procrastinate_app = App(
    connector=PsycopgConnector(conninfo=_to_dsn()),
    # Each domain owns its jobs in services/<domain>/jobs.py; list them here so
    # the worker discovers every task.
    import_paths=["app.services.shipments.jobs", "app.services.devices.jobs"],
)
