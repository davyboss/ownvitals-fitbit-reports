from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class GoogleHealthIdentity(Base):
    __tablename__ = "google_health_identity"
    __table_args__ = (UniqueConstraint("singleton_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    singleton_key: Mapped[str] = mapped_column(String(16), default="me")
    health_user_id: Mapped[str] = mapped_column(String(64))
    legacy_user_id: Mapped[str | None] = mapped_column(String(64))


class RawHealthRecord(Base):
    __tablename__ = "fitbit_raw_records"
    __table_args__ = (UniqueConstraint("provider", "endpoint", "record_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(32))
    endpoint: Mapped[str] = mapped_column(String(255))
    record_date: Mapped[date] = mapped_column(Date)
    payload_json: Mapped[str] = mapped_column(Text)
    payload_hash: Mapped[str] = mapped_column(String(64))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    requested_date: Mapped[date] = mapped_column(Date)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32))
    fetched_count: Mapped[int] = mapped_column(Integer, default=0)
    inserted_count: Mapped[int] = mapped_column(Integer, default=0)
    normalized_count: Mapped[int] = mapped_column(Integer, default=0)
    error_type: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)


class SleepSession(Base):
    __tablename__ = "sleep_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    record_date: Mapped[date] = mapped_column(Date, index=True)
    source_record_id: Mapped[int | None] = mapped_column(Integer)
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    minutes_asleep: Mapped[int | None] = mapped_column(Integer)
    minutes_in_bed: Mapped[int | None] = mapped_column(Integer)
    efficiency: Mapped[float | None] = mapped_column(Float)
    stages_json: Mapped[str | None] = mapped_column(Text)


class DailyActivity(Base):
    __tablename__ = "daily_activity"

    id: Mapped[int] = mapped_column(primary_key=True)
    record_date: Mapped[date] = mapped_column(Date, unique=True)
    source_record_id: Mapped[int | None] = mapped_column(Integer)
    steps: Mapped[int | None] = mapped_column(Integer)
    distance: Mapped[float | None] = mapped_column(Float)
    calories_out: Mapped[float | None] = mapped_column(Float)
    active_zone_minutes: Mapped[int | None] = mapped_column(Integer)


class ExerciseSession(Base):
    __tablename__ = "exercise_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    record_date: Mapped[date] = mapped_column(Date, index=True)
    source_record_id: Mapped[int | None] = mapped_column(Integer)
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exercise_type: Mapped[str | None] = mapped_column(String(64))
    display_name: Mapped[str | None] = mapped_column(String(255))
    active_duration_min: Mapped[float | None] = mapped_column(Float)
    calories_kcal: Mapped[float | None] = mapped_column(Float)
    distance_km: Mapped[float | None] = mapped_column(Float)
    steps: Mapped[int | None] = mapped_column(Integer)
    average_heart_rate_bpm: Mapped[float | None] = mapped_column(Float)
    active_zone_minutes: Mapped[int | None] = mapped_column(Integer)
    details_json: Mapped[str | None] = mapped_column(Text)


class HeartRateDaily(Base):
    __tablename__ = "heart_rate_daily"

    id: Mapped[int] = mapped_column(primary_key=True)
    record_date: Mapped[date] = mapped_column(Date, unique=True)
    source_record_id: Mapped[int | None] = mapped_column(Integer)
    resting_heart_rate: Mapped[float | None] = mapped_column(Float)
    zones_json: Mapped[str | None] = mapped_column(Text)


class HeartRateIntraday(Base):
    __tablename__ = "heart_rate_intraday"

    id: Mapped[int] = mapped_column(primary_key=True)
    record_date: Mapped[date] = mapped_column(Date, index=True)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    bpm: Mapped[int] = mapped_column(Integer)
    source_record_id: Mapped[int | None] = mapped_column(Integer)


class HrvMeasurement(Base):
    __tablename__ = "hrv_measurements"

    id: Mapped[int] = mapped_column(primary_key=True)
    record_date: Mapped[date] = mapped_column(Date, index=True)
    measured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rmssd: Mapped[float | None] = mapped_column(Float)
    coverage: Mapped[float | None] = mapped_column(Float)
    source_record_id: Mapped[int | None] = mapped_column(Integer)


class BodyMeasurement(Base):
    __tablename__ = "body_measurements"

    id: Mapped[int] = mapped_column(primary_key=True)
    record_date: Mapped[date] = mapped_column(Date, index=True)
    measurement_type: Mapped[str] = mapped_column(String(32))
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(16))
    source_record_id: Mapped[int | None] = mapped_column(Integer)


class JournalEvent(Base):
    __tablename__ = "journal_events"
    __table_args__ = (UniqueConstraint("category", "occurred_at", "quantity", "unit", "original_text"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(32), index=True)
    subtype: Mapped[str | None] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    quantity: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(16))
    dose: Mapped[float | None] = mapped_column(Float)
    dose_unit: Mapped[str | None] = mapped_column(String(16))
    duration_min: Mapped[int | None] = mapped_column(Integer)
    intensity: Mapped[float | None] = mapped_column(Float)
    note: Mapped[str | None] = mapped_column(Text)
    original_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class MealPhotoAnalysis(Base):
    __tablename__ = "meal_photo_analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    meal_type: Mapped[str] = mapped_column(String(16))
    photo_path: Mapped[str] = mapped_column(Text)
    analysis_json: Mapped[str] = mapped_column(Text)
    confirmed_json: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    correction_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class MealTextAnalysis(Base):
    __tablename__ = "meal_text_analyses"
    __table_args__ = (UniqueConstraint("journal_event_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    journal_event_id: Mapped[int] = mapped_column(Integer, index=True)
    analysis_json: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    model: Mapped[str] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class MealTimeLog(Base):
    __tablename__ = "meal_time_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    meal_date: Mapped[date] = mapped_column(Date, index=True)
    meal_type: Mapped[str] = mapped_column(String(16), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source: Mapped[str] = mapped_column(String(32), default="telegram")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class FatSecretImport(Base):
    __tablename__ = "fatsecret_imports"
    __table_args__ = (UniqueConstraint("source_url"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    report_date: Mapped[date] = mapped_column(Date, index=True)
    source_url: Mapped[str] = mapped_column(Text)
    pdf_path: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="success", index=True)
    raw_text: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class FatSecretFoodEntry(Base):
    __tablename__ = "fatsecret_food_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    import_id: Mapped[int] = mapped_column(Integer, index=True)
    report_date: Mapped[date] = mapped_column(Date, index=True)
    meal_type: Mapped[str] = mapped_column(String(16), index=True)
    meal_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    food_name: Mapped[str] = mapped_column(Text)
    serving: Mapped[str | None] = mapped_column(Text)
    calories: Mapped[float | None] = mapped_column(Float)
    fat_g: Mapped[float | None] = mapped_column(Float)
    saturated_fat_g: Mapped[float | None] = mapped_column(Float)
    carbohydrates_g: Mapped[float | None] = mapped_column(Float)
    fiber_g: Mapped[float | None] = mapped_column(Float)
    sugar_g: Mapped[float | None] = mapped_column(Float)
    protein_g: Mapped[float | None] = mapped_column(Float)
    sodium_mg: Mapped[float | None] = mapped_column(Float)
    cholesterol_mg: Mapped[float | None] = mapped_column(Float)
    potassium_mg: Mapped[float | None] = mapped_column(Float)


class FatSecretAuthorization(Base):
    """OAuth 1.0 tokens for the single FatSecret account connected to this bot."""

    __tablename__ = "fatsecret_authorizations"
    __table_args__ = (UniqueConstraint("singleton_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    singleton_key: Mapped[str] = mapped_column(String(16), default="me")
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    request_token: Mapped[str | None] = mapped_column(Text)
    request_token_secret: Mapped[str | None] = mapped_column(Text)
    access_token: Mapped[str | None] = mapped_column(Text)
    access_token_secret: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class TrainingLog(Base):
    __tablename__ = "training_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source_type: Mapped[str] = mapped_column(String(16))
    original_text: Mapped[str | None] = mapped_column(Text)
    photo_path: Mapped[str | None] = mapped_column(Text)
    analysis_json: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class ProductivityCheckin(Base):
    __tablename__ = "productivity_checkins"
    __table_args__ = (UniqueConstraint("local_date", "period"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    local_date: Mapped[date] = mapped_column(Date, index=True)
    period: Mapped[str] = mapped_column(String(16))
    energy: Mapped[int | None] = mapped_column(Integer)
    sleep_quality: Mapped[int | None] = mapped_column(Integer)
    persistence: Mapped[int | None] = mapped_column(Integer)
    work_quality: Mapped[int | None] = mapped_column(Integer)
    focus: Mapped[int | None] = mapped_column(Integer)
    mood: Mapped[int | None] = mapped_column(Integer)
    stress: Mapped[int | None] = mapped_column(Integer)
    deep_work_min: Mapped[int | None] = mapped_column(Integer)
    priority: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    original_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class PersonalFact(Base):
    __tablename__ = "personal_facts"

    id: Mapped[int] = mapped_column(primary_key=True)
    statement: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="active")
    source_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Observation(Base):
    __tablename__ = "observations"
    __table_args__ = (UniqueConstraint("factor", "target", "period_start", "period_end"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    factor: Mapped[str] = mapped_column(String(64), index=True)
    target: Mapped[str] = mapped_column(String(64))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    direction: Mapped[str] = mapped_column(String(16))
    effect_size: Mapped[float | None] = mapped_column(Float)
    sample_size: Mapped[int] = mapped_column(Integer)
    confidence: Mapped[str] = mapped_column(String(16))
    tags_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(16), default="active")


class Hypothesis(Base):
    __tablename__ = "hypotheses"

    id: Mapped[int] = mapped_column(primary_key=True)
    observation_id: Mapped[int] = mapped_column(Integer)
    explanation: Mapped[str] = mapped_column(Text)
    alternatives_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(16), default="active")


class Experiment(Base):
    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    factor: Mapped[str] = mapped_column(String(64))
    outcome_metrics_json: Mapped[str] = mapped_column(Text)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="planned")
    result_json: Mapped[str | None] = mapped_column(Text)


class UserCorrection(Base):
    __tablename__ = "user_corrections"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(Integer)
    correction_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class InsightFeedback(Base):
    __tablename__ = "insight_feedback"
    __table_args__ = (UniqueConstraint("report_id", "item_type", "item_index"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(Integer, index=True)
    item_type: Mapped[str] = mapped_column(String(32))
    item_index: Mapped[int] = mapped_column(Integer)
    verdict: Mapped[str] = mapped_column(String(32))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class LlmUsage(Base):
    __tablename__ = "llm_usage"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    operation: Mapped[str] = mapped_column(String(32), index=True)
    model: Mapped[str] = mapped_column(String(64))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_creation_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    estimated: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default="success")
    metadata_json: Mapped[str | None] = mapped_column(Text)


class GeneratedReport(Base):
    __tablename__ = "generated_reports"
    __table_args__ = (UniqueConstraint("report_type", "period_start", "period_end", "context_hash"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    report_type: Mapped[str] = mapped_column(String(16))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16))
    model: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(32))
    context_hash: Mapped[str] = mapped_column(String(64))
    context_json: Mapped[str] = mapped_column(Text)
    draft_json: Mapped[str | None] = mapped_column(Text)
    markdown_path: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    telegram_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReportSource(Base):
    __tablename__ = "report_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(Integer, index=True)
    source_type: Mapped[str] = mapped_column(String(32))
    source_id: Mapped[int] = mapped_column(Integer)
