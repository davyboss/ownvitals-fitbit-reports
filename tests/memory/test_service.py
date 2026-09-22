from datetime import date

from fitbit_report.analytics.associations import Association
from fitbit_report.memory.service import (
    apply_correction,
    list_relevant_memories,
    record_observation,
)


def test_relevant_memory_contains_source_and_confidence(db_session):
    observation = record_observation(
        db_session,
        Association(
            factor="caffeine_after_15h",
            target="productivity",
            direction="negative",
            effect_size=-1.5,
            sample_size=8,
            confidence="medium",
        ),
        date(2026, 8, 1),
        date(2026, 8, 12),
    )
    context = list_relevant_memories(
        db_session, date(2026, 8, 1), date(2026, 8, 12), {"caffeine"}
    )

    assert context.items[0].observation_id == observation.id
    assert context.items[0].sample_size == 8


def test_user_correction_is_retrieved_for_future_context(db_session):
    correction = apply_correction(db_session, report_id=3, correction_text="конфликт на работе")
    context = list_relevant_memories(
        db_session, date(2026, 8, 1), date(2026, 8, 12), {"work"}
    )

    assert correction.id in context.correction_ids


def test_confirmed_insight_becomes_personal_fact(db_session):
    from fitbit_report.memory.service import list_relevant_memories, record_insight_feedback

    record_insight_feedback(
        db_session,
        report_id=10,
        item_type="claim",
        item_index=0,
        verdict="confirmed",
        note="После короткого сна моя энергия обычно ниже.",
    )

    context = list_relevant_memories(db_session, date(2026, 8, 1), date(2026, 8, 31), set())
    assert context.facts[0]["statement"] == "После короткого сна моя энергия обычно ниже."
    assert context.feedback[0]["verdict"] == "confirmed"
