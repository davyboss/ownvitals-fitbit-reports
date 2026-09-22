from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import Engine, create_engine, inspect
from sqlalchemy.orm import Session

from fitbit_report.config import Settings
from fitbit_report.db.models import Base
from fitbit_report.private_storage import ensure_private_directory


def create_engine_from_settings(settings: Settings) -> Engine:
    kwargs = {"future": True}
    if settings.database_url.startswith("sqlite"):
        # The Telegram handlers and scheduled sync run in separate worker
        # threads.  Let SQLite wait for a short-lived writer instead of
        # failing a user action with "database is locked" immediately.
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
        database_path = Path(settings.database_url.removeprefix("sqlite:///"))
        if database_path.name != ":memory:":
            ensure_private_directory(database_path.parent)
    return create_engine(settings.database_url, **kwargs)


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    if engine.dialect.name == "sqlite":
        columns = {item["name"] for item in inspect(engine).get_columns("exercise_sessions")}
        if "details_json" not in columns:
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "ALTER TABLE exercise_sessions ADD COLUMN details_json TEXT"
                )
        journal_columns = {
            item["name"] for item in inspect(engine).get_columns("journal_events")
        }
        with engine.begin() as connection:
            if "dose" not in journal_columns:
                connection.exec_driver_sql("ALTER TABLE journal_events ADD COLUMN dose FLOAT")
            if "dose_unit" not in journal_columns:
                connection.exec_driver_sql(
                    "ALTER TABLE journal_events ADD COLUMN dose_unit VARCHAR(16)"
                )
        report_columns = {
            item["name"] for item in inspect(engine).get_columns("generated_reports")
        }
        if "telegram_sent_at" not in report_columns:
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "ALTER TABLE generated_reports ADD COLUMN telegram_sent_at DATETIME"
                )
                if "created_at" in report_columns:
                    connection.exec_driver_sql(
                        "UPDATE generated_reports SET telegram_sent_at = created_at "
                        "WHERE status = 'success' AND telegram_sent_at IS NULL"
                    )


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
