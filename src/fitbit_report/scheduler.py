import zipfile
from datetime import date, datetime
from pathlib import Path

from fitbit_report.types import DateRange
from fitbit_report.private_storage import ensure_private_directory, restrict_private_file


def daily_period(day: date) -> DateRange:
    return DateRange(day, day)


def create_backup(settings, now: datetime) -> Path:
    ensure_private_directory(settings.backup_dir)
    target = settings.backup_dir / f"backup-{now:%Y-%m-%d-%H%M%S}.zip"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        database_path = _database_path(settings.database_url)
        if database_path.exists():
            archive.write(database_path, "app.db")
        for source in (settings.raw_data_dir, settings.obsidian_vault):
            if source.exists():
                for path in source.rglob("*"):
                    if path.is_file() and path.name != ".env":
                        archive.write(path, path.relative_to(source.parent))
    restrict_private_file(target)
    return target


def _database_path(database_url: str) -> Path:
    return Path(database_url.removeprefix("sqlite:///"))
