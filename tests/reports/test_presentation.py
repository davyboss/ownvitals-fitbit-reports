import pytest

from fitbit_report.reports.presentation import personal_metrics


def test_resting_heart_rate_quality_ratio_treats_lower_value_as_better():
    context = {
        "personal_state": {
            "current": {"resting_heart_rate": 60},
            "baseline_28d": {"resting_heart_rate": 66},
        }
    }

    resting_hr = next(
        metric for metric in personal_metrics(context, "en")
        if metric.key == "resting_hr"
    )

    assert resting_hr.raw_delta_percent == -9.090909090909092
    assert resting_hr.quality_ratio == pytest.approx(110)
