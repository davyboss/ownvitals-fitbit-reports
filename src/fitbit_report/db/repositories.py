from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from fitbit_report.db.models import (
    GeneratedReport,
    JournalEvent,
    ProductivityCheckin,
    RawHealthRecord,
    SyncRun,
)


class RawRecordRepository:
    def get(self, session: Session, provider: str, endpoint: str, record_date: date):
        return session.scalar(
            select(RawHealthRecord).where(
                RawHealthRecord.provider == provider,
                RawHealthRecord.endpoint == endpoint,
                RawHealthRecord.record_date == record_date,
            )
        )

    def add_or_update(self, session: Session, record: RawHealthRecord) -> bool:
        existing = self.get(session, record.provider, record.endpoint, record.record_date)
        if existing is None:
            session.add(record)
            session.flush()
            return True
        if existing.payload_hash == record.payload_hash:
            return False
        existing.payload_json = record.payload_json
        existing.payload_hash = record.payload_hash
        existing.fetched_at = record.fetched_at
        return True


class SyncRunRepository:
    def start(self, session: Session, requested_date: date, started_at: datetime) -> SyncRun:
        run = SyncRun(requested_date=requested_date, started_at=started_at, status="running")
        session.add(run)
        session.flush()
        return run


class JournalRepository:
    def add_or_existing(self, session: Session, event: JournalEvent) -> JournalEvent:
        existing = session.scalar(
            select(JournalEvent).where(
                JournalEvent.category == event.category,
                JournalEvent.occurred_at == event.occurred_at,
                JournalEvent.quantity == event.quantity,
                JournalEvent.unit == event.unit,
                JournalEvent.original_text == event.original_text,
            )
        )
        if existing is not None:
            return existing
        session.add(event)
        session.flush()
        return event


class ProductivityRepository:
    def get_for_period(self, session: Session, local_date: date, period: str):
        return session.scalar(
            select(ProductivityCheckin).where(
                ProductivityCheckin.local_date == local_date,
                ProductivityCheckin.period == period,
            )
        )


class MemoryRepository:
    pass


class ReportRepository:
    def find_by_key(self, session: Session, report_type: str, period_start: date, period_end: date, context_hash: str):
        return session.scalar(
            select(GeneratedReport).where(
                GeneratedReport.report_type == report_type,
                GeneratedReport.period_start == period_start,
                GeneratedReport.period_end == period_end,
                GeneratedReport.context_hash == context_hash,
            )
        )
