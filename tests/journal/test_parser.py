from datetime import datetime
from zoneinfo import ZoneInfo

from fitbit_report.journal.parser import parse_log_command


KIEV = ZoneInfo("Europe/Kiev")
FIXED_NOW = datetime(2026, 8, 12, 18, 0, tzinfo=KIEV)


def test_parse_caffeine_command():
    event = parse_log_command("/log caffeine 150mg at 10:30", FIXED_NOW, KIEV)

    assert event.category == "caffeine"
    assert event.quantity == 150
    assert event.unit == "mg"
    assert event.occurred_at.hour == 10
    assert event.occurred_at.minute == 30


def test_parse_nicotine_command_with_subtype():
    event = parse_log_command("/log nicotine snus 12mg at 14:00", FIXED_NOW, KIEV)

    assert event.category == "nicotine"
    assert event.subtype == "snus"
    assert event.quantity == 12


def test_parse_nicotine_command_with_piece_count_and_strength():
    event = parse_log_command("/log nicotine snus 1шт 50мг", FIXED_NOW, KIEV)

    assert event.quantity == 1
    assert event.unit == "шт"
    assert event.dose == 50
    assert event.dose_unit == "мг"


def test_parse_training_key_values_and_reject_unknown_field():
    event = parse_log_command(
        '/log training duration=45 intensity=7 note="силовая"',
        FIXED_NOW,
        KIEV,
    )
    assert event.duration_min == 45
    assert event.intensity == 7
    assert event.note == "силовая"

    try:
        parse_log_command("/log training unknown=1", FIXED_NOW, KIEV)
    except ValueError as exc:
        assert "unknown" in str(exc)
    else:
        raise AssertionError("unknown field was accepted")


def test_parse_meal_command_with_type_description_and_time():
    event = parse_log_command(
        '/log meal breakfast "овсянка с бананом" at 08:30',
        FIXED_NOW,
        KIEV,
    )

    assert event.category == "meal"
    assert event.subtype == "breakfast"
    assert event.note == "овсянка с бананом"
    assert event.occurred_at.hour == 8
    assert event.occurred_at.minute == 30


def test_parse_meal_command_without_time_uses_current_time():
    event = parse_log_command('/log meal snack "йогурт"', FIXED_NOW, KIEV)

    assert event.subtype == "snack"
    assert event.note == "йогурт"
    assert event.occurred_at == FIXED_NOW


def test_parse_masturbation_as_a_personal_factor():
    event = parse_log_command("/log masturbation", FIXED_NOW, KIEV)

    assert event.category == "masturbation"
    assert event.occurred_at == FIXED_NOW
