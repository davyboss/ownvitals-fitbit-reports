from datetime import date

from fitbit_report.db.models import (
    DailyActivity,
    ExerciseSession,
    HeartRateDaily,
    HrvMeasurement,
    ProductivityCheckin,
    SleepSession,
)
from fitbit_report.reports.baseline import build_personal_baselines


def test_baseline_uses_daily_values_and_excludes_current_and_future_dates(db_session):
    db_session.add_all([
        SleepSession(record_date=date(2026, 8, 9), minutes_asleep=420),
        SleepSession(record_date=date(2026, 8, 10), minutes_asleep=480),
        SleepSession(record_date=date(2026, 8, 11), minutes_asleep=360),
        DailyActivity(record_date=date(2026, 8, 9), steps=1000),
        DailyActivity(record_date=date(2026, 8, 10), steps=2000),
        DailyActivity(record_date=date(2026, 8, 11), steps=3000),
        DailyActivity(record_date=date(2026, 8, 12), steps=9999),
        DailyActivity(record_date=date(2026, 8, 13), steps=12345),
        HrvMeasurement(record_date=date(2026, 8, 10), rmssd=40),
        HrvMeasurement(record_date=date(2026, 8, 10), rmssd=60),
        HrvMeasurement(record_date=date(2026, 8, 11), rmssd=80),
        ExerciseSession(
            record_date=date(2026, 8, 10),
            active_duration_min=60,
            calories_kcal=500,
        ),
        ExerciseSession(
            record_date=date(2026, 8, 11),
            active_duration_min=30,
            calories_kcal=300,
        ),
        ProductivityCheckin(
            local_date=date(2026, 8, 9),
            period="morning",
            energy=3,
            original_text="morning",
        ),
        ProductivityCheckin(
            local_date=date(2026, 8, 9),
            period="evening",
            energy=7,
            original_text="evening",
        ),
        ProductivityCheckin(
            local_date=date(2026, 8, 10),
            period="morning",
            energy=5,
            original_text="morning",
        ),
        ProductivityCheckin(
            local_date=date(2026, 8, 11),
            period="morning",
            energy=6,
            original_text="morning",
        ),
        ProductivityCheckin(
            local_date=date(2026, 8, 12),
            period="evening",
            energy=10,
            original_text="current day",
        ),
    ])
    db_session.flush()

    result = build_personal_baselines(db_session, date(2026, 8, 12))

    assert set(result["windows"]) == {"7d", "14d", "28d"}
    assert result["windows"]["7d"]["metrics"]["activity.steps"] == {
        "samples": 3,
        "average": 2000.0,
        "median": 2000.0,
        "minimum": 1000.0,
        "maximum": 3000.0,
        "standard_deviation": 816.5,
        "sample_status": "limited",
    }
    assert result["windows"]["7d"]["metrics"]["hrv.rmssd"]["average"] == 65.0
    assert result["windows"]["7d"]["metrics"]["hrv.rmssd"]["samples"] == 2
    assert result["windows"]["7d"]["metrics"]["productivity.energy"]["average"] == 6.0
    assert result["windows"]["7d"]["metrics"]["exercise.active_duration_min"]["average"] == 45.0
    assert "current day" not in str(result)
    assert "12345" not in str(result)


def test_baseline_marks_single_observation_as_insufficient(db_session):
    db_session.add(
        HeartRateDaily(record_date=date(2026, 8, 11), resting_heart_rate=62)
    )
    db_session.flush()

    result = build_personal_baselines(db_session, date(2026, 8, 12))
    metric = result["windows"]["7d"]["metrics"]["heart_rate.resting_heart_rate"]

    assert metric["samples"] == 1
    assert metric["average"] == 62.0
    assert metric["sample_status"] == "insufficient"
