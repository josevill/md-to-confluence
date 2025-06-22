"""Tests for SyncEngine."""

import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

from src.confluence.client import ConfluenceClient
from src.confluence.converter import MarkdownConverter
from src.sync.engine import SyncEngine, SyncEvent


class TestSyncEvent:
    """Test suite for SyncEvent."""

    def test_sync_event_creation(self):
        """Test SyncEvent creation and attributes."""
        file_path = Path("/test/file.md")
        event = SyncEvent("created", file_path)

        assert event.event_type == "created"
        assert event.file_path == file_path.resolve()
        assert isinstance(event.timestamp, float)
        assert event.timestamp > 0

    def test_sync_event_repr(self):
        """Test SyncEvent string representation."""
        file_path = Path("/test/file.md")
        event = SyncEvent("modified", file_path)

        repr_str = repr(event)
        assert "SyncEvent" in repr_str
        assert "modified" in repr_str
        assert str(file_path.resolve()) in repr_str


class TestSyncEngine:
    """Test suite for SyncEngine."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)

    @pytest.fixture
    def mock_confluence_client(self):
        """Mock ConfluenceClient."""
        mock_client = Mock(spec=ConfluenceClient)
        mock_client.create_page.return_value = {"id": "123", "title": "Test Page"}
        mock_client.update_page.return_value = {"id": "123", "title": "Updated Page"}
        mock_client.delete_page.return_value = True
        mock_client.upload_attachment.return_value = {"id": "att123"}
        return mock_client

    @pytest.fixture
    def mock_converter(self):
        """Mock MarkdownConverter."""
        mock_converter = Mock(spec=MarkdownConverter)
        mock_converter.convert_with_images.return_value = ("<p>Converted content</p>", {})
        mock_converter.finalize_content_with_images.return_value = "<p>Final content</p>"
        return mock_converter

    @pytest.fixture
    def sync_engine(self, temp_dir, mock_confluence_client, mock_converter):
        """Create a SyncEngine instance for testing."""
        docs_dir = temp_dir / "docs"
        docs_dir.mkdir()
        state_file = temp_dir / "state.json"

        # Clear any existing instance
        SyncEngine._instance = None

        engine = SyncEngine.get_instance(
            docs_dir=docs_dir,
            state_file=state_file,
            confluence_client=mock_confluence_client,
            converter=mock_converter,
            debounce_interval=0.1,
        )

        yield engine

        # Clean up
        engine.stop()
        SyncEngine._instance = None

    def test_singleton_pattern(self, temp_dir, mock_confluence_client, mock_converter):
        """Test that SyncEngine follows singleton pattern."""
        docs_dir = temp_dir / "docs"
        docs_dir.mkdir()
        state_file = temp_dir / "state.json"

        # Clear any existing instance
        SyncEngine._instance = None

        engine1 = SyncEngine.get_instance(
            docs_dir=docs_dir,
            state_file=state_file,
            confluence_client=mock_confluence_client,
            converter=mock_converter,
        )

        engine2 = SyncEngine.get_instance()

        assert engine1 is engine2

        engine1.stop()
        SyncEngine._instance = None

    def test_singleton_thread_safety(self, temp_dir, mock_confluence_client, mock_converter):
        """Test singleton pattern is thread-safe."""
        docs_dir = temp_dir / "docs"
        docs_dir.mkdir()
        state_file = temp_dir / "state.json"

        # Clear any existing instance
        SyncEngine._instance = None
        instances = []

        def create_engine():
            try:
                engine = SyncEngine.get_instance(
                    docs_dir=docs_dir,
                    state_file=state_file,
                    confluence_client=mock_confluence_client,
                    converter=mock_converter,
                )
                instances.append(engine)
            except Exception:
                pass  # Ignore errors from multiple threads

        # Create multiple threads
        threads = [threading.Thread(target=create_engine) for _ in range(5)]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # Should have at least one instance created, and all should be the same
        assert len(instances) >= 1
        assert len(set(instances)) == 1

        instances[0].stop()
        SyncEngine._instance = None

    def test_direct_instantiation_forbidden(self, temp_dir, mock_confluence_client, mock_converter):
        """Test that direct instantiation raises an exception when instance exists."""
        docs_dir = temp_dir / "docs"
        docs_dir.mkdir()
        state_file = temp_dir / "state.json"

        # Clear any existing instance
        SyncEngine._instance = None

        # Create first instance through get_instance
        engine = SyncEngine.get_instance(
            docs_dir=docs_dir,
            state_file=state_file,
            confluence_client=mock_confluence_client,
            converter=mock_converter,
        )

        # Try direct instantiation - should raise exception
        with pytest.raises(Exception, match="SyncEngine is a singleton"):
            SyncEngine(
                docs_dir=docs_dir,
                state_file=state_file,
                confluence_client=mock_confluence_client,
                converter=mock_converter,
            )

        engine.stop()
        SyncEngine._instance = None

    def test_enqueue_event(self, sync_engine):
        """Test event enqueueing."""
        test_file = sync_engine.docs_dir / "test.md"
        test_file.write_text("# Test")

        event = SyncEvent("created", test_file)
        sync_engine.enqueue_event(event)

        # Event should be in the queue
        assert not sync_engine.event_queue.empty()

    def test_get_relative_path_valid(self, sync_engine):
        """Test getting relative path for valid file."""
        test_file = sync_engine.docs_dir / "subfolder" / "test.md"
        test_file.parent.mkdir()
        test_file.write_text("# Test")

        rel_path = sync_engine._get_relative_path(test_file)

        assert rel_path == Path("subfolder/test.md")

    def test_get_relative_path_invalid(self, sync_engine):
        """Test getting relative path for file outside docs_dir."""
        outside_file = sync_engine.docs_dir.parent / "outside.md"
        outside_file.write_text("# Test")

        rel_path = sync_engine._get_relative_path(outside_file)

        assert rel_path is None

    def test_get_parent_page_id_top_level(self, sync_engine):
        """Test getting parent page ID for top-level file."""
        rel_path = Path("test.md")

        parent_id = sync_engine._get_parent_page_id(rel_path)

        assert parent_id is None

    def test_get_parent_page_id_nested(self, sync_engine):
        """Test getting parent page ID for nested file."""
        # Set up a parent directory mapping
        parent_dir = sync_engine.docs_dir / "subfolder"
        parent_dir.mkdir()
        sync_engine.state.add_mapping(str(parent_dir), "parent123", time.time())

        rel_path = Path("subfolder/test.md")

        parent_id = sync_engine._get_parent_page_id(rel_path)

        assert parent_id == "parent123"

    def test_process_event_created_new_file(self, sync_engine):
        """Test processing created event for new file."""
        test_file = sync_engine.docs_dir / "new_file.md"
        test_file.write_text("# New File")

        event = SyncEvent("created", test_file)
        sync_engine._process_event(event)

        # Verify Confluence operations were called
        sync_engine.confluence.create_page.assert_called_once()
        sync_engine.converter.convert_with_images.assert_called_once()

    def test_process_event_modified_existing_file(self, sync_engine):
        """Test processing modified event for existing file."""
        test_file = sync_engine.docs_dir / "existing_file.md"
        test_file.write_text("# Existing File")

        # Set up existing mapping
        sync_engine.state.add_mapping(str(test_file), "page123", time.time())

        event = SyncEvent("modified", test_file)
        sync_engine._process_event(event)

        # Verify update was called
        sync_engine.confluence.update_page.assert_called()
        sync_engine.converter.convert_with_images.assert_called_once()

    def test_process_event_deleted_file(self, sync_engine):
        """Test processing deleted event."""
        test_file = sync_engine.docs_dir / "deleted_file.md"

        # Set up existing mapping
        sync_engine.state.add_mapping(str(test_file), "page123", time.time())

        event = SyncEvent("deleted", test_file)
        sync_engine._process_event(event)

        # Verify delete was called
        sync_engine.confluence.delete_page.assert_called_once_with("page123")

    def test_process_event_deleted_file_no_mapping(self, sync_engine):
        """Test processing deleted event for file with no mapping."""
        test_file = sync_engine.docs_dir / "unmapped_file.md"

        event = SyncEvent("deleted", test_file)
        sync_engine._process_event(event)

        # Delete should not be called
        sync_engine.confluence.delete_page.assert_not_called()

    def test_process_event_file_not_exists(self, sync_engine):
        """Test processing event for non-existent file."""
        test_file = sync_engine.docs_dir / "nonexistent.md"

        event = SyncEvent("created", test_file)
        sync_engine._process_event(event)

        # Should not call create_page for non-existent file
        sync_engine.confluence.create_page.assert_not_called()

    def test_process_event_with_images(self, sync_engine):
        """Test processing event with local images."""
        test_file = sync_engine.docs_dir / "with_images.md"
        test_file.write_text("# File with images")

        # Mock converter to return local images
        local_images = {"image1.png": {"path": Path("/test/image1.png"), "filename": "image1.png"}}
        sync_engine.converter.convert_with_images.return_value = (
            "<p>Content with placeholders</p>",
            local_images,
        )

        event = SyncEvent("created", test_file)
        sync_engine._process_event(event)

        # Verify image upload was called
        sync_engine.confluence.upload_attachment.assert_called()
        sync_engine.converter.finalize_content_with_images.assert_called()

    def test_upload_images_success(self, sync_engine):
        """Test successful image upload."""
        page_id = "page123"
        local_images = {
            "placeholder1": {"path": Path("/test/image1.png"), "filename": "image1.png"},
            "placeholder2": {"path": Path("/test/image2.jpg"), "filename": "image2.jpg"},
        }

        result = sync_engine._upload_images(page_id, local_images)

        assert len(result) == 2
        assert result["image1.png"] is True
        assert result["image2.jpg"] is True
        assert sync_engine.confluence.upload_attachment.call_count == 2

    def test_upload_images_failure(self, sync_engine):
        """Test image upload with failures."""
        page_id = "page123"
        local_images = {
            "placeholder1": {"path": Path("/test/image1.png"), "filename": "image1.png"}
        }

        # Mock upload failure
        sync_engine.confluence.upload_attachment.side_effect = Exception("Upload failed")

        result = sync_engine._upload_images(page_id, local_images)

        assert result["image1.png"] is False

    def test_initial_scan(self, sync_engine):
        """Test initial scan for untracked files."""
        # Create test files
        file1 = sync_engine.docs_dir / "file1.md"
        file2 = sync_engine.docs_dir / "subfolder" / "file2.md"
        file2.parent.mkdir()
        file1.write_text("# File 1")
        file2.write_text("# File 2")

        # Add one file to state (already tracked)
        sync_engine.state.add_mapping(str(file1), "page123", time.time())

        sync_engine.initial_scan()

        # Should enqueue event only for untracked file
        # Let the worker process the queue briefly
        time.sleep(0.2)

        # Verify that create_page was called (for untracked file)
        sync_engine.confluence.create_page.assert_called()

    def test_debouncing_logic(self, sync_engine):
        """Test event debouncing in worker thread."""
        test_file = sync_engine.docs_dir / "debounce_test.md"
        test_file.write_text("# Test")

        # Enqueue multiple events quickly
        for _ in range(3):
            event = SyncEvent("modified", test_file)
            sync_engine.enqueue_event(event)
            time.sleep(0.01)  # Small delay between events

        # Wait for debounce interval + processing time
        time.sleep(sync_engine.debounce_interval + 0.2)

        # Should have processed events (debounced)
        assert sync_engine.converter.convert_with_images.call_count >= 1

    def test_worker_thread_error_handling(self, sync_engine):
        """Test worker thread error handling."""
        test_file = sync_engine.docs_dir / "error_test.md"
        test_file.write_text("# Test")

        # Mock an error in processing
        sync_engine.confluence.create_page.side_effect = Exception("Processing error")

        event = SyncEvent("created", test_file)
        sync_engine.enqueue_event(event)

        # Wait for processing
        time.sleep(0.2)

        # Worker thread should continue running despite error
        assert sync_engine._worker_thread.is_alive()

    def test_process_event_outside_docs_dir(self, sync_engine):
        """Test processing event for file outside docs directory."""
        outside_file = sync_engine.docs_dir.parent / "outside.md"
        outside_file.write_text("# Outside")

        event = SyncEvent("created", outside_file)
        sync_engine._process_event(event)

        # Should not process files outside docs_dir
        sync_engine.confluence.create_page.assert_not_called()

    def test_stop_engine(self, sync_engine):
        """Test stopping the sync engine."""
        assert sync_engine._worker_thread.is_alive()

        sync_engine.stop()

        # Worker thread should stop
        assert not sync_engine._worker_thread.is_alive()

    @pytest.mark.integration
    def test_full_sync_workflow(self, sync_engine):
        """Test complete sync workflow from file creation to Confluence."""
        # Create test file
        test_file = sync_engine.docs_dir / "workflow_test.md"
        test_file.write_text("# Workflow Test\n\nThis is a test file.")

        # Enqueue creation event
        event = SyncEvent("created", test_file)
        sync_engine.enqueue_event(event)

        # Wait for processing
        time.sleep(0.3)

        # Verify complete workflow
        sync_engine.converter.convert_with_images.assert_called_once()
        sync_engine.confluence.create_page.assert_called_once()

        # Verify state was updated
        page_id = sync_engine.state.get_page_id(str(test_file))
        assert page_id == "123"  # From mock return value

    @pytest.mark.thread_safety
    def test_concurrent_event_processing(self, sync_engine):
        """Test concurrent event processing."""
        test_files = []

        # Create multiple test files
        for i in range(5):
            test_file = sync_engine.docs_dir / f"concurrent_test_{i}.md"
            test_file.write_text(f"# Test {i}")
            test_files.append(test_file)

        # Enqueue events from multiple threads
        def enqueue_events():
            for test_file in test_files:
                event = SyncEvent("created", test_file)
                sync_engine.enqueue_event(event)

        threads = [threading.Thread(target=enqueue_events) for _ in range(3)]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # Wait for processing
        time.sleep(0.5)

        # Should have processed multiple files
        assert sync_engine.converter.convert_with_images.call_count >= 5
