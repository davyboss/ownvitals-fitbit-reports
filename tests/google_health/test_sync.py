from datetime import date

from fitbit_report.db.models import ExerciseSession, RawHealthRecord
from fitbit_report.google_health.schemas import GoogleHealthResponse
from fitbit_report.google_health.sync import GoogleHealthSync


class FakeGoogleHealthClient:
    def __init__(self):
        self.calls = []
        self.exercise_item = None

    def post_json(self, path, body):
        self.calls.append(("POST", path, body))
        if path.endswith("/steps/dataPoints:dailyRollUp"):
            return GoogleHealthResponse(
                status_code=200,
                payload={"rollupDataPoints": [{"steps": {"countSum": "8123"}}]},
            )
        return GoogleHealthResponse(status_code=200, payload={"rollupDataPoints": []})

    def list_pages(self, path, params=None):
        self.calls.append(("GET", path, params))
        if path.endswith("/sleep/dataPoints"):
            yield {
                "sleep": {
                    "interval": {
                        "startTime": "2026-08-12T22:00:00Z",
                        "endTime": "2026-08-13T06:00:00Z",
                    },
                    "summary": {"minutesAsleep": "420"},
                }
            }
        if path.endswith("/exercise/dataPoints") and self.exercise_item is not None:
            yield self.exercise_item


def test_sync_day_fetches_supported_data_types_and_is_idempotent(db_session):
    client = FakeGoogleHealthClient()
    sync = GoogleHealthSync(client)

    first = sync.sync_day(date(2026, 8, 12), db_session)
    second = sync.sync_day(date(2026, 8, 12), db_session)

    assert first.status == "success"
    assert first.fetched > 0
    assert second.inserted == 0
    assert db_session.query(RawHealthRecord).count() == first.fetched
    assert any(path.endswith("/steps/dataPoints:dailyRollUp") for _, path, _ in client.calls)
    assert any(path.endswith("/exercise/dataPoints") for _, path, _ in client.calls)


def test_sync_day_normalizes_exercise_sessions(db_session):
    client = FakeGoogleHealthClient()
    client.exercise_item = {
        "exercise": {
            "interval": {
                "startTime": "2026-08-12T18:00:00Z",
                "endTime": "2026-08-12T18:35:00Z",
            },
            "exerciseType": "RUNNING",
            "activeDuration": "1800s",
            "metricsSummary": {"caloriesKcal": 380.0},
        }
    }
    summary = GoogleHealthSync(client).sync_day(date(2026, 8, 12), db_session)

    workout = db_session.query(ExerciseSession).one()
    assert summary.status == "success"
    assert workout.exercise_type == "RUNNING"
    assert workout.active_duration_min == 30


def test_daily_rollup_for_one_day_requests_one_window(db_session):
    client = FakeGoogleHealthClient()
    sync = GoogleHealthSync(client)

    sync._fetch_rollup("steps", date(2026, 8, 12))

    _, endpoint, body = client.calls[0]
    assert endpoint.endswith("/steps/dataPoints:dailyRollUp")
    assert body["windowSizeDays"] == 1
    assert body["pageSize"] == 1


def test_exercise_filter_uses_local_civil_day_bounds():
    client = FakeGoogleHealthClient()
    sync = GoogleHealthSync(client, timezone_name="Europe/Kiev")

    sync._fetch_list("exercise", date(2026, 8, 12))

    _, endpoint, params = client.calls[-1]
    assert endpoint.endswith("/exercise/dataPoints")
    assert params["filter"] == (
        'exercise.interval.civil_start_time >= "2026-08-12T00:00:00" AND '
        'exercise.interval.civil_start_time < "2026-08-13T00:00:00"'
    )


def test_sync_replaces_changed_raw_payload(db_session):
    client = FakeGoogleHealthClient()
    sync = GoogleHealthSync(client)

    first = sync.sync_day(date(2026, 8, 12), db_session)
    original = db_session.query(RawHealthRecord).filter(
        RawHealthRecord.endpoint.endswith("/steps/dataPoints:dailyRollUp")
    ).one()
    original_hash = original.payload_hash

    client.post_json = lambda path, body: GoogleHealthResponse(
        status_code=200,
        payload={"rollupDataPoints": [{"steps": {"countSum": "9999"}}]}
        if path.endswith("/steps/dataPoints:dailyRollUp")
        else {"rollupDataPoints": []},
    )
    second = sync.sync_day(date(2026, 8, 12), db_session)

    updated = db_session.query(RawHealthRecord).filter(
        RawHealthRecord.endpoint.endswith("/steps/dataPoints:dailyRollUp")
    ).one()
    assert first.inserted > 0
    assert second.inserted > 0
    assert updated.payload_hash != original_hash
    assert db_session.query(RawHealthRecord).count() == first.fetched
