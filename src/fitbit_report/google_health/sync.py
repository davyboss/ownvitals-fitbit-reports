import hashlib
import json
from collections.abc import Iterable
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import delete
from sqlalchemy.orm import Session

from fitbit_report.db.models import (
    BodyMeasurement,
    DailyActivity,
    ExerciseSession,
    HeartRateDaily,
    HeartRateIntraday,
    HrvMeasurement,
    RawHealthRecord,
    SleepSession,
    SyncRun,
)
from fitbit_report.db.repositories import RawRecordRepository
from fitbit_report.google_health.normalization import normalize_data_points
from fitbit_report.google_health.schemas import (
    GoogleHealthAuthorizationRequired,
    GoogleHealthPermissionError,
    GoogleHealthRateLimitError,
    GoogleHealthTransientError,
)
from fitbit_report.types import SyncSummary


ROLLUP_DATA_TYPES = (
    "steps",
    "distance",
    "total-calories",
    "active-zone-minutes",
    "active-minutes",
)
LIST_DATA_TYPES = (
    "sleep",
    "exercise",
    "heart-rate",
    "daily-resting-heart-rate",
    "daily-heart-rate-variability",
    "heart-rate-variability",
    "weight",
    "body-fat",
)


class GoogleHealthSync:
    def __init__(self, client, timezone_name: str = "Europe/Kiev"):
        self.client = client
        self.timezone_name = timezone_name
        self.raw_records = RawRecordRepository()

    def sync_day(self, day: date, session: Session) -> SyncSummary:
        started = datetime.now(timezone.utc)
        fetched = 0
        inserted = 0
        normalized_rows: list[object] = []
        raw_payloads: list[tuple[str, dict]] = []
        try:
            # Fetching Google Health can take minutes when a request is
            # retried.  Do it before any database write, otherwise SQLite
            # stays locked and Telegram cannot save journal entries.
            for data_type in ROLLUP_DATA_TYPES:
                endpoint, payload = self._fetch_rollup(data_type, day)
                fetched += 1
                raw_payloads.append((endpoint, payload))
                normalized_rows.extend(normalize_data_points(payload, data_type, day))
            for data_type in LIST_DATA_TYPES:
                endpoint, payload = self._fetch_list(data_type, day)
                fetched += 1
                raw_payloads.append((endpoint, payload))
                normalized_rows.extend(normalize_data_points(payload, data_type, day))
        except GoogleHealthRateLimitError as exc:
            run = SyncRun(requested_date=day, started_at=started, status="running")
            session.add(run)
            return self._finish_failed_run(run, fetched, inserted, "rate_limit", exc, "rate_limited")
        except GoogleHealthAuthorizationRequired as exc:
            run = SyncRun(requested_date=day, started_at=started, status="running")
            session.add(run)
            return self._finish_failed_run(run, fetched, inserted, "authorization", exc, "failed")
        except GoogleHealthPermissionError as exc:
            run = SyncRun(requested_date=day, started_at=started, status="running")
            session.add(run)
            return self._finish_failed_run(run, fetched, inserted, "permission", exc, "failed")
        except GoogleHealthTransientError as exc:
            run = SyncRun(requested_date=day, started_at=started, status="running")
            session.add(run)
            return self._finish_failed_run(run, fetched, inserted, "transient", exc, "failed")

        run = SyncRun(requested_date=day, started_at=started, status="running")
        session.add(run)
        for endpoint, payload in raw_payloads:
            inserted += self._store_raw(session, endpoint, day, payload)
        normalized_count = self._replace_normalized(session, day, normalized_rows)
        run.status = "success"
        run.fetched_count = fetched
        run.inserted_count = inserted
        run.normalized_count = normalized_count
        run.finished_at = datetime.now(timezone.utc)
        return SyncSummary("success", day, fetched, inserted, normalized_count)

    def sync_range(self, start: date, end: date, session: Session) -> list[SyncSummary]:
        if end < start:
            raise ValueError("sync range end must not be before start")
        results = []
        current = start
        while current <= end:
            results.append(self.sync_day(current, session))
            # Do not keep the first day's write transaction open while the
            # next day is fetched over the network.
            session.commit()
            current += timedelta(days=1)
        return results

    def _fetch_rollup(self, data_type: str, day: date) -> tuple[str, dict]:
        endpoint = f"users/me/dataTypes/{data_type}/dataPoints:dailyRollUp"
        local_start = {"date": {"year": day.year, "month": day.month, "day": day.day}}
        next_day = day + timedelta(days=1)
        local_end = {
            "date": {"year": next_day.year, "month": next_day.month, "day": next_day.day}
        }
        payload = self.client.post_json(
            endpoint,
            {
                "range": {"start": local_start, "end": local_end},
                "windowSizeDays": 1,
                "pageSize": 1,
            },
        ).payload
        return endpoint, payload

    def _fetch_list(self, data_type: str, day: date) -> tuple[str, dict]:
        endpoint = f"users/me/dataTypes/{data_type}/dataPoints"
        next_day = day + timedelta(days=1)
        filter_name = data_type.replace("-", "_")
        if data_type == "sleep":
            filter_expression = (
                f'{filter_name}.interval.civil_end_time >= "{day.isoformat()}" AND '
                f'{filter_name}.interval.civil_end_time < "{next_day.isoformat()}"'
            )
        elif data_type == "exercise":
            filter_expression = (
                f'{filter_name}.interval.civil_start_time >= "{day.isoformat()}T00:00:00" AND '
                f'{filter_name}.interval.civil_start_time < "{next_day.isoformat()}T00:00:00"'
            )
        elif data_type in {"heart-rate", "heart-rate-variability", "weight", "body-fat"}:
            start_utc, end_utc = self._utc_day_bounds(day)
            filter_expression = (
                f'{filter_name}.sample_time.physical_time >= "{start_utc}" AND '
                f'{filter_name}.sample_time.physical_time < "{end_utc}"'
            )
        else:
            filter_expression = (
                f'{filter_name}.date >= "{day.isoformat()}" AND '
                f'{filter_name}.date < "{next_day.isoformat()}"'
            )
        items = list(self.client.list_pages(endpoint, params={"filter": filter_expression}))
        return endpoint, {"dataPoints": items}

    def _utc_day_bounds(self, day: date) -> tuple[str, str]:
        zone = ZoneInfo(self.timezone_name)
        start = datetime.combine(day, time.min, tzinfo=zone).astimezone(timezone.utc)
        end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone).astimezone(timezone.utc)
        return _format_api_datetime(start), _format_api_datetime(end)

    def _store_raw(self, session: Session, endpoint: str, day: date, payload: dict) -> int:
        payload_json = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        record = RawHealthRecord(
            provider="google_health",
            endpoint=endpoint,
            record_date=day,
            payload_json=payload_json,
            payload_hash=hashlib.sha256(payload_json.encode()).hexdigest(),
            fetched_at=datetime.now(timezone.utc),
        )
        changed = self.raw_records.add_or_update(session, record)
        return int(changed)

    def _replace_normalized(self, session: Session, day: date, rows: Iterable[object]) -> int:
        models = (
            SleepSession,
            DailyActivity,
            HeartRateDaily,
            HeartRateIntraday,
            HrvMeasurement,
            BodyMeasurement,
            ExerciseSession,
        )
        for model in models:
            session.execute(delete(model).where(model.record_date == day))

        activity: DailyActivity | None = None
        count = 0
        for row in rows:
            if isinstance(row, DailyActivity):
                activity = _merge_activity(activity, row)
            else:
                session.add(row)
                count += 1
        if activity is not None:
            session.add(activity)
            count += 1
        return count

    @staticmethod
    def _finish_failed_run(
        run: SyncRun,
        fetched: int,
        inserted: int,
        error_type: str,
        exc: Exception,
        status: str,
    ) -> SyncSummary:
        run.status = status
        run.error_type = error_type
        run.error_message = str(exc)
        run.fetched_count = fetched
        run.inserted_count = inserted
        run.finished_at = datetime.now(timezone.utc)
        return SyncSummary(status, run.requested_date, fetched, inserted, error_type=error_type)


def _merge_activity(current: DailyActivity | None, incoming: DailyActivity) -> DailyActivity:
    if current is None:
        return incoming
    for field in ("steps", "distance", "calories_out", "active_zone_minutes"):
        value = getattr(incoming, field)
        if value is not None:
            setattr(current, field, value)
    return current


def _format_api_datetime(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")
