from datetime import date

from fitbit_report.runtime import report_period


def test_weekly_period_is_monday_to_sunday():
    period = report_period("weekly", date(2026, 8, 12))
    assert period.start == date(2026, 8, 10)
    assert period.end == date(2026, 8, 16)


def test_monthly_period_is_full_calendar_month():
    period = report_period("monthly", date(2026, 8, 12))
    assert period.start == date(2026, 8, 1)
    assert period.end == date(2026, 8, 31)
