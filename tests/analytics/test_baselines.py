from fitbit_report.analytics.baselines import compute_baseline


def test_compute_baseline_ignores_missing_values():
    baseline = compute_baseline([8.0, None, 10.0, 12.0], window_days=28)

    assert baseline.sample_size == 3
    assert baseline.mean == 10.0
    assert baseline.median == 10.0


def test_compute_baseline_marks_small_sample_insufficient():
    baseline = compute_baseline([8.0, 10.0], window_days=7)

    assert baseline.status == "insufficient"
