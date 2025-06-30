"""Tests for the config module."""

import json
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.config import (
    LOG_BACKUP_COUNT,
    LOG_DATE_FORMAT,
    LOG_FORMAT,
    LOG_MAX_BYTES,
    OPTIONAL_CONFIG_KEYS,
    REQUIRED_CONFIG_KEYS,
    create_default_config,
    get_confluence_pat_1password,
    load_and_validate_config,
    sanitize_file_path,
    sanitize_space_key,
    sanitize_url,
    secure_get_confluence_pat,
    setup_logging,
    validate_configuration,
    validate_token_format,
)


class TestLoggingSetup:
    """Test logging configuration setup."""

    def test_setup_logging_default(self, tmp_path):
        """Test default logging setup."""
        logs_dir = tmp_path / "logs"
        setup_logging(logs_dir=logs_dir)

        # Check that log directory was created
        assert logs_dir.exists()
        assert logs_dir.is_dir()

        # Check that log file exists
        log_file = logs_dir / "md_to_confluence.log"
        assert log_file.exists()

        # Check root logger configuration
        root_logger = logging.getLogger()
        assert root_logger.level == logging.INFO
        assert len(root_logger.handlers) == 1

        handler = root_logger.handlers[0]
        assert isinstance(handler, logging.handlers.RotatingFileHandler)
        assert handler.maxBytes == LOG_MAX_BYTES
        assert handler.backupCount == LOG_BACKUP_COUNT

    def test_setup_logging_custom_level(self, tmp_path):
        """Test logging setup with custom level."""
        logs_dir = tmp_path / "logs"
        setup_logging(level=logging.DEBUG, logs_dir=logs_dir)

        root_logger = logging.getLogger()
        assert root_logger.level == logging.DEBUG

    def test_setup_logging_session_marker(self, tmp_path):
        """Test that session markers are written to log."""
        logs_dir = tmp_path / "logs"
        setup_logging(logs_dir=logs_dir)

        log_file = logs_dir / "md_to_confluence.log"
        content = log_file.read_text()
        assert "New session started at" in content
        assert "=" * 80 in content

    def test_setup_logging_handler_replacement(self, tmp_path):
        """Test that existing handlers are replaced."""
        # Add a handler first
        root_logger = logging.getLogger()
        old_handler = logging.StreamHandler()
        root_logger.addHandler(old_handler)

        logs_dir = tmp_path / "logs"
        setup_logging(logs_dir=logs_dir)

        # Should only have the new file handler
        assert len(root_logger.handlers) == 1
        assert old_handler not in root_logger.handlers


class TestOnePasswordIntegration:
    """Test 1Password CLI integration."""

    @patch("src.config.shutil.which")
    @patch("src.config.subprocess.run")
    def test_get_confluence_pat_1password_success(self, mock_run, mock_which):
        """Test successful PAT retrieval from 1Password."""
        # Mock that op CLI is available
        mock_which.return_value = "/usr/local/bin/op"

        # Mock successful subprocess call
        mock_result = Mock()
        mock_result.stdout = b"ATTv1xGDM0MjM5NDc2MDctYWJjZC1lZmdhLWIxMjMtNDU2Nzg5YWJjZGVm\n"
        mock_run.return_value = mock_result

        token = get_confluence_pat_1password("TestPAT")

        assert token == "ATTv1xGDM0MjM5NDc2MDctYWJjZC1lZmdhLWIxMjMtNDU2Nzg5YWJjZGVm"
        mock_run.assert_called_once_with(
            ["op", "item", "get", "TestPAT", "--fields", "label=notesPlain"],
            check=True,
            capture_output=True,
        )

    @patch("src.config.shutil.which")
    def test_get_confluence_pat_1password_cli_not_found(self, mock_which):
        """Test error when 1Password CLI is not found."""
        mock_which.return_value = None

        with pytest.raises(FileNotFoundError, match="1Password CLI not found"):
            get_confluence_pat_1password()

    @patch("src.config.shutil.which")
    @patch("src.config.subprocess.run")
    def test_get_confluence_pat_1password_subprocess_error(self, mock_run, mock_which):
        """Test error when subprocess fails."""
        mock_which.return_value = "/usr/local/bin/op"
        mock_run.side_effect = subprocess.CalledProcessError(1, "op")

        with pytest.raises(RuntimeError, match="Failed to read 1Password item"):
            get_confluence_pat_1password("FailPAT")

    @patch("src.config.shutil.which")
    @patch("src.config.subprocess.run")
    def test_secure_get_confluence_pat(self, mock_run, mock_which):
        """Test secure PAT retrieval wrapper."""
        mock_which.return_value = "/usr/local/bin/op"
        mock_result = Mock()
        mock_result.stdout = b"ATTv1xValidPATToken12345\n"
        mock_run.return_value = mock_result

        token = secure_get_confluence_pat("SecurePAT")
        assert token == "ATTv1xValidPATToken12345"


class TestConfigurationValidation:
    """Test configuration validation."""

    def test_validate_configuration_valid_minimal(self):
        """Test validation with minimal valid config."""
        config = {
            "confluence": {
                "base_url": "https://example.atlassian.net",
                "space_key": "DOCS",
            },
            "sync": {
                "docs_dir": "docs",
            },
        }

        is_valid, errors = validate_configuration(config)
        assert is_valid
        assert len(errors) == 0

    def test_validate_configuration_missing_section(self):
        """Test validation with missing required section."""
        config = {
            "confluence": {
                "base_url": "https://example.atlassian.net",
                "space_key": "DOCS",
            },
            # Missing sync section
        }

        is_valid, errors = validate_configuration(config)
        assert not is_valid
        assert "Missing required section: sync" in errors

    def test_validate_configuration_missing_required_key(self):
        """Test validation with missing required key."""
        config = {
            "confluence": {
                "base_url": "https://example.atlassian.net",
                # Missing space_key
            },
            "sync": {
                "docs_dir": "docs",
            },
        }

        is_valid, errors = validate_configuration(config)
        assert not is_valid
        assert "Missing required key: confluence.space_key" in errors

    def test_validate_configuration_empty_value(self):
        """Test validation with empty required value."""
        config = {
            "confluence": {
                "base_url": "",
                "space_key": "DOCS",
            },
            "sync": {
                "docs_dir": "docs",
            },
        }

        is_valid, errors = validate_configuration(config)
        assert not is_valid
        assert "Empty value for required key: confluence.base_url" in errors

    def test_validate_configuration_invalid_url(self):
        """Test validation with invalid URL format."""
        config = {
            "confluence": {
                "base_url": "not-a-valid-url",
                "space_key": "DOCS",
            },
            "sync": {
                "docs_dir": "docs",
            },
        }

        is_valid, errors = validate_configuration(config)
        assert not is_valid
        assert "confluence.base_url must start with http:// or https://" in errors

    def test_validate_configuration_nonexistent_docs_dir(self):
        """Test validation with non-existent docs directory."""
        config = {
            "confluence": {
                "base_url": "https://example.atlassian.net",
                "space_key": "DOCS",
            },
            "sync": {
                "docs_dir": "/nonexistent/path",
            },
        }

        is_valid, errors = validate_configuration(config)
        assert not is_valid
        assert "sync.docs_dir path does not exist:" in errors[0]

    def test_validate_configuration_docs_dir_not_directory(self, tmp_path):
        """Test validation when docs_dir is not a directory."""
        # Create a file instead of directory
        not_dir = tmp_path / "not_a_directory.txt"
        not_dir.write_text("content")

        config = {
            "confluence": {
                "base_url": "https://example.atlassian.net",
                "space_key": "DOCS",
            },
            "sync": {
                "docs_dir": str(not_dir),
            },
        }

        is_valid, errors = validate_configuration(config)
        assert not is_valid
        assert "sync.docs_dir is not a directory:" in errors[0]

    def test_validate_configuration_section_not_dict(self):
        """Test validation when section is not a dictionary."""
        config = {
            "confluence": "not a dict",
            "sync": {
                "docs_dir": "docs",
            },
        }

        is_valid, errors = validate_configuration(config)
        assert not is_valid
        assert "Section ''confluence'' must be a dictionary" in errors


class TestConfigurationLoading:
    """Test configuration file loading and validation."""

    def test_load_and_validate_config_success(self, tmp_path):
        """Test successful config loading."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        config_data = {
            "confluence": {
                "base_url": "https://example.atlassian.net",
                "space_key": "DOCS",
            },
            "sync": {
                "docs_dir": str(docs_dir),
            },
        }

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config_data, indent=2))

        config, errors = load_and_validate_config(config_file)
        assert config is not None
        assert len(errors) == 0
        assert config == config_data

    def test_load_and_validate_config_file_not_found(self, tmp_path):
        """Test loading non-existent config file."""
        config_file = tmp_path / "nonexistent.json"

        config, errors = load_and_validate_config(config_file)
        assert config is None
        assert len(errors) == 1
        assert "Configuration file not found:" in errors[0]

    def test_load_and_validate_config_invalid_json(self, tmp_path):
        """Test loading config with invalid JSON."""
        config_file = tmp_path / "config.json"
        config_file.write_text("{ invalid json }")

        config, errors = load_and_validate_config(config_file)
        assert config is None
        assert len(errors) == 1
        assert "Invalid JSON in configuration file:" in errors[0]

    def test_load_and_validate_config_validation_failure(self, tmp_path):
        """Test loading config that fails validation."""
        config_data = {
            "confluence": {
                "base_url": "invalid-url",
                "space_key": "DOCS",
            },
            # Missing sync section
        }

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config_data))

        config, errors = load_and_validate_config(config_file)
        assert config is None
        assert len(errors) >= 1
        assert any("Missing required section: sync" in error for error in errors)

    def test_load_and_validate_config_permission_error(self, tmp_path):
        """Test loading config with permission error."""
        config_file = tmp_path / "protected.json"
        config_data = {
            "confluence": {"base_url": "https://test.com", "space_key": "TEST"},
            "sync": {"docs_dir": "docs"},
        }
        config_file.write_text(json.dumps(config_data))
        config_file.chmod(0o000)  # Remove all permissions

        try:
            config, errors = load_and_validate_config(config_file)
            assert config is None
            assert len(errors) == 1
            assert "Permission denied reading configuration file:" in errors[0]
        finally:
            config_file.chmod(0o644)  # Restore permissions for cleanup


class TestDefaultConfiguration:
    """Test default configuration creation."""

    def test_create_default_config_structure(self):
        """Test default config has correct structure."""
        config = create_default_config()

        # Check top-level sections
        assert "confluence" in config
        assert "sync" in config
        assert "ui" in config

        # Check required keys are present
        for section, keys in REQUIRED_CONFIG_KEYS.items():
            assert section in config
            for key in keys:
                assert key in config[section]

        # Check optional keys are present with defaults
        for section, keys in OPTIONAL_CONFIG_KEYS.items():
            assert section in config
            for key in keys:
                assert key in config[section]

    def test_create_default_config_values(self):
        """Test default config has reasonable values."""
        config = create_default_config()

        # Confluence section
        assert config["confluence"]["base_url"] == "https://your-domain.atlassian.net"
        assert config["confluence"]["space_key"] == "YOUR_SPACE_KEY"
        assert config["confluence"]["token_1password_item"] == "ConfluencePAT"
        assert config["confluence"]["retry_max_attempts"] == 3
        assert config["confluence"]["retry_backoff_factor"] == 1.0

        # Sync section
        assert config["sync"]["docs_dir"] == "docs"
        assert config["sync"]["initial_scan"] is True
        assert config["sync"]["debounce_delay"] == 2.0

        # UI section
        assert config["ui"]["refresh_interval"] == 1.0
        assert config["ui"]["log_lines"] == 100


class TestTokenValidation:
    """Test token format validation."""

    def test_validate_token_format_valid_tokens(self):
        """Test validation of valid Confluence PAT formats."""
        valid_tokens = [
            "ATTv1xGDM0MjM5NDc2MDctYWJjZC1lZmdhLWIxMjMtNDU2Nzg5YWJjZGVm",
            "MDM0MjM5NDc2MDQxNDkyMzQ1NjcxMjM0NTY3ODkwMTIzNDU2Nzg5MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5",
            "ABC123def456GHI789jkl012MNO345pqr678STU901vwx234YZA567bcd890EFG123hij456KLM789nop012QRS345tuv678",
            "ATATT3xFfGF0T_valid_token_example_123456789",
        ]

        for token in valid_tokens:
            assert validate_token_format(token), f"Token should be valid: {token}"

    def test_validate_token_format_invalid_tokens(self):
        """Test validation of invalid token formats."""
        invalid_tokens = [
            "",  # Empty
            "   ",  # Whitespace only
            "short",  # Too short
            "token with spaces",  # Contains spaces
            "token\nwith\nnewlines",  # Contains newlines
            "token\twith\ttabs",  # Contains tabs
            None,  # None value
            123,  # Not a string
        ]

        for token in invalid_tokens:
            assert not validate_token_format(token), f"Token should be invalid: {token}"

    def test_validate_token_format_whitespace_stripping(self):
        """Test that whitespace is properly stripped."""
        token_with_whitespace = "  ATTv1xGDM0MjM5NDc2MDctYWJjZC1lZmdhLWIxMjMtNDU2Nzg5YWJjZGVm  \n"
        assert validate_token_format(token_with_whitespace)


class TestUtilityFunctions:
    """Test utility functions for sanitization."""

    def test_sanitize_url_valid_urls(self):
        """Test URL sanitization with valid URLs."""
        test_cases = [
            ("https://example.atlassian.net", "https://example.atlassian.net"),
            ("https://example.atlassian.net/wiki", "https://example.atlassian.net/wiki"),
            ("https://localhost:8080", "https://localhost:8080"),
            ("https://my-domain.atlassian.net/", "https://my-domain.atlassian.net/"),
        ]

        for input_url, expected in test_cases:
            result = sanitize_url(input_url)
            assert (
                result == expected
            ), f"URL {input_url} should sanitize to {expected}, got {result}"

    def test_sanitize_url_invalid_urls(self):
        """Test URL sanitization with invalid URLs."""
        invalid_urls = [
            "not-a-url",
            "http://example.com",  # http not allowed, only https
            "ftp://example.com",
            "file:///etc/passwd",
        ]

        for url in invalid_urls:
            with pytest.raises(ValueError):
                sanitize_url(url)

    def test_sanitize_url_empty_returns_empty(self):
        """Test that empty URL returns empty string."""
        assert sanitize_url("") == ""

    def test_sanitize_space_key_valid_keys(self):
        """Test space key sanitization with valid keys."""
        test_cases = [
            ("DOCS", "DOCS"),
            ("TEST123", "TEST123"),
            ("MY_SPACE", "MY_SPACE"),  # Should be uppercase
        ]

        for input_key, expected in test_cases:
            result = sanitize_space_key(input_key)
            assert result == expected

    def test_sanitize_space_key_invalid_keys(self):
        """Test space key sanitization with invalid keys."""
        invalid_keys = [
            "sp ace",
            "key@with#symbols",
            "lowercase",
            "verylongspacekeythatexceedslimit" * 10,
        ]

        for key in invalid_keys:
            with pytest.raises(ValueError):
                sanitize_space_key(key)

    def test_sanitize_space_key_empty_returns_empty(self):
        """Test that empty space key returns empty string."""
        assert sanitize_space_key("") == ""

    def test_sanitize_file_path_valid_paths(self, tmp_path):
        """Test file path sanitization with valid paths."""
        base_dir = tmp_path / "docs"
        base_dir.mkdir()

        # Create test files
        test_file = base_dir / "test.md"
        test_file.write_text("content")

        nested_dir = base_dir / "nested"
        nested_dir.mkdir()
        nested_file = nested_dir / "nested.md"
        nested_file.write_text("content")

        test_cases = [
            ("test.md", test_file),
            ("nested/nested.md", nested_file),
        ]

        for input_path, expected in test_cases:
            result = sanitize_file_path(input_path, base_dir)
            assert result == expected

    def test_sanitize_file_path_invalid_paths(self, tmp_path):
        """Test file path sanitization with invalid paths."""
        base_dir = tmp_path / "docs"
        base_dir.mkdir()

        invalid_paths = [
            "../../../etc/passwd",  # Path traversal
            "/etc/passwd",  # Absolute path outside base
            "",  # Empty path
        ]

        for path in invalid_paths:
            with pytest.raises(ValueError):
                sanitize_file_path(path, base_dir)


class TestConfigurationConstants:
    """Test configuration constants and structure."""

    def test_required_config_keys_structure(self):
        """Test that required config keys are properly defined."""
        assert isinstance(REQUIRED_CONFIG_KEYS, dict)
        assert "confluence" in REQUIRED_CONFIG_KEYS
        assert "sync" in REQUIRED_CONFIG_KEYS

        # Check specific required keys
        assert "base_url" in REQUIRED_CONFIG_KEYS["confluence"]
        assert "space_key" in REQUIRED_CONFIG_KEYS["confluence"]
        assert "docs_dir" in REQUIRED_CONFIG_KEYS["sync"]

    def test_optional_config_keys_structure(self):
        """Test that optional config keys are properly defined."""
        assert isinstance(OPTIONAL_CONFIG_KEYS, dict)
        assert "confluence" in OPTIONAL_CONFIG_KEYS
        assert "sync" in OPTIONAL_CONFIG_KEYS
        assert "ui" in OPTIONAL_CONFIG_KEYS

    def test_logging_constants(self):
        """Test logging configuration constants."""
        assert isinstance(LOG_FORMAT, str)
        assert isinstance(LOG_DATE_FORMAT, str)
        assert isinstance(LOG_MAX_BYTES, int)
        assert isinstance(LOG_BACKUP_COUNT, int)

        assert LOG_MAX_BYTES > 0
        assert LOG_BACKUP_COUNT > 0
        assert "%(asctime)s" in LOG_FORMAT
        assert "%(levelname)s" in LOG_FORMAT


if __name__ == "__main__":
    pytest.main([__file__])
