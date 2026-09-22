from datetime import date, datetime, timezone
import os

from fitbit_report.scheduler import create_backup, daily_period
from fitbit_report.types import DateRange


def test_backup_creates_timestamped_archive(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "app.db").write_text("db", encoding="utf-8")
    settings = type("Settings", (), {
        "database_url": f"sqlite:///{tmp_path / 'app.db'}",
        "raw_data_dir": tmp_path / "data",
        "obsidian_vault": tmp_path / "vault",
        "backup_dir": tmp_path / "backups",
    })()
    archive = create_backup(settings, datetime(2026, 8, 12, 3, 0, tzinfo=timezone.utc))
    assert archive.name == "backup-2026-08-12-030000.zip"
    assert archive.exists()
    if os.name == "posix":
        assert archive.parent.stat().st_mode & 0o777 == 0o700
        assert archive.stat().st_mode & 0o777 == 0o600


def test_daily_period_uses_date():
    assert daily_period(date(2026, 8, 12)) == DateRange(date(2026, 8, 12), date(2026, 8, 12))
