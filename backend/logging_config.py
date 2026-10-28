"""
ATBot — Dedicated Date-wise Logging System
Saves logs date-by-date into:
  - logs/requests_YYYY-MM-DD.log  (API request telemetry & latencies)
  - logs/errors_YYYY-MM-DD.log    (Dedicated ERROR & CRITICAL stack traces)
  - logs/app_YYYY-MM-DD.log       (Full application events, scheduler, engines)
"""

import os
import sys
import logging
from datetime import datetime, date
from typing import Optional

# Safe UTF-8 console output for Windows terminals (avoid UnicodeEncodeError on emojis)
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Path to the logs directory at project root
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
DEFAULT_LOG_DIR = os.path.join(PROJECT_ROOT, "logs")


class DailyFileHandler(logging.Handler):
    """
    Thread-safe daily rotating file handler that writes directly to
    prefix_YYYY-MM-DD.log without cumbersome file renames.
    Automatically rolls over to a new file when the date changes.
    """
    def __init__(self, log_dir: str, prefix: str, encoding: str = "utf-8", retention_days: int = 30):
        super().__init__()
        self.log_dir = os.path.abspath(log_dir)
        self.prefix = prefix
        self.encoding = encoding
        self.retention_days = retention_days
        self.current_date: Optional[date] = None
        self._stream = None
        os.makedirs(self.log_dir, exist_ok=True)
        self._cleanup_old_logs()

    def _get_filename(self, d: date) -> str:
        return os.path.join(self.log_dir, f"{self.prefix}_{d.strftime('%Y-%m-%d')}.log")

    def _cleanup_old_logs(self):
        """Purge logs older than retention_days."""
        try:
            today = datetime.now().date()
            for fname in os.listdir(self.log_dir):
                if fname.startswith(f"{self.prefix}_") and fname.endswith(".log"):
                    try:
                        date_str = fname[len(self.prefix) + 1 : -4]
                        fdate = datetime.strptime(date_str, "%Y-%m-%d").date()
                        if (today - fdate).days > self.retention_days:
                            os.remove(os.path.join(self.log_dir, fname))
                    except Exception:
                        pass
        except Exception:
            pass

    def _ensure_stream(self):
        today = datetime.now().date()
        if self._stream is None or self.current_date != today:
            if self._stream is not None:
                try:
                    self._stream.flush()
                    self._stream.close()
                except Exception:
                    pass
            self.current_date = today
            self._cleanup_old_logs()
            filepath = self._get_filename(today)
            self._stream = open(filepath, "a", encoding=self.encoding)

    def emit(self, record: logging.LogRecord):
        try:
            self._ensure_stream()
            msg = self.format(record)
            self._stream.write(msg + "\n")
            self._stream.flush()
        except Exception:
            self.handleError(record)

    def close(self):
        self.acquire()
        try:
            if self._stream is not None:
                try:
                    self._stream.flush()
                    self._stream.close()
                except Exception:
                    pass
                self._stream = None
        finally:
            self.release()
        super().close()


def setup_logging(log_dir: str = DEFAULT_LOG_DIR, debug: bool = True):
    """
    Configures console and date-wise file logging for ATBot:
      1. Console: Standard stdout stream
      2. App file: logs/app_YYYY-MM-DD.log (INFO+)
      3. Error file: logs/errors_YYYY-MM-DD.log (ERROR+)
      4. Requests file: logs/requests_YYYY-MM-DD.log (API HTTP requests)
    """
    os.makedirs(log_dir, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if debug else logging.INFO)

    # Clear existing handlers to prevent duplicates
    for h in list(root_logger.handlers):
        root_logger.removeHandler(h)

    # --- Formatters ---
    standard_formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    request_formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 1. Console Handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO if debug else logging.WARNING)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # 2. Daily Application Log (app_YYYY-MM-DD.log)
    app_handler = DailyFileHandler(log_dir=log_dir, prefix="app", retention_days=30)
    app_handler.setLevel(logging.INFO if debug else logging.WARNING)
    app_handler.setFormatter(standard_formatter)
    root_logger.addHandler(app_handler)

    # 3. Daily Dedicated Error Log (errors_YYYY-MM-DD.log)
    error_handler = DailyFileHandler(log_dir=log_dir, prefix="errors", retention_days=30)
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(standard_formatter)
    root_logger.addHandler(error_handler)

    # 4. Dedicated API Requests Logger (requests_YYYY-MM-DD.log)
    request_logger = logging.getLogger("atbot.requests")
    request_logger.setLevel(logging.INFO)
    request_logger.propagate = False
    for h in list(request_logger.handlers):
        request_logger.removeHandler(h)

    req_handler = DailyFileHandler(log_dir=log_dir, prefix="requests", retention_days=30)
    req_handler.setLevel(logging.INFO)
    req_handler.setFormatter(request_formatter)
    request_logger.addHandler(req_handler)

    # Quiet overly chatty third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("yfinance").setLevel(logging.WARNING)
    logging.getLogger("passlib").setLevel(logging.WARNING)
    logging.getLogger("watchfiles").setLevel(logging.WARNING)

    logging.info(f"Date-wise file logging initialized at: {log_dir}")
    return root_logger


def get_request_logger() -> logging.Logger:
    """Return the dedicated logger for API requests."""
    return logging.getLogger("atbot.requests")
