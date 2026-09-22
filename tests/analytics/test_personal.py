from datetime import date, datetime, timezone

from fitbit_report.analytics.personal import build_personal_state


def test_personal_state_compares_current_values_with_personal_baseline():
    state = build_personal_state(
        as_of=date(2026, 8, 12),
        baselines={"windows": {"28d": {"metrics": {
            "sleep.minutes_asleep": {"average": 480},
            "heart_rate.resting_heart_rate": {"average": 55},
            "hrv.rmssd": {"average": 50},
        }}}},
        health={
            "sleep": [{
                "record_date": date(2026, 8, 12),
                "minutes_asleep": 390,
                "start_time": datetime(2026, 8, 11, 23, 40, tzinfo=timezone.utc),
                "end_time": datetime(2026, 8, 12, 6, 10, tzinfo=timezone.utc),
            }],
            "activity": [],
            "heart_rate": [{"record_date": date(2026, 8, 12), "resting_heart_rate": 62}],
            "hrv": [{"record_date": date(2026, 8, 12), "rmssd": 40}],
            "gym_training": [],
        },
        productivity_context={"days": []},
        personal_factors=[],
    )

    assert state["readiness"]["score"] < 50
    assert state["readiness"]["status"] == "сниженное"
    assert state["readiness"]["base_score"] == 50
    assert sum(
        item["points"] for item in state["readiness"]["contributions"]
    ) == state["readiness"]["score"] - 50
    assert [
        item["label"] for item in state["readiness"]["contributions"]
    ] == ["Сон", "Пульс покоя", "ВСР"]
    assert state["deviations"]["sleep_minutes"]["difference"] == -90
    assert state["current"]["sleep_start_time"].hour == 23
    assert state["current"]["sleep_end_time"].hour == 6


def test_personal_state_localizes_generated_text_to_english():
    state = build_personal_state(
        as_of=date(2026, 8, 12),
        baselines={"windows": {"28d": {"metrics": {
            "sleep.minutes_asleep": {"average": 480},
            "heart_rate.resting_heart_rate": {"average": 55},
            "hrv.rmssd": {"average": 50},
        }}}},
        health={
            "sleep": [{"record_date": date(2026, 8, 12), "minutes_asleep": 390}],
            "activity": [],
            "heart_rate": [{"record_date": date(2026, 8, 12), "resting_heart_rate": 62}],
            "hrv": [{"record_date": date(2026, 8, 12), "rmssd": 40}],
            "gym_training": [],
        },
        productivity_context={"days": []},
        personal_factors=[],
        locale="en",
    )

    assert state["readiness"]["status"] == "reduced"
    assert state["readiness"]["contributions"][0]["label"] == "Sleep"
    assert "sleep is notably shorter" in state["readiness"]["reasons"][0]
    assert state["disclaimer"].startswith("This is an exploratory")


def test_personal_state_exposes_readiness_contributions_for_daily_chart():
    state = build_personal_state(
        as_of=date(2026, 9, 15),
        baselines={"windows": {"28d": {"metrics": {
            "sleep.minutes_asleep": {"average": 558.4},
            "heart_rate.resting_heart_rate": {"average": 64.8},
            "hrv.rmssd": {"average": 106.3},
            "productivity.energy": {"average": 4.3},
        }}}},
        health={
            "sleep": [{"record_date": date(2026, 9, 15), "minutes_asleep": 652}],
            "activity": [],
            "heart_rate": [
                {"record_date": date(2026, 9, 15), "resting_heart_rate": 60}
            ],
            "hrv": [{"record_date": date(2026, 9, 15), "rmssd": 137.6}],
            "gym_training": [],
        },
        productivity_context={
            "days": [{"date": date(2026, 9, 15), "morning": {"energy": 7}}]
        },
        personal_factors=[],
    )

    assert state["readiness"]["score"] == 76
    assert [
        item["points"] for item in state["readiness"]["contributions"]
    ] == [8, 6, 7, 5.4]
