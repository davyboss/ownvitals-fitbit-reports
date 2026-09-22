from datetime import datetime
from zoneinfo import ZoneInfo

from fitbit_report.journal.parser import parse_checkin_command
from fitbit_report.productivity.service import ProductivityService


KIEV = ZoneInfo("Europe/Kiev")
FIXED_NOW = datetime(2026, 8, 12, 18, 0, tzinfo=KIEV)


def test_parse_evening_checkin():
    checkin = parse_checkin_command(
        "/checkin evening persistence=8 quality=6 energy=4 focus=5 deep_work_min=180 stress=7",
        FIXED_NOW,
        KIEV,
    )

    assert checkin.period == "evening"
    assert checkin.persistence == 8
    assert checkin.deep_work_min == 180


def test_productivity_service_upserts_one_checkin_per_period(db_session):
    service = ProductivityService()
    first = service.record(
        parse_checkin_command("/checkin evening persistence=8 quality=6", FIXED_NOW, KIEV),
        db_session,
    )
    second = service.record(
        parse_checkin_command("/checkin evening persistence=9 quality=7", FIXED_NOW, KIEV),
        db_session,
    )

    assert first.id == second.id
    assert second.persistence == 9
    assert second.work_quality == 7
