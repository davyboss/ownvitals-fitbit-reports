import logging
from logging.handlers import RotatingFileHandler

from fitbit_report.config import Settings
from fitbit_report.private_storage import ensure_private_directory, restrict_private_file


def configure_logging(settings: Settings) -> None:
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    log_dir = settings.log_dir
    ensure_private_directory(log_dir)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if root.handlers:
        return

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    file_handler = RotatingFileHandler(
        log_dir / "fitbit-report.log",
        maxBytes=2_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    restrict_private_file(log_dir / "fitbit-report.log")
    file_handler.setFormatter(formatter)
    root.addHandler(console)
    root.addHandler(file_handler)
