from datetime import date

from fitbit_report.db.models import JournalEvent, ProductivityCheckin
from fitbit_report.integrations.obsidian import write_report
from fitbit_report.journal.parser import parse_log_command, parse_checkin_command
from fitbit_report.journal.service import JournalService
from fitbit_report.productivity.service import ProductivityService
from fitbit_report.reports.context import build_report_context
from fitbit_report.reports.renderer import render_markdown
from fitbit_report.types import DateRange


def test_daily_pipeline_persists_context_report_and_obsidian_file(db_session, tmp_path, monkeypatch):
    from zoneinfo import ZoneInfo
    from datetime import datetime

    zone = ZoneInfo("Europe/Kiev")
    now = datetime(2026, 8, 12, 18, 0, tzinfo=zone)
    JournalService().record(parse_log_command("/log caffeine 150mg at 10:30", now, zone), db_session)
    ProductivityService().record(
        parse_checkin_command("/checkin evening persistence=8 quality=7 energy=6 focus=7 deep_work_min=180 stress=3", now, zone),
        db_session,
    )
    context = build_report_context(db_session, "daily", DateRange(date(2026, 8, 12), date(2026, 8, 12)))
    draft = {"summary": "ok", "claims": [], "recommendations": [], "experiments": [], "confidence": "low"}
    markdown = render_markdown({"type": "daily", "period_start": date(2026, 8, 12), "period_end": date(2026, 8, 12), "model": "sonnet", "context_hash": "test"}, draft)
    path = write_report(tmp_path, "daily", DateRange(date(2026, 8, 12), date(2026, 8, 12)), markdown)

    assert context.events
    assert path.exists()
    assert db_session.query(JournalEvent).count() == 1
    assert db_session.query(ProductivityCheckin).count() == 1
