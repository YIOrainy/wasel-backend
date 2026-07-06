from procrastinate import App, PsycopgConnector

from app.config import settings


def _to_dsn() -> str:
    return settings.database_url.replace("+psycopg", "")


procrastinate_app = App(
    connector=PsycopgConnector(conninfo=_to_dsn()),
    import_paths=["app.services.shipments.jobs", "app.services.devices.jobs"],
)
