from sqlalchemy import select
from sqlalchemy.orm import Session

from fitbit_report.db.models import JournalEvent
from fitbit_report.db.repositories import JournalRepository
from fitbit_report.journal.schemas import JournalEventInput


class JournalService:
    def __init__(self, repository: JournalRepository | None = None):
        self.repository = repository or JournalRepository()

    def record(self, input: JournalEventInput, session: Session) -> JournalEvent:
        return self.repository.add_or_existing(session, JournalEvent(**input.model_dump()))

    def recent(self, session: Session, limit: int = 10) -> list[JournalEvent]:
        return list(session.scalars(select(JournalEvent).order_by(JournalEvent.occurred_at.desc()).limit(limit)))

    def get(self, session: Session, event_id: int) -> JournalEvent | None:
        return session.get(JournalEvent, event_id)

    def update(self, event_id: int, values: dict, session: Session) -> JournalEvent:
        event = self.get(session, event_id)
        if event is None:
            raise ValueError("Journal entry was not found")
        for key, value in values.items():
            if key not in {"occurred_at", "subtype", "quantity", "unit", "dose", "dose_unit", "duration_min", "intensity", "note"}:
                raise ValueError(f"Unsupported journal field: {key}")
            setattr(event, key, value)
        session.flush()
        return event

    def delete(self, event_id: int, session: Session) -> None:
        event = self.get(session, event_id)
        if event is None:
            raise ValueError("Journal entry was not found")
        session.delete(event)
