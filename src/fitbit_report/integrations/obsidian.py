from pathlib import Path

from fitbit_report.types import DateRange, ReportType
from fitbit_report.private_storage import write_private_text


def write_report(vault: Path, report_type: ReportType, period: DateRange, markdown: str) -> Path:
    if report_type == "daily":
        relative = Path("Health") / "Daily" / f"{period.start:%Y-%m-%d}.md"
    elif report_type == "weekly":
        relative = Path("Health") / "Weekly" / f"{period.start:%G-W%V}.md"
    else:
        relative = Path("Health") / "Monthly" / f"{period.start:%Y-%m}.md"
    target = vault / relative
    write_private_text(target, markdown)
    return target
