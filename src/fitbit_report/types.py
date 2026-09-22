from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class DateRange:
    start: date
    end: date


ReportType = Literal["daily", "weekly", "monthly"]


@dataclass(frozen=True)
class ReportResult:
    report_type: ReportType
    period: DateRange
    path: Path
    markdown: str
    telegram_text: str | None = None
    report_id: int | None = None
    telegram_sent_at: datetime | None = None
    chart_paths: tuple[Path, ...] = ()
    claim_count: int = 0
    recommendation_count: int = 0
    feedback_claim_indices: tuple[int, ...] = ()
    telegram_rich_html: str | None = None
    telegram_before_chart: str | None = None
    telegram_after_chart: str | None = None
    feedback_claim_summaries: tuple[tuple[int, str], ...] = ()


@dataclass(frozen=True)
class SyncSummary:
    status: str
    requested_date: date
    fetched: int = 0
    inserted: int = 0
    normalized: int = 0
    error_type: str | None = None
