from datetime import date

from fitbit_report.integrations.obsidian import write_report
from fitbit_report.types import DateRange


def test_write_report_uses_stable_date_path(tmp_path):
    path = write_report(tmp_path, "daily", DateRange(date(2026, 8, 12), date(2026, 8, 12)), "content")
    assert path == tmp_path / "Health" / "Daily" / "2026-08-12.md"
    assert path.read_text(encoding="utf-8") == "content"
