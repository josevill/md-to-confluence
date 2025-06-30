"""Tests for UI components."""

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.sync.engine import SyncEngine
from src.sync.state import SyncState
from src.ui.app import LogWidget, MDToConfluenceApp, load_config


class TestLogWidget:
    """Test suite for LogWidget."""

    def test_log_widget_initialization(self):
        """Test LogWidget initialization."""
        widget = LogWidget(max_lines=500)

        assert widget.max_lines == 500
        assert widget.session_start_time is None
        assert widget.last_file_size == 0

    def test_add_log_message(self):
        """Test adding log messages to widget."""
        widget = LogWidget()

        widget.add_log("Test log message")

        # Check that message was added (write method called)
        # Note: Can't easily verify content without rendering

    def test_is_current_session_no_session_time(self):
        """Test session checking when no session time is set."""
        widget = LogWidget()
        widget.session_start_time = None

        result = widget._is_current_session("2024-01-01 10:00:00 - INFO - Test message")

        assert result is True

    def test_is_current_session_valid_format(self):
        """Test session checking with valid log format."""
        widget = LogWidget()

        # Set session start time
        from datetime import datetime

        widget.session_start_time = datetime(2024, 1, 1, 9, 0, 0)

        # Test message after session start
        result = widget._is_current_session("2024-01-01 10:00:00 - INFO - Test message")
        assert result is True

        # Test message before session start
        result = widget._is_current_session("2024-01-01 08:00:00 - INFO - Old message")
        assert result is False

    def test_is_current_session_invalid_format(self):
        """Test session checking with invalid log format."""
        widget = LogWidget()

        from datetime import datetime

        widget.session_start_time = datetime(2024, 1, 1, 9, 0, 0)

        # Test invalid format - should return True
        result = widget._is_current_session("Invalid log format")
        assert result is True

    @pytest.mark.asyncio
    async def test_refresh_logs_no_file(self):
        """Test refreshing logs when log file doesn't exist."""
        widget = LogWidget()

        # Should not raise exception
        await widget.refresh_logs()

    @pytest.mark.asyncio
    async def test_refresh_logs_with_file(self):
        """Test refreshing logs with existing log file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "md_to_confluence.log"

            # Create log file with content
            log_content = "2024-01-01 10:00:00 - INFO - Test message\n"
            log_file.write_text(log_content)

            widget = LogWidget()

            # Mock the log file path
            with patch("src.ui.app.Path") as mock_path:
                mock_path.return_value = log_file
                mock_path.side_effect = lambda x: (
                    Path(x) if x != "logs/md_to_confluence.log" else log_file
                )

                # Mock write method to track calls
                widget.write = Mock()

                await widget.refresh_logs()

                # Should have called write with log content
                widget.write.assert_called()

    @pytest.mark.asyncio
    async def test_refresh_logs_file_truncated(self):
        """Test refreshing logs when file was truncated."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "md_to_confluence.log"

            widget = LogWidget()
            widget.last_file_size = 1000  # Larger than actual file

            # Create smaller log file
            log_content = "2024-01-01 10:00:00 - INFO - New content\n"
            log_file.write_text(log_content)

            with patch("src.ui.app.Path") as mock_path:
                mock_path.return_value = log_file
                mock_path.side_effect = lambda x: (
                    Path(x) if x != "logs/md_to_confluence.log" else log_file
                )

                widget.clear = Mock()
                widget.write = Mock()

                await widget.refresh_logs()

                # Should have cleared and reloaded
                widget.clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_mount_with_log_file(self):
        """Test widget mounting with existing log file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "md_to_confluence.log"
            log_content = "2024-01-01 10:00:00 - INFO - Initial message\n"
            log_file.write_text(log_content)

            widget = LogWidget()

            with patch("src.ui.app.Path") as mock_path:
                mock_path.return_value = log_file
                mock_path.side_effect = lambda x: (
                    Path(x) if x != "logs/md_to_confluence.log" else log_file
                )

                widget.write = Mock()

                await widget.on_mount()

                # Should have loaded initial content
                assert widget.last_file_size > 0

    def test_find_session_start_no_file(self):
        """Test finding session start when no log file exists."""
        widget = LogWidget()

        with patch("src.ui.app.Path") as mock_path:
            mock_path.return_value.exists.return_value = False

            widget._find_session_start()

            assert widget.session_start_time is None

    def test_find_session_start_with_session_marker(self):
        """Test finding session start with session marker in log."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "md_to_confluence.log"
            log_content = (
                "2024-01-01 10:00:00 - INFO - New session started at 2024-01-01 10:00:00\n"
            )
            log_file.write_text(log_content)

            widget = LogWidget()

            with patch("src.ui.app.Path") as mock_path:
                mock_path.return_value = log_file
                mock_path.side_effect = lambda x: (
                    Path(x) if x != "logs/md_to_confluence.log" else log_file
                )

                widget._find_session_start()

                assert widget.session_start_time is not None


class TestMDToConfluenceApp:
    """Test suite for MDToConfluenceApp."""

    @pytest.fixture
    def mock_sync_engine(self):
        """Mock SyncEngine for testing."""
        mock_engine = Mock(spec=SyncEngine)
        mock_state = Mock(spec=SyncState)
        mock_state.get_all_tracked_files.return_value = ["/test/file1.md", "/test/file2.md"]
        mock_engine.state = mock_state
        return mock_engine

    @pytest.fixture
    def app(self, mock_sync_engine):
        """Create app instance for testing."""
        return MDToConfluenceApp(sync_engine=mock_sync_engine)

    def test_app_initialization(self, app, mock_sync_engine):
        """Test app initialization."""
        assert app.sync_engine is mock_sync_engine
        assert app.state is mock_sync_engine.state
        assert app.log_widget is not None
        assert app.data_table is not None

    def test_app_bindings(self, app):
        """Test app key bindings."""
        bindings = app.BINDINGS

        # Extract binding keys
        binding_keys = [binding[0] for binding in bindings]

        assert "q" in binding_keys
        assert "ctrl+c" in binding_keys

    def test_compose_method(self, app):
        """Test app composition."""
        # This is a basic test - compose returns a generator
        compose_result = app.compose()

        # Should be a generator/iterator
        assert hasattr(compose_result, "__iter__")

    @pytest.mark.asyncio
    async def test_on_mount(self, app):
        """Test app mounting behavior."""
        # Mock the data table and set interval methods
        app.data_table.add_columns = Mock()
        app.set_interval = Mock()

        with patch.object(app, "refresh_file_statuses", new_callable=AsyncMock):
            await app.on_mount()

            # Should add columns to data table
            app.data_table.add_columns.assert_called_once_with("File", "Status")

            # Should set up intervals (file status, log refresh, conflict summary)
            assert app.set_interval.call_count == 3

    @pytest.mark.asyncio
    async def test_refresh_file_statuses(self, app):
        """Test refreshing file statuses."""
        app.data_table.clear = Mock()
        app.data_table.add_row = Mock()

        await app.refresh_file_statuses()

        # Should clear table and add rows
        app.data_table.clear.assert_called_once()

        # Should add rows for tracked files
        expected_calls = app.sync_engine.state.get_all_tracked_files.return_value
        assert app.data_table.add_row.call_count == len(expected_calls)

    def test_action_clear_logs(self, app):
        """Test clearing logs action."""
        # Mock the log widget
        app.log_widget.clear = Mock()

        app.action_clear_logs()

        app.log_widget.clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_conflict_summary_no_conflicts(self, app):
        """Test refresh conflict summary when no conflicts exist."""
        # Mock get_conflict_summary to return empty dict
        app.sync_engine.get_conflict_summary.return_value = {}

        # Mock widget visibility state
        app.conflict_widget_visible = False
        app._hide_conflict_widget = AsyncMock()
        app._show_conflict_widget = AsyncMock()

        await app.refresh_conflict_summary()

        # Should not show widget when no conflicts
        app._show_conflict_widget.assert_not_called()
        app._hide_conflict_widget.assert_not_called()

    @pytest.mark.asyncio
    async def test_refresh_conflict_summary_with_conflicts_show_widget(self, app):
        """Test refresh conflict summary when conflicts exist and widget is hidden."""
        # Mock get_conflict_summary to return conflicts
        app.sync_engine.get_conflict_summary.return_value = {"title_conflict": 2}

        # Mock widget state - not visible
        app.conflict_widget_visible = False
        app._show_conflict_widget = AsyncMock()
        app.conflict_widget.update_summary = Mock()

        await app.refresh_conflict_summary()

        # Should show widget and update summary
        app._show_conflict_widget.assert_called_once()
        app.conflict_widget.update_summary.assert_called_once_with({"title_conflict": 2})

    @pytest.mark.asyncio
    async def test_refresh_conflict_summary_conflicts_resolved_hide_widget(self, app):
        """Test refresh conflict summary when conflicts are resolved and widget is visible."""
        # Mock get_conflict_summary to return no conflicts
        app.sync_engine.get_conflict_summary.return_value = {}

        # Mock widget state - visible
        app.conflict_widget_visible = True
        app._hide_conflict_widget = AsyncMock()
        app._show_conflict_widget = AsyncMock()

        await app.refresh_conflict_summary()

        # Should hide widget when conflicts are resolved
        app._hide_conflict_widget.assert_called_once()
        app._show_conflict_widget.assert_not_called()

    @pytest.mark.asyncio
    async def test_refresh_conflict_summary_update_existing_widget(self, app):
        """Test refresh conflict summary when conflicts exist and widget is already visible."""
        # Mock get_conflict_summary to return conflicts
        app.sync_engine.get_conflict_summary.return_value = {"title_conflict": 1}

        # Mock widget state - already visible
        app.conflict_widget_visible = True
        app._show_conflict_widget = AsyncMock()
        app._hide_conflict_widget = AsyncMock()
        app.conflict_widget.update_summary = Mock()

        await app.refresh_conflict_summary()

        # Should only update the existing widget
        app._show_conflict_widget.assert_not_called()
        app._hide_conflict_widget.assert_not_called()
        app.conflict_widget.update_summary.assert_called_once_with({"title_conflict": 1})

    @pytest.mark.asyncio
    async def test_show_conflict_widget(self, app):
        """Test showing the conflict widget."""
        # Mock the container structure
        mock_vertical = Mock()
        mock_vertical.mount = AsyncMock()
        app.main_container = Mock()
        app.main_container.children = [mock_vertical]

        app.conflict_widget_visible = False

        await app._show_conflict_widget()

        # Should mount widget and set visibility flag
        mock_vertical.mount.assert_called_once_with(app.conflict_widget, before=app.data_table)
        assert app.conflict_widget_visible is True

    @pytest.mark.asyncio
    async def test_hide_conflict_widget(self, app):
        """Test hiding the conflict widget."""
        app.conflict_widget.remove = AsyncMock()
        app.conflict_widget_visible = True

        await app._hide_conflict_widget()

        # Should remove widget and clear visibility flag
        app.conflict_widget.remove.assert_called_once()
        assert app.conflict_widget_visible is False

    @pytest.mark.asyncio
    async def test_show_conflict_widget_no_container(self, app):
        """Test showing conflict widget when main container is not set."""
        app.main_container = None
        app.conflict_widget_visible = False

        await app._show_conflict_widget()

        # Should not change visibility when container is not available
        assert app.conflict_widget_visible is False

    @pytest.mark.asyncio
    async def test_hide_conflict_widget_already_hidden(self, app):
        """Test hiding conflict widget when it's already hidden."""
        app.conflict_widget.remove = AsyncMock()
        app.conflict_widget_visible = False

        await app._hide_conflict_widget()

        # Should not try to remove widget if not visible
        app.conflict_widget.remove.assert_not_called()
        assert app.conflict_widget_visible is False

    @pytest.mark.asyncio
    async def test_app_with_pilot(self, app):
        """Test app interaction using Textual pilot."""
        async with app.run_test() as pilot:
            # Test basic functionality
            assert pilot.app is app

            # Test quit action
            await pilot.press("q")
            # App should be in process of exiting


class TestLoadConfig:
    """Test suite for load_config function."""

    def test_load_config_success(self):
        """Test successful config loading."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "config.json"
            config_data = {
                "confluence": {"base_url": "https://test.atlassian.net", "space_key": "TEST"},
                "docs_dir": "docs",
                "sync": {"debounce_interval": 2.0},
            }

            config_file.write_text(json.dumps(config_data))

            result = load_config(config_file)

            assert result == config_data

    def test_load_config_file_not_found(self):
        """Test config loading when file doesn't exist."""
        non_existent_file = Path("/non/existent/config.json")

        with pytest.raises(FileNotFoundError):
            load_config(non_existent_file)

    def test_load_config_invalid_json(self):
        """Test config loading with invalid JSON."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "config.json"
            config_file.write_text("{ invalid json ")

            with pytest.raises(json.JSONDecodeError):
                load_config(config_file)


class TestUIIntegration:
    """Integration tests for UI components."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_full_app_workflow(self):
        """Test complete app workflow."""
        # Create mock sync engine with realistic behavior
        mock_engine = Mock(spec=SyncEngine)
        mock_state = Mock(spec=SyncState)

        # Set up realistic file tracking
        tracked_files = ["/docs/getting-started.md", "/docs/advanced/configuration.md"]
        mock_state.get_all_tracked_files.return_value = tracked_files
        mock_engine.state = mock_state

        app = MDToConfluenceApp(sync_engine=mock_engine)

        async with app.run_test() as pilot:
            # Test initial state
            assert pilot.app.sync_engine is mock_engine

            # Test clear logs action
            await pilot.press("ctrl+c")

            # Test quit action
            await pilot.press("q")

    @pytest.mark.integration
    def test_log_widget_with_real_content(self):
        """Test LogWidget with realistic log content."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "md_to_confluence.log"

            # Create realistic log content
            log_content = """2024-01-01 10:00:00 - INFO - MD-to-Confluence started
2024-01-01 10:00:01 - INFO - New session started at 2024-01-01 10:00:00
2024-01-01 10:00:02 - DEBUG - Scanning docs directory
2024-01-01 10:00:03 - INFO - Found 5 markdown files
2024-01-01 10:00:04 - INFO - Processing file: getting-started.md
2024-01-01 10:00:05 - INFO - Created page with ID: 123456
"""
            log_file.write_text(log_content)

            widget = LogWidget()

            with patch("src.ui.app.Path") as mock_path:
                mock_path.return_value = log_file
                mock_path.side_effect = lambda x: (
                    Path(x) if x != "logs/md_to_confluence.log" else log_file
                )

                # Find session start
                widget._find_session_start()

                # Should have found session start time
                assert widget.session_start_time is not None

                # Test session filtering
                session_lines = [
                    "2024-01-01 10:00:02 - DEBUG - Scanning docs directory",
                    "2024-01-01 09:59:59 - INFO - Old message",  # Before session
                ]

                assert widget._is_current_session(session_lines[0]) is True
                assert widget._is_current_session(session_lines[1]) is False

    @pytest.mark.asyncio
    async def test_app_error_handling(self):
        """Test app error handling scenarios."""
        # Create mock engine that raises exceptions
        mock_engine = Mock(spec=SyncEngine)
        mock_state = Mock(spec=SyncState)
        mock_state.get_all_tracked_files.side_effect = Exception("State error")
        mock_engine.state = mock_state

        app = MDToConfluenceApp(sync_engine=mock_engine)

        # Should handle errors gracefully
        try:
            await app.refresh_file_statuses()
        except Exception:
            pytest.fail("App should handle state errors gracefully")

    def test_css_styling(self):
        """Test CSS styling is properly defined."""
        app = MDToConfluenceApp(sync_engine=Mock())

        # Should have CSS defined
        assert hasattr(app, "CSS")
        assert isinstance(app.CSS, str)
        assert "LogWidget" in app.CSS
        assert "DataTable" in app.CSS
