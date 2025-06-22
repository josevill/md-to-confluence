"""Configuration module for the md-to-confluence application."""

import json
import logging
import logging.handlers
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

# Logging configuration
PROJECT_ROOT = Path(__file__).parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"
LOGS_DIR.mkdir(exist_ok=True)
LOG_FILE = LOGS_DIR / "md_to_confluence.log"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
LOG_BACKUP_COUNT = 5

# Configuration validation
REQUIRED_CONFIG_KEYS = {
    "confluence": ["base_url", "space_key"],
    "sync": ["docs_dir"],
}

OPTIONAL_CONFIG_KEYS = {
    "confluence": ["token_1password_item", "retry_max_attempts", "retry_backoff_factor"],
    "sync": ["initial_scan", "debounce_delay"],
    "ui": ["refresh_interval", "log_lines"],
}


def setup_logging(level: int = logging.INFO, logs_dir: Optional[Path] = None) -> None:
    """Set up logging configuration for the application.

    Args:
        level: The logging level to use. Defaults to logging.INFO.
        logs_dir: Optional logs directory. Defaults to global LOGS_DIR.
    """
    target_logs_dir = logs_dir if logs_dir is not None else LOGS_DIR
    target_logs_dir.mkdir(exist_ok=True)
    log_file = target_logs_dir / "md_to_confluence.log"

    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        mode="a",  # Append mode
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
    )

    formatter = logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT)
    file_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    root_logger.addHandler(file_handler)

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


def validate_configuration(config: Dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate configuration structure and required fields.

    Args:
        config: Configuration dictionary to validate

    Returns:
        Tuple of (is_valid, error_messages)
    """
    errors = []

    for section, required_keys in REQUIRED_CONFIG_KEYS.items():
        if section not in config:
            errors.append(f"Missing required section: {section}")
            continue

        if not isinstance(config[section], dict):
            errors.append(f"Section '{section!r}' must be a dictionary")
            continue

        for key in required_keys:
            if key not in config[section]:
                errors.append(f"Missing required key: {section}.{key}")
            elif not config[section][key]:  # Check for empty values
                errors.append(f"Empty value for required key: {section}.{key}")

    if "confluence" in config and isinstance(config["confluence"], dict):
        base_url = config["confluence"].get("base_url")
        if base_url and not (base_url.startswith("http://") or base_url.startswith("https://")):
            errors.append("confluence.base_url must start with http:// or https://")

    if "sync" in config and isinstance(config["sync"], dict):
        docs_dir = config["sync"].get("docs_dir")
        if docs_dir:
            docs_path = Path(docs_dir)
            if not docs_path.exists():
                errors.append(f"sync.docs_dir path does not exist: {docs_dir}")
            elif not docs_path.is_dir():
                errors.append(f"sync.docs_dir is not a directory: {docs_dir}")

    return len(errors) == 0, errors


def load_and_validate_config(config_path: Path) -> tuple[Optional[Dict[str, Any]], list[str]]:
    """Load and validate configuration from file.

    Args:
        config_path: Path to configuration file

    Returns:
        Tuple of (config_dict or None, error_messages)
    """
    errors = []

    try:
        if not config_path.exists():
            return None, [f"Configuration file not found: {config_path}"]

        with config_path.open("r", encoding="utf-8") as f:
            config = json.load(f)

        is_valid, validation_errors = validate_configuration(config)
        if not is_valid:
            errors.extend(validation_errors)

        return config if is_valid else None, errors

    except json.JSONDecodeError as e:
        return None, [f"Invalid JSON in configuration file: {e}"]
    except PermissionError:
        return None, [f"Permission denied reading configuration file: {config_path}"]
    except Exception as e:
        return None, [f"Error loading configuration: {e}"]


def create_default_config() -> Dict[str, Any]:
    """Create a default configuration structure.

    Returns:
        Default configuration dictionary
    """
    return {
        "confluence": {
            "base_url": "https://your-domain.atlassian.net",
            "space_key": "YOUR_SPACE_KEY",
            "token_1password_item": "ConfluencePAT",
            "retry_max_attempts": 3,
            "retry_backoff_factor": 1.0,
        },
        "sync": {"docs_dir": "docs", "initial_scan": True, "debounce_delay": 2.0},
        "ui": {"refresh_interval": 1.0, "log_lines": 100},
    }


def validate_token_format(token: str) -> bool:
    """Validate that a token follows expected format patterns.

    Args:
        token: The token to validate

    Returns:
        True if token format is valid
    """
    if not token or not isinstance(token, str):
        return False

    # Remove whitespace
    token = token.strip()

    # Basic length check (Confluence PATs are typically long)
    if len(token) < 20:
        return False

    # Should contain only alphanumeric characters and common special chars
    if not re.match(r"^[A-Za-z0-9+/=_-]+$", token):
        return False

    return True


def sanitize_url(url: str) -> str:
    """Sanitize a URL to prevent injection attacks.

    Args:
        url: The URL to sanitize

    Returns:
        Sanitized URL
    """
    if not url:
        return ""

    # Remove whitespace
    url = url.strip()

    # Ensure it starts with http:// or https://
    if not url.startswith("https://"):
        raise ValueError("URL must start with https://")

    # Remove any potentially dangerous characters
    # Allow only alphanumeric, dots, hyphens, slashes, colons, and query params
    if not re.match(
        r"^https?://[A-Za-z0-9.-]+(?::\d+)?(?:/[A-Za-z0-9._~:/?#[\]@!$&\'()*+,;=-]*)?$", url
    ):
        raise ValueError("URL contains invalid characters")

    return url


def sanitize_space_key(space_key: str) -> str:
    """Sanitize a Confluence space key.

    Args:
        space_key: The space key to sanitize

    Returns:
        Sanitized space key
    """
    if not space_key:
        return ""

    # Remove whitespace
    space_key = space_key.strip()

    # Confluence space keys should only contain uppercase letters, numbers, and underscores
    if not re.match(r"^[A-Z0-9_]+$", space_key):
        raise ValueError("Space key must contain only uppercase letters, numbers, and underscores")

    return space_key


def sanitize_file_path(file_path: str, base_dir: Path) -> Path:
    """Sanitize a file path to prevent directory traversal attacks.

    Args:
        file_path: The file path to sanitize
        base_dir: The base directory that paths should be relative to

    Returns:
        Sanitized Path object

    Raises:
        ValueError: If path is invalid or attempts directory traversal
    """
    if not file_path:
        raise ValueError("File path cannot be empty")

    # Convert to Path and resolve
    path = Path(file_path)

    # If it's absolute, make it relative to base_dir
    if path.is_absolute():
        try:
            path = path.relative_to(base_dir)
        except ValueError as e:
            raise ValueError(f"Absolute path is not within base directory: {file_path}") from e

    # Resolve the full path relative to base_dir
    full_path = (base_dir / path).resolve()

    # Ensure the resolved path is still within base_dir
    try:
        full_path.relative_to(base_dir.resolve())
    except ValueError as e:
        raise ValueError(f"Path traversal detected: {file_path}") from e

    return full_path


def secure_get_confluence_pat(op_item: str = "ConfluencePAT") -> str:
    """Securely get the Confluence PAT from 1password with validation.

    Args:
        op_item: The 1Password item name

    Returns:
        The validated PAT token

    Raises:
        ValueError: If token format is invalid
        RuntimeError: If 1Password operation fails
        FileNotFoundError: If 1Password CLI is not found
    """
    # Sanitize the op_item name
    op_item = re.sub(r"[^A-Za-z0-9_-]", "", op_item)
    if not op_item:
        raise ValueError("Invalid 1Password item name")

    token = get_confluence_pat_1password(op_item)

    if not validate_token_format(token):
        raise ValueError("Retrieved token does not match expected format")

    return token
