import json
from datetime import date
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from fitbit_report.db.models import JournalEvent, MealTextAnalysis
from fitbit_report.journal.food import FoodTextAnalyzer


class MealTextAnalysisService:
    def __init__(self, analyzer: FoodTextAnalyzer):
        self.analyzer = analyzer
        self.model = getattr(getattr(analyzer, "runner", None), "model", "sonnet")

    def analyze_event(
        self,
        session: Session,
        event: JournalEvent,
        retry_failed: bool = True,
    ) -> MealTextAnalysis:
        if event.category != "meal":
            raise ValueError("Only meal journal events can be analyzed as food")

        record = session.scalar(
            select(MealTextAnalysis).where(
                MealTextAnalysis.journal_event_id == event.id
            )
        )
        if record is not None and record.status == "success":
            return record
        if record is not None and record.status == "failed" and not retry_failed:
            return record
        if record is None:
            record = MealTextAnalysis(
                journal_event_id=event.id,
                status="pending",
                model=self.model,
            )
            session.add(record)

        record.status = "running"
        record.model = self.model
        record.error_message = None
        try:
            analysis = self.analyzer.analyze(event.note or event.original_text, event.subtype or "other")
            record.analysis_json = json.dumps(analysis.model_dump(), ensure_ascii=False)
            record.status = "success"
        except Exception as exc:
            record.analysis_json = None
            record.status = "failed"
            record.error_message = str(exc)
        # Let the caller choose the transaction boundary.  Flushing here can
        # leave a SQLite write lock active while analyze_period proceeds to
        # another, potentially slow, Claude request.
        return record

    def analyze_period(
        self,
        session: Session,
        start: date,
        end: date,
        timezone_name: str,
    ) -> None:
        zone = ZoneInfo(timezone_name)
        events = session.scalars(
            select(JournalEvent)
            .where(JournalEvent.category == "meal")
            .order_by(JournalEvent.occurred_at)
        ).all()
        for event in events:
            occurred_at = event.occurred_at
            if occurred_at.tzinfo is None:
                occurred_at = occurred_at.replace(tzinfo=zone)
            local_day = occurred_at.astimezone(zone).date()
            if start <= local_day <= end:
                self.analyze_event(session, event)
