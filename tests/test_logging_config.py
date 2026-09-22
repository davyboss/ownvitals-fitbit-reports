import logging
from types import SimpleNamespace

from fitbit_report.logging_config import configure_logging


def test_configure_logging_hides_http_request_urls(monkeypatch, tmp_path):
    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", [])
    settings = SimpleNamespace(log_dir=tmp_path)

    configure_logging(settings)

    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING
