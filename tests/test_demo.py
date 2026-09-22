from datetime import date

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from fitbit_report.db.models import (
    DailyActivity,
    HeartRateDaily,
    HrvMeasurement,
    JournalEvent,
    MealTextAnalysis,
    ProductivityCheckin,
    SleepSession,
)
from fitbit_report.demo import create_demo_database
from fitbit_report.reports.context import build_report_context
from fitbit_report.types import DateRange


def test_create_demo_database_builds_complete_synthetic_history(tmp_path):
    target = date(2026, 9, 15)
    path = create_demo_database(tmp_path / "demo.db", target)
    engine = create_engine(f"sqlite:///{path}", future=True)

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(SleepSession)) == 35
        assert session.scalar(select(func.count()).select_from(DailyActivity)) == 35
        assert session.scalar(select(func.count()).select_from(HeartRateDaily)) == 35
        assert session.scalar(select(func.count()).select_from(HrvMeasurement)) == 35
        assert session.scalar(select(func.count()).select_from(ProductivityCheckin)) == 70
        assert session.scalar(select(func.count()).select_from(MealTextAnalysis)) == 105

        activity = session.scalar(select(DailyActivity).where(DailyActivity.record_date == target))
        sleep = session.scalar(select(SleepSession).where(SleepSession.record_date == target))
        assert activity is not None and activity.steps == 10_800
        assert sleep is not None and sleep.minutes_asleep == 545

        original_texts = session.scalars(select(JournalEvent.original_text)).all()
        assert original_texts
        assert all("synthetic" in text for text in original_texts)

        context = build_report_context(
            session,
            "daily",
            DateRange(target, target),
            timezone_name="Europe/Kiev",
            locale="en",
        )
        assert context.health["activity"][0]["steps"] == 10_800
        assert len(context.health["nutrition"]) == 3
        assert context.personal_state["readiness"]["score"] is not None

    engine.dispose()


def test_create_demo_database_requires_force_to_replace_existing_file(tmp_path):
    path = tmp_path / "demo.db"
    target = date(2026, 9, 15)
    create_demo_database(path, target)

    with pytest.raises(FileExistsError):
        create_demo_database(path, target)

    assert create_demo_database(path, target, force=True) == path


def test_create_demo_database_requires_enough_baseline_history(tmp_path):
    with pytest.raises(ValueError, match="at least 29 days"):
        create_demo_database(tmp_path / "demo.db", date(2026, 9, 15), days=28)
