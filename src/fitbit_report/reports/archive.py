from pathlib import Path

from fitbit_report.types import ReportType


_REPORT_DIRECTORIES: dict[ReportType, Path] = {
    "daily": Path("Health") / "Daily",
    "weekly": Path("Health") / "Weekly",
    "monthly": Path("Health") / "Monthly",
}


def list_report_paths(vault: Path, report_type: ReportType, limit: int = 10) -> list[Path]:
    directory = vault / _REPORT_DIRECTORIES[report_type]
    if not directory.exists():
        return []
    return sorted(directory.glob("*.md"), reverse=True)[:limit]


def read_report(path: Path) -> str:
    return path.read_text(encoding="utf-8")
