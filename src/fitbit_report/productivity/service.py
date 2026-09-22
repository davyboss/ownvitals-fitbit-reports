from sqlalchemy.orm import Session

from fitbit_report.db.models import ProductivityCheckin
from fitbit_report.db.repositories import ProductivityRepository
from fitbit_report.journal.schemas import ProductivityCheckinInput


class ProductivityService:
    def __init__(self, repository: ProductivityRepository | None = None):
        self.repository = repository or ProductivityRepository()

    def record(self, input: ProductivityCheckinInput, session: Session) -> ProductivityCheckin:
        existing = self.repository.get_for_period(session, input.local_date, input.period)
        values = input.model_dump()
        if existing is None:
            existing = ProductivityCheckin(**values)
            session.add(existing)
        else:
            for key, value in values.items():
                setattr(existing, key, value)
        session.flush()
        return existing
