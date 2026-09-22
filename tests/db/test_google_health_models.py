from datetime import datetime

from fitbit_report.db.models import GoogleHealthIdentity, JournalEvent, MealPhotoAnalysis, MealTextAnalysis


def test_google_health_identity_has_singleton_key(db_session):
    identity = GoogleHealthIdentity(
        singleton_key="me",
        health_user_id="google-1",
        legacy_user_id="fitbit-1",
    )
    db_session.add(identity)
    db_session.commit()

    assert db_session.query(GoogleHealthIdentity).one().health_user_id == "google-1"


def test_meal_photo_analysis_table_is_created(db_session):
    record = MealPhotoAnalysis(
        occurred_at=datetime(2026, 8, 14, 13, 30),
        meal_type="lunch",
        photo_path="data/food-photos/meal.jpg",
        analysis_json="{}",
    )
    db_session.add(record)
    db_session.commit()

    assert db_session.query(MealPhotoAnalysis).one().meal_type == "lunch"


def test_text_meal_analysis_table_stores_status_and_result(db_session):
    event = JournalEvent(
        category="meal",
        subtype="snack",
        occurred_at=datetime(2026, 8, 16, 12, 0),
        note="Баунти 55 г",
        original_text="/log meal snack Баунти 55 г",
    )
    db_session.add(event)
    db_session.flush()
    db_session.add(MealTextAnalysis(
        journal_event_id=event.id,
        analysis_json='{"total_calories_min": 260, "total_calories_max": 300}',
        status="success",
        model="sonnet",
    ))
    db_session.commit()

    stored = db_session.query(MealTextAnalysis).one()
    assert stored.journal_event_id == event.id
    assert stored.status == "success"
