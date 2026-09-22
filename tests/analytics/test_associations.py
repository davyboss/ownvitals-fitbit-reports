from fitbit_report.analytics.associations import (
    LaggedDayFeatures,
    find_associations,
)


def test_association_reports_sample_size_and_direction():
    rows = [
        LaggedDayFeatures(target_productivity=8, caffeine_after_15h=0),
        LaggedDayFeatures(target_productivity=4, caffeine_after_15h=1),
        LaggedDayFeatures(target_productivity=9, caffeine_after_15h=0),
        LaggedDayFeatures(target_productivity=5, caffeine_after_15h=1),
        LaggedDayFeatures(target_productivity=8, caffeine_after_15h=0),
    ]

    results = find_associations(rows, target="target_productivity")
    caffeine = next(item for item in results if item.factor == "caffeine_after_15h")

    assert caffeine.sample_size == 5
    assert caffeine.direction == "negative"
    assert caffeine.group_counts == {"0": 3, "1": 2}
