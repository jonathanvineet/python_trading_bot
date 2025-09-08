import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(log_level: str = "INFO", log_dir: str = "logs") -> None:
    """Configure root logger with console + rotating file handlers.

    Args:
        log_level: Minimum log level.
        log_dir: Directory to write log file.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)
    logger = logging.getLogger()
    if logger.handlers:
        # Already configured
        return

    logger.setLevel(level)

    Path(log_dir).mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        Path(log_dir) / "trading_bot.log", maxBytes=2_000_000, backupCount=5
    )
    file_fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )
    file_handler.setFormatter(file_fmt)
    file_handler.setLevel(level)

    console_handler = logging.StreamHandler()
    console_fmt = logging.Formatter("%(levelname)s: %(message)s")
    console_handler.setFormatter(console_fmt)
    console_handler.setLevel(level)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
