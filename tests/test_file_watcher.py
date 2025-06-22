"""Tests for FileMonitor."""

import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.monitor.file_watcher import FileMonitor, MarkdownFileEventHandler
from src.sync.engine import SyncEvent


class TestMarkdownFileEventHandler:
    """Test suite for MarkdownFileEventHandler."""

    @pytest.fixture
    def temp_docs_dir(self):
        """Create a temporary docs directory."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            yield Path(tmp_dir).resolve()  # Ensure resolved path

    @pytest.fixture
    def mock_callback(self):
        """Mock event callback function."""
        return Mock()

    @pytest.fixture
    def handler(self, temp_docs_dir, mock_callback):
        """Create a MarkdownFileEventHandler instance."""
        return MarkdownFileEventHandler(
            docs_dir=temp_docs_dir,
            event_callback=mock_callback,
            debounce_interval=0.1,  # Short interval for testing
        )

    def test_initialization(self, temp_docs_dir, mock_callback):
        """Test handler initialization."""
        handler = MarkdownFileEventHandler(
            docs_dir=temp_docs_dir, event_callback=mock_callback, debounce_interval=0.5
        )

        assert handler.docs_dir == temp_docs_dir.resolve()
        assert handler.event_callback == mock_callback
        assert handler.debounce_interval == 0.5
        assert isinstance(handler._last_event_time, dict)
        assert hasattr(handler._lock, "acquire")  # Check it's a lock-like object

    def test_should_process_valid_md_file(self, handler, temp_docs_dir):
        """Test that valid .md files are processed."""
        md_file = temp_docs_dir / "test.md"
        md_file.touch()

        assert handler._should_process(md_file) is True

    def test_should_process_non_md_file(self, handler, temp_docs_dir):
        """Test that non-.md files are not processed."""
        txt_file = temp_docs_dir / "test.txt"
        txt_file.touch()

        assert handler._should_process(txt_file) is False

    def test_should_process_file_outside_docs_dir(self, handler):
        """Test that files outside docs directory are not processed."""
        # Create a file in a different temp directory
        with tempfile.TemporaryDirectory() as other_dir:
            outside_file = Path(other_dir) / "outside.md"
            outside_file.touch()

            assert handler._should_process(outside_file) is False

    def test_should_process_debounce_logic(self, handler, temp_docs_dir):
        """Test debounce logic prevents rapid successive events."""
        md_file = temp_docs_dir / "test.md"
        md_file.touch()

        # First call should return True
        assert handler._should_process(md_file) is True

        # Immediate second call should return False (debounced)
        assert handler._should_process(md_file) is False

        # Wait for debounce interval and try again
        time.sleep(0.2)  # Longer than debounce_interval of 0.1
        assert handler._should_process(md_file) is True

    def test_should_process_thread_safety(self, handler, temp_docs_dir):
        """Test that debounce logic is thread-safe."""
        md_file = temp_docs_dir / "test.md"
        md_file.touch()

        results = []

        def check_process():
            result = handler._should_process(md_file)
            results.append(result)

        # Create multiple threads checking simultaneously
        threads = [threading.Thread(target=check_process) for _ in range(5)]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # Only one should return True, others should be debounced
        true_count = sum(results)
        assert true_count == 1

    def test_on_created_md_file(self, handler, temp_docs_dir, mock_callback):
        """Test handling of .md file creation."""
        md_file = temp_docs_dir / "new.md"
        md_file.touch()

        event = Mock()
        event.is_directory = False
        event.src_path = str(md_file)

        handler.on_created(event)

        mock_callback.assert_called_once()
        call_args = mock_callback.call_args[0]
        sync_event = call_args[0]
        assert sync_event.event_type == "created"
        assert sync_event.file_path == md_file.resolve()

    def test_on_created_directory(self, handler, mock_callback):
        """Test that directory creation is ignored."""
        event = Mock()
        event.is_directory = True
        event.src_path = "/some/directory"

        handler.on_created(event)

        mock_callback.assert_not_called()

    def test_on_created_non_md_file(self, handler, temp_docs_dir, mock_callback):
        """Test that non-.md file creation is ignored."""
        txt_file = temp_docs_dir / "test.txt"
        txt_file.touch()

        event = Mock()
        event.is_directory = False
        event.src_path = str(txt_file)

        handler.on_created(event)

        mock_callback.assert_not_called()

    def test_on_modified_md_file(self, handler, temp_docs_dir, mock_callback):
        """Test handling of .md file modification."""
        md_file = temp_docs_dir / "existing.md"
        md_file.touch()

        event = Mock()
        event.is_directory = False
        event.src_path = str(md_file)

        handler.on_modified(event)

        mock_callback.assert_called_once()
        call_args = mock_callback.call_args[0]
        sync_event = call_args[0]
        assert sync_event.event_type == "modified"
        assert sync_event.file_path == md_file.resolve()

    def test_on_modified_directory(self, handler, mock_callback):
        """Test that directory modification is ignored."""
        event = Mock()
        event.is_directory = True
        event.src_path = "/some/directory"

        handler.on_modified(event)

        mock_callback.assert_not_called()

    def test_on_deleted_md_file(self, handler, temp_docs_dir, mock_callback):
        """Test handling of .md file deletion."""
        md_file = temp_docs_dir / "deleted.md"

        event = Mock()
        event.is_directory = False
        event.src_path = str(md_file)

        handler.on_deleted(event)

        mock_callback.assert_called_once()
        call_args = mock_callback.call_args[0]
        sync_event = call_args[0]
        assert sync_event.event_type == "deleted"
        assert sync_event.file_path == md_file.resolve()

    def test_on_deleted_file_outside_docs_dir(self, handler, mock_callback):
        """Test that deletion outside docs directory is ignored."""
        # Use a path that definitely won't be under temp docs dir
        outside_file = Path("/tmp/outside.md")

        event = Mock()
        event.is_directory = False
        event.src_path = str(outside_file)

        handler.on_deleted(event)

        mock_callback.assert_not_called()

    def test_on_deleted_directory(self, handler, mock_callback):
        """Test that directory deletion is ignored."""
        event = Mock()
        event.is_directory = True
        event.src_path = "/some/directory"

        handler.on_deleted(event)

        mock_callback.assert_not_called()


class TestFileMonitor:
    """Test suite for FileMonitor."""

    @pytest.fixture
    def temp_docs_dir(self):
        """Create a temporary docs directory."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            yield Path(tmp_dir).resolve()

    @pytest.fixture
    def mock_sync_engine(self):
        """Mock sync engine."""
        mock_engine = Mock()
        mock_engine.enqueue_event = Mock()
        mock_engine.initial_scan = Mock()
        return mock_engine

    @pytest.fixture
    def file_monitor(self, temp_docs_dir, mock_sync_engine):
        """Create a FileMonitor instance."""
        return FileMonitor(
            docs_dir=temp_docs_dir, sync_engine=mock_sync_engine, debounce_interval=0.1
        )

    def test_initialization(self, temp_docs_dir, mock_sync_engine):
        """Test FileMonitor initialization."""
        monitor = FileMonitor(
            docs_dir=temp_docs_dir, sync_engine=mock_sync_engine, debounce_interval=0.5
        )

        assert monitor.docs_dir == temp_docs_dir.resolve()
        assert monitor.sync_engine == mock_sync_engine
        assert monitor.debounce_interval == 0.5
        assert monitor._thread is None
        assert monitor._stop_event is not None

    @patch("src.monitor.file_watcher.Observer")
    def test_start_monitor(self, mock_observer_class, file_monitor, mock_sync_engine):
        """Test starting the file monitor."""
        # Set up the mock to return itself for method chaining
        mock_observer = Mock()
        mock_observer_class.return_value = mock_observer
        file_monitor._observer = mock_observer  # Set the observer directly

        file_monitor.start()

        # Verify observer was configured and started
        mock_observer.schedule.assert_called_once()
        mock_observer.start.assert_called_once()

        # Verify initial scan was called
        mock_sync_engine.initial_scan.assert_called_once()

        # Verify thread was started
        assert file_monitor._thread is not None
        assert file_monitor._thread.daemon is True

        # Clean up
        file_monitor.stop()

    @patch("src.monitor.file_watcher.Observer")
    def test_stop_monitor(self, mock_observer_class, file_monitor):
        """Test stopping the file monitor."""
        # Set up the mock
        mock_observer = Mock()
        mock_observer_class.return_value = mock_observer
        file_monitor._observer = mock_observer

        # Start the monitor first
        file_monitor.start()

        # Stop the monitor
        file_monitor.stop()

        # Verify observer was stopped
        mock_observer.stop.assert_called_once()
        mock_observer.join.assert_called_once()

    @patch("src.monitor.file_watcher.Observer")
    def test_run_loop(self, mock_observer_class, file_monitor):
        """Test the internal run loop."""
        mock_observer = Mock()
        mock_observer_class.return_value = mock_observer
        file_monitor._observer = mock_observer

        # Start the monitor
        file_monitor.start()

        # Let it run briefly
        time.sleep(0.2)

        # Stop and verify no exceptions were raised
        file_monitor.stop()

    @patch("src.monitor.file_watcher.Observer")
    def test_run_loop_exception_handling(self, mock_observer_class, file_monitor):
        """Test that exceptions in run loop are handled gracefully."""
        mock_observer = Mock()
        mock_observer_class.return_value = mock_observer
        file_monitor._observer = mock_observer

        # Mock the _run method to raise an exception
        def mock_run():
            raise Exception("Test exception")

        file_monitor._run = mock_run

        # Start monitor - should not raise exception
        file_monitor.start()

        # Brief pause then stop
        time.sleep(0.1)
        file_monitor.stop()

    def test_event_callback_integration(self, temp_docs_dir, mock_sync_engine):
        """Test that events are properly passed to sync engine."""
        monitor = FileMonitor(temp_docs_dir, mock_sync_engine)

        # Create the event handler
        handler = MarkdownFileEventHandler(
            docs_dir=temp_docs_dir,
            event_callback=monitor.sync_engine.enqueue_event,
            debounce_interval=0.1,
        )

        # Create a test file and simulate event
        md_file = temp_docs_dir / "test.md"
        md_file.touch()

        event = Mock()
        event.is_directory = False
        event.src_path = str(md_file)

        handler.on_created(event)

        # Verify sync engine received the event
        mock_sync_engine.enqueue_event.assert_called_once()
        call_args = mock_sync_engine.enqueue_event.call_args[0]
        sync_event = call_args[0]
        assert isinstance(sync_event, SyncEvent)
        assert sync_event.event_type == "created"

    @patch("src.monitor.file_watcher.Observer")
    def test_multiple_start_stop_cycles(self, mock_observer_class, file_monitor):
        """Test multiple start/stop cycles work correctly."""
        # Create separate mock observers for each cycle
        mock_observers = [Mock() for _ in range(3)]
        mock_observer_class.side_effect = mock_observers

        # Multiple start/stop cycles
        for _ in range(3):
            # Create new monitor for each cycle to avoid thread reuse issues
            new_monitor = FileMonitor(
                file_monitor.docs_dir, file_monitor.sync_engine, file_monitor.debounce_interval
            )
            new_monitor.start()
            time.sleep(0.1)
            new_monitor.stop()
            time.sleep(0.1)

        # Verify observer was created for each cycle
        assert mock_observer_class.call_count == 3

    @patch("src.monitor.file_watcher.Observer")
    def test_thread_cleanup_on_stop(self, mock_observer_class, file_monitor):
        """Test that threads are properly cleaned up on stop."""
        mock_observer = Mock()
        mock_observer_class.return_value = mock_observer
        file_monitor._observer = mock_observer

        file_monitor.start()
        thread = file_monitor._thread

        file_monitor.stop()

        # Thread should be joined and stopped
        assert not thread.is_alive()

    @pytest.mark.integration
    @patch("src.monitor.file_watcher.Observer")
    def test_real_file_events(self, mock_observer_class, temp_docs_dir, mock_sync_engine):
        """Test with real file system events."""
        mock_observer = Mock()
        mock_observer_class.return_value = mock_observer

        monitor = FileMonitor(temp_docs_dir, mock_sync_engine, debounce_interval=0.05)

        # Create handler for testing
        handler = monitor._event_handler

        # Create, modify, and delete a markdown file
        md_file = temp_docs_dir / "test.md"

        # Test creation
        md_file.write_text("# Test")
        create_event = Mock()
        create_event.is_directory = False
        create_event.src_path = str(md_file)
        handler.on_created(create_event)

        # Test modification
        time.sleep(0.1)  # Wait for debounce
        modify_event = Mock()
        modify_event.is_directory = False
        modify_event.src_path = str(md_file)
        handler.on_modified(modify_event)

        # Test deletion
        delete_event = Mock()
        delete_event.is_directory = False
        delete_event.src_path = str(md_file)
        handler.on_deleted(delete_event)

        # Verify all events were processed
        assert mock_sync_engine.enqueue_event.call_count == 3

        # Verify event types
        event_types = [
            call[0][0].event_type for call in mock_sync_engine.enqueue_event.call_args_list
        ]
        assert "created" in event_types
        assert "modified" in event_types
        assert "deleted" in event_types

    def test_debounce_prevents_spam(self, temp_docs_dir, mock_sync_engine):
        """Test that debouncing prevents event spam."""
        handler = MarkdownFileEventHandler(
            docs_dir=temp_docs_dir,
            event_callback=mock_sync_engine.enqueue_event,
            debounce_interval=0.1,
        )

        md_file = temp_docs_dir / "spam.md"
        md_file.touch()

        event = Mock()
        event.is_directory = False
        event.src_path = str(md_file)

        # Send multiple rapid events
        for _ in range(10):
            handler.on_modified(event)

        # Only one event should have been processed
        assert mock_sync_engine.enqueue_event.call_count == 1

    @pytest.mark.unit
    def test_docs_dir_resolution(self, temp_docs_dir, mock_sync_engine):
        """Test that docs directory path is properly resolved."""
        # Test with the actual temp directory
        monitor = FileMonitor(temp_docs_dir, mock_sync_engine)
        assert monitor.docs_dir == temp_docs_dir.resolve()

    @pytest.mark.unit
    def test_event_handler_configuration(self, temp_docs_dir, mock_sync_engine):
        """Test that event handler is properly configured."""
        monitor = FileMonitor(temp_docs_dir, mock_sync_engine, debounce_interval=0.5)

        handler = monitor._event_handler
        assert isinstance(handler, MarkdownFileEventHandler)
        assert handler.docs_dir == temp_docs_dir.resolve()
        assert handler.event_callback == mock_sync_engine.enqueue_event
        assert handler.debounce_interval == 0.5
