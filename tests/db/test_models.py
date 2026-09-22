from datetime import date, datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from fitbit_report.db.models import JournalEvent, RawHealthRecord


def test_raw_record_has_unique_provider_key(db_session):
    first = RawHealthRecord(
        provider="fitbit",
        endpoint="sleep/date/2026-08-12.json",
        record_date=date(2026, 8, 12),
        payload_json='{"ok": true}',
        payload_hash="abc",
        fetched_at=datetime.now(timezone.utc),
    )
    db_session.add(first)
    db_session.commit()

    duplicate = RawHealthRecord(
        provider=first.provider,
        endpoint=first.endpoint,
        record_date=first.record_date,
        payload_json=first.payload_json,
        payload_hash="abc",
        fetched_at=first.fetched_at,
    )
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_journal_event_preserves_original_text(db_session):
    event = JournalEvent(
        category="caffeine",
        occurred_at=datetime(2026, 8, 12, 10, 30, tzinfo=timezone.utc),
        quantity=150,
        unit="mg",
        original_text="выпил кофе в 10:30",
    )
    db_session.add(event)
    db_session.commit()

    assert db_session.get(JournalEvent, event.id).original_text == "выпил кофе в 10:30"
