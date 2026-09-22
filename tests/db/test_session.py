from pathlib import Path

from sqlalchemy import create_engine

from fitbit_report.config import Settings
from fitbit_report.db.session import create_engine_from_settings, init_db


def test_sqlite_engine_creates_parent_directory(tmp_path: Path):
    database = tmp_path / "nested" / "data" / "app.db"
    settings = Settings(
        telegram_bot_token="telegram",
        telegram_allowed_chat_id=42,
        database_url=f"sqlite:///{database}",
    )

    engine = create_engine_from_settings(settings)

    assert database.parent.is_dir()
    engine.dispose()


def test_init_db_adds_details_column_to_existing_exercise_table(tmp_path: Path):
    from sqlalchemy import inspect, text

    database = tmp_path / "app.db"
    engine = create_engine(f"sqlite:///{database}", future=True)
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE exercise_sessions (id INTEGER PRIMARY KEY, record_date DATE)"
        ))

    init_db(engine)

    columns = {item["name"] for item in inspect(engine).get_columns("exercise_sessions")}
    assert "details_json" in columns
    engine.dispose()


def test_init_db_adds_nicotine_dose_columns_to_existing_journal_table(tmp_path: Path):
    from sqlalchemy import inspect, text

    database = tmp_path / "app.db"
    engine = create_engine(f"sqlite:///{database}", future=True)
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE journal_events (id INTEGER PRIMARY KEY, category VARCHAR(32))"
        ))

    init_db(engine)

    columns = {item["name"] for item in inspect(engine).get_columns("journal_events")}
    assert {"dose", "dose_unit"}.issubset(columns)
    engine.dispose()


def test_init_db_adds_telegram_delivery_column_to_existing_reports_table(tmp_path: Path):
    from sqlalchemy import inspect, text

    database = tmp_path / "app.db"
    engine = create_engine(f"sqlite:///{database}", future=True)
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE generated_reports (id INTEGER PRIMARY KEY, status VARCHAR(16))"
        ))

    init_db(engine)

    columns = {item["name"] for item in inspect(engine).get_columns("generated_reports")}
    assert "telegram_sent_at" in columns
    engine.dispose()


def test_init_db_marks_existing_successful_reports_as_already_delivered(tmp_path: Path):
    from sqlalchemy import text

    database = tmp_path / "app.db"
    engine = create_engine(f"sqlite:///{database}", future=True)
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE generated_reports ("
            "id INTEGER PRIMARY KEY, status VARCHAR(16), created_at DATETIME)"
        ))
        connection.execute(text(
            "INSERT INTO generated_reports (id, status, created_at) "
            "VALUES (1, 'success', '2026-08-15 08:00:00')"
        ))

    init_db(engine)

    with engine.connect() as connection:
        sent_at = connection.execute(text(
            "SELECT telegram_sent_at FROM generated_reports WHERE id = 1"
        )).scalar_one()
    assert sent_at == "2026-08-15 08:00:00"
    engine.dispose()
