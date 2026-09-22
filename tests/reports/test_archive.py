from fitbit_report.reports.archive import list_report_paths, read_report


def test_list_report_paths_returns_newest_first(tmp_path):
    daily = tmp_path / "Health" / "Daily"
    daily.mkdir(parents=True)
    old = daily / "2026-08-10.md"
    new = daily / "2026-08-12.md"
    old.write_text("old", encoding="utf-8")
    new.write_text("new", encoding="utf-8")

    assert list_report_paths(tmp_path, "daily") == [new, old]


def test_read_report_returns_existing_markdown(tmp_path):
    path = tmp_path / "report.md"
    path.write_text("# report", encoding="utf-8")

    assert read_report(path) == "# report"
