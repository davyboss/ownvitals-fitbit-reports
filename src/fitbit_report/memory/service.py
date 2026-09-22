import json
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from fitbit_report.analytics.associations import Association
from fitbit_report.db.models import InsightFeedback, Observation, UserCorrection
from fitbit_report.memory.schemas import MemoryContext, MemoryItem


def record_fact(session: Session, statement: str, source_ids: list[int]):
    from fitbit_report.db.models import PersonalFact
    fact = PersonalFact(statement=statement, source_ids_json=json.dumps(source_ids))
    session.add(fact)
    session.flush()
    return fact


def record_observation(session: Session, association: Association, start: date, end: date):
    existing = session.scalar(
        select(Observation).where(
            Observation.factor == association.factor,
            Observation.target == association.target,
            Observation.period_start == start,
            Observation.period_end == end,
        )
    )
    if existing:
        return existing
    observation = Observation(
        factor=association.factor,
        target=association.target,
        period_start=start,
        period_end=end,
        direction=association.direction,
        effect_size=association.effect_size,
        sample_size=association.sample_size,
        confidence=association.confidence,
        tags_json=json.dumps([association.factor.split("_")[0]]),
    )
    session.add(observation)
    session.flush()
    return observation


def create_hypothesis(session: Session, observation_id: int, explanation: str, alternatives: list[str]):
    from fitbit_report.db.models import Hypothesis
    hypothesis = Hypothesis(
        observation_id=observation_id,
        explanation=explanation,
        alternatives_json=json.dumps(alternatives, ensure_ascii=False),
    )
    session.add(hypothesis)
    session.flush()
    return hypothesis


def apply_correction(session: Session, report_id: int, correction_text: str):
    correction = UserCorrection(report_id=report_id, correction_text=correction_text)
    session.add(correction)
    session.flush()
    return correction


def record_insight_feedback(
    session: Session,
    report_id: int,
    item_type: str,
    item_index: int,
    verdict: str,
    note: str | None = None,
):
    feedback = session.scalar(
        select(InsightFeedback).where(
            InsightFeedback.report_id == report_id,
            InsightFeedback.item_type == item_type,
            InsightFeedback.item_index == item_index,
        )
    )
    if feedback is None:
        feedback = InsightFeedback(
            report_id=report_id,
            item_type=item_type,
            item_index=item_index,
            verdict=verdict,
            note=note,
        )
        session.add(feedback)
    else:
        feedback.verdict = verdict
        feedback.note = note
    if item_type == "claim" and verdict == "confirmed" and note:
        from fitbit_report.db.models import PersonalFact

        existing = session.scalar(
            select(PersonalFact).where(
                PersonalFact.statement == note,
                PersonalFact.status == "active",
            )
        )
        if existing is None:
            session.add(
                PersonalFact(
                    statement=note,
                    source_ids_json=json.dumps([f"report:{report_id}:claim:{item_index}"]),
                    status="active",
                    validated_at=datetime.now(timezone.utc),
                )
            )
    session.flush()
    return feedback


def list_relevant_memories(session: Session, start: date, end: date, tags: set[str], limit: int = 20):
    from fitbit_report.db.models import PersonalFact
    observations = list(session.scalars(select(Observation).where(Observation.status == "active")))
    items = []
    for observation in observations:
        observation_tags = set(json.loads(observation.tags_json or "[]"))
        overlaps = observation.period_start <= end and observation.period_end >= start
        if overlaps or observation_tags & tags:
            items.append(MemoryItem(observation.id, observation.factor, observation.sample_size, observation.confidence))
    items = items[:limit]
    corrections = list(session.scalars(select(UserCorrection)))
    facts = [
        {
            "id": fact.id,
            "statement": fact.statement,
            "source_ids": json.loads(fact.source_ids_json or "[]"),
            "validated_at": fact.validated_at,
        }
        for fact in session.scalars(
            select(PersonalFact).where(PersonalFact.status == "active").order_by(PersonalFact.created_at.desc()).limit(limit)
        )
    ]
    return MemoryContext(
        items=items,
        correction_ids=[item.id for item in corrections],
        facts=facts,
        feedback=list_feedback(session, limit=limit),
    )


def list_feedback(session: Session, limit: int = 50) -> list[dict]:
    rows = list(
        session.scalars(
            select(InsightFeedback)
            .order_by(InsightFeedback.created_at.desc())
            .limit(limit)
        )
    )
    return [
        {
            "report_id": row.report_id,
            "item_type": row.item_type,
            "item_index": row.item_index,
            "verdict": row.verdict,
            "note": row.note,
            "created_at": row.created_at,
        }
        for row in rows
    ]
