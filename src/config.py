"""Configuration module for the md-to-confluence application."""

import logging
import logging.handlers
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

# import os

# Base directories
PROJECT_ROOT = Path(__file__).parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# Logging configuration
LOG_FILE = LOGS_DIR / "md_to_confluence.log"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
LOG_BACKUP_COUNT = 5


def setup_logging(level: int = logging.INFO) -> None:
    """Set up logging configuration for the application.

    Args:
        level: The logging level to use. Defaults to logging.INFO.
    """
    # Create file handler with append mode
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE,
        mode="a",  # Append mode
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
    )

    # Create formatter and add it to handler
    formatter = logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT)
    file_handler.setFormatter(formatter)

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove any existing handlers (to avoid duplicates)
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add file handler to the logger
    root_logger.addHandler(file_handler)

    # Add session marker to the log file
    session_start = datetime.now().strftime(LOG_DATE_FORMAT)
    logging.info("=" * 80)
    logging.info(f"New session started at {session_start}")
    logging.info("=" * 80)


def get_confluence_pat_1password(op_item="ConfluencePAT") -> str:
    """Get the Confluence PAT from 1password."""

    OP_BINARY_NAME = "op"
    if not shutil.which(OP_BINARY_NAME):
        raise FileNotFoundError(
            "1Password CLI not found. Install it from https://1password.com/downloads/"
        )
    try:
        result = subprocess.run(
            [OP_BINARY_NAME, "item", "get", op_item, "--fields", "label=notesPlain"],
            check=True,
            capture_output=True,
        )
        return result.stdout.decode("utf-8").strip()
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to read 1Password item {op_item}") from e
