import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from fitbit_report.db.models import Base


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()
