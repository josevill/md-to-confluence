"""Integration tests for md-to-confluence."""

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

from src.config import setup_logging
from src.confluence.client import ConfluenceClient
from src.confluence.converter import MarkdownConverter
from src.monitor.file_watcher import FileMonitor
from src.sync.engine import SyncEngine, SyncEvent
from src.sync.state import SyncState
from src.ui.app import MDToConfluenceApp


class TestComponentIntegration:
    """Test integration between core components."""

    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            docs_dir = workspace / "docs"
            logs_dir = workspace / "logs"
            docs_dir.mkdir()
            logs_dir.mkdir()

            yield {
                "workspace": workspace,
                "docs_dir": docs_dir,
                "logs_dir": logs_dir,
                "state_file": workspace / "state.json",
                "config_file": workspace / "config.json",
            }

    @pytest.fixture
    def mock_confluence_client(self):
        """Mock ConfluenceClient for integration tests."""
        mock_client = Mock(spec=ConfluenceClient)
        mock_client.create_page.return_value = {"id": "123", "title": "Test Page"}
        mock_client.update_page.return_value = {"id": "123", "title": "Updated Page"}
        mock_client.delete_page.return_value = None
        mock_client.upload_attachment.return_value = {"id": "att123"}
        return mock_client

    @pytest.fixture
    def converter(self):
        """Create a real MarkdownConverter instance."""
        return MarkdownConverter()

    @pytest.fixture
    def sync_engine(self, temp_workspace, mock_confluence_client, converter):
        """Create SyncEngine with real components."""
        # Clear any existing instance
        SyncEngine._instance = None

        engine = SyncEngine.get_instance(
            docs_dir=temp_workspace["docs_dir"],
            state_file=temp_workspace["state_file"],
            confluence_client=mock_confluence_client,
            converter=converter,
            debounce_interval=0.1,
        )

        yield engine

        engine.stop()
        SyncEngine._instance = None

    def test_state_and_engine_integration(self, sync_engine, temp_workspace):
        """Test integration between SyncState and SyncEngine."""
        # Create test file
        test_file = temp_workspace["docs_dir"] / "integration_test.md"
        test_file.write_text("# Integration Test\n\nThis is a test.")

        # Process creation event
        event = SyncEvent("created", test_file)
        sync_engine._process_event(event)

        # Verify state was updated (use resolved path to match SyncEvent behavior)
        page_id = sync_engine.state.get_page_id(str(test_file.resolve()))
        assert page_id == "123"  # From mock return value

        # Verify Confluence operations were called
        sync_engine.confluence.create_page.assert_called_once()

    def test_converter_and_engine_integration(self, sync_engine, temp_workspace):
        """Test integration between MarkdownConverter and SyncEngine."""
        # Create test file with markdown content
        content = """# Test Document

This is a **test** document with:

- List item 1
- List item 2

```python
def hello():
    print("Hello, World!")
```

> This is a note block.
"""
        test_file = temp_workspace["docs_dir"] / "converter_test.md"
        test_file.write_text(content)

        # Process creation event
        event = SyncEvent("created", test_file)
        sync_engine._process_event(event)

        # Verify converter was called and Confluence page was created
        sync_engine.confluence.create_page.assert_called_once()

        # Get the call arguments to verify conversion
        call_args = sync_engine.confluence.create_page.call_args
        assert "body" in call_args.kwargs
        converted_body = call_args.kwargs["body"]

        # Verify conversion worked (contains XHTML and Confluence macros)
        assert "<p>" in converted_body
        assert "<strong>" in converted_body
        assert 'ac:name="code"' in converted_body

    def test_file_monitor_and_engine_integration(self, sync_engine, temp_workspace):
        """Test integration between FileMonitor and SyncEngine."""
        # Create file monitor
        monitor = FileMonitor(docs_dir=temp_workspace["docs_dir"], sync_engine=sync_engine)

        # Start monitoring
        monitor.start()

        try:
            # Create a test file
            test_file = temp_workspace["docs_dir"] / "monitor_test.md"
            test_file.write_text("# Monitor Test")

            # Wait for file system event and processing
            time.sleep(0.3)

            # Verify file was processed (use resolved path to match SyncEvent behavior)
            page_id = sync_engine.state.get_page_id(str(test_file.resolve()))
            assert page_id is not None

        finally:
            monitor.stop()

    def test_ui_and_engine_integration(self, sync_engine):
        """Test integration between UI and SyncEngine."""
        # Create UI app with real sync engine
        app = MDToConfluenceApp(sync_engine=sync_engine)

        # Verify app is properly configured
        assert app.sync_engine is sync_engine
        assert app.state is sync_engine.state

        # Test that app can get file statuses
        tracked_files = app.state.get_all_tracked_files()
        assert isinstance(tracked_files, set)


@pytest.fixture
def full_workspace():
    """Create a complete workspace with all necessary files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir)

        # Create directory structure
        docs_dir = workspace / "docs"
        logs_dir = workspace / "logs"
        docs_dir.mkdir()
        logs_dir.mkdir()

        # Create nested structure
        (docs_dir / "advanced").mkdir()
        (docs_dir / "images").mkdir()

        # Create config file
        config = {
            "confluence": {
                "base_url": "https://test.atlassian.net",
                "space_key": "TEST",
                "token_op_item": "test-item",
            },
            "docs_dir": str(docs_dir),
            "sync": {"debounce_interval": 1.0},
        }
        config_file = workspace / "config.json"
        config_file.write_text(json.dumps(config, indent=2))

        yield {
            "workspace": workspace,
            "docs_dir": docs_dir,
            "logs_dir": logs_dir,
            "config_file": config_file,
            "state_file": workspace / "state.json",
        }


@pytest.fixture
def mock_confluence_for_e2e():
    """Enhanced mock for end-to-end testing."""
    mock_client = Mock(spec=ConfluenceClient)

    # Track created pages
    created_pages = {}
    page_counter = [100]  # Use list for mutability

    def mock_create_page(title, body, parent_id=None):
        page_id = str(page_counter[0])
        page_counter[0] += 1
        page_data = {"id": page_id, "title": title, "body": body, "parent_id": parent_id}
        created_pages[page_id] = page_data
        return page_data

    def mock_update_page(page_id, title, body):
        if page_id in created_pages:
            created_pages[page_id].update({"title": title, "body": body})
            return created_pages[page_id]
        return None

    def mock_delete_page(page_id):
        if page_id in created_pages:
            del created_pages[page_id]
            return True
        return False

    def mock_check_title_conflicts(titles):
        """Mock conflict checking - return empty dict (no conflicts)."""
        return {}

    def mock_get_space_page_titles():
        """Mock space page titles - return empty list."""
        return []

    mock_client.create_page.side_effect = mock_create_page
    mock_client.update_page.side_effect = mock_update_page
    mock_client.delete_page.side_effect = mock_delete_page
    mock_client.upload_attachment.return_value = {"id": "att123"}
    mock_client.check_title_conflicts.side_effect = mock_check_title_conflicts
    mock_client.get_space_page_titles.return_value = []

    # Add access to created pages for verification
    mock_client._created_pages = created_pages

    return mock_client


class TestEndToEndWorkflows:
    """Test complete end-to-end workflows."""

    @pytest.mark.integration
    def test_complete_file_lifecycle(self, full_workspace, mock_confluence_for_e2e):
        """Test complete file lifecycle: create, modify, delete."""
        # Clear any existing instance
        SyncEngine._instance = None

        # Set up components
        converter = MarkdownConverter()
        sync_engine = SyncEngine.get_instance(
            docs_dir=full_workspace["docs_dir"],
            state_file=full_workspace["state_file"],
            confluence_client=mock_confluence_for_e2e,
            converter=converter,
            debounce_interval=0.1,
        )

        try:
            # 1. Create file
            test_file = full_workspace["docs_dir"] / "lifecycle_test.md"
            initial_content = "# Lifecycle Test\n\nInitial content."
            test_file.write_text(initial_content)

            # Process creation
            create_event = SyncEvent("created", test_file)
            sync_engine._process_event(create_event)

            # Verify creation (use resolved path for consistency)
            page_id = sync_engine.state.get_page_id(str(test_file.resolve()))
            assert page_id is not None
            assert page_id in mock_confluence_for_e2e._created_pages

            # 2. Modify file
            modified_content = "# Lifecycle Test\n\nModified content with **formatting**."
            test_file.write_text(modified_content)

            # Process modification
            modify_event = SyncEvent("modified", test_file)
            sync_engine._process_event(modify_event)

            # Verify modification
            updated_page = mock_confluence_for_e2e._created_pages[page_id]
            assert "<strong>formatting</strong>" in updated_page["body"]

            # 3. Delete file
            test_file.unlink()

            # Process deletion
            delete_event = SyncEvent("deleted", test_file)
            sync_engine._process_event(delete_event)

            # Verify deletion
            assert page_id not in mock_confluence_for_e2e._created_pages
            assert sync_engine.state.get_page_id(str(test_file.resolve())) is None

        finally:
            sync_engine.stop()
            SyncEngine._instance = None

    @pytest.mark.integration
    def test_hierarchical_structure_sync(self, full_workspace, mock_confluence_for_e2e):
        """Test syncing hierarchical directory structure."""
        # Clear any existing instance
        SyncEngine._instance = None

        converter = MarkdownConverter()
        sync_engine = SyncEngine.get_instance(
            docs_dir=full_workspace["docs_dir"],
            state_file=full_workspace["state_file"],
            confluence_client=mock_confluence_for_e2e,
            converter=converter,
            debounce_interval=0.1,
        )

        try:
            # Create nested files
            files = {
                "index.md": "# Main Index\n\nWelcome to the documentation.",
                "getting-started.md": "# Getting Started\n\nHow to get started.",
                "advanced/configuration.md": "# Configuration\n\nAdvanced configuration.",
                "advanced/troubleshooting.md": "# Troubleshooting\n\nCommon issues.",
            }

            created_page_ids = {}

            for file_path, content in files.items():
                file_obj = full_workspace["docs_dir"] / file_path
                file_obj.parent.mkdir(parents=True, exist_ok=True)
                file_obj.write_text(content)

                # Process creation
                event = SyncEvent("created", file_obj)
                sync_engine._process_event(event)

                # Track page ID
                page_id = sync_engine.state.get_page_id(str(file_obj.resolve()))
                created_page_ids[file_path] = page_id

            # Verify all files were processed
            assert len(created_page_ids) == 4
            assert all(page_id is not None for page_id in created_page_ids.values())

            # Verify hierarchical relationships would be established
            # (parent_id logic would need to be enhanced for full hierarchy)

        finally:
            sync_engine.stop()
            SyncEngine._instance = None

    @pytest.mark.integration
    def test_file_with_images_workflow(self, full_workspace, mock_confluence_for_e2e):
        """Test complete workflow with image handling."""
        # Clear any existing instance
        SyncEngine._instance = None

        converter = MarkdownConverter()
        sync_engine = SyncEngine.get_instance(
            docs_dir=full_workspace["docs_dir"],
            state_file=full_workspace["state_file"],
            confluence_client=mock_confluence_for_e2e,
            converter=converter,
            debounce_interval=0.1,
        )

        try:
            # Create an image file (mock)
            image_file = full_workspace["docs_dir"] / "images" / "diagram.png"
            image_file.write_bytes(b"fake_png_data")

            # Create markdown file with image reference
            content = """# Document with Images

This document contains an image:

![Diagram](images/diagram.png)

And some more content.
"""
            test_file = full_workspace["docs_dir"] / "with_images.md"
            test_file.write_text(content)

            # Process the file
            event = SyncEvent("created", test_file)
            sync_engine._process_event(event)

            # Verify page was created
            page_id = sync_engine.state.get_page_id(str(test_file.resolve()))
            assert page_id is not None

            # Verify image upload was attempted
            sync_engine.confluence.upload_attachment.assert_called()

            # Verify final content contains image macro or fallback
            created_page = mock_confluence_for_e2e._created_pages[page_id]
            # Should contain either image macro or fallback info macro
            assert (
                'ac:name="image"' in created_page["body"]
                or 'ac:name="info"' in created_page["body"]
                or "![" in created_page["body"]
            )
        finally:
            sync_engine.stop()
            SyncEngine._instance = None

    @pytest.mark.integration
    def test_error_recovery_workflow(self, full_workspace, mock_confluence_for_e2e):
        """Test error recovery in end-to-end workflow."""
        # Clear any existing instance
        SyncEngine._instance = None

        converter = MarkdownConverter()
        sync_engine = SyncEngine.get_instance(
            docs_dir=full_workspace["docs_dir"],
            state_file=full_workspace["state_file"],
            confluence_client=mock_confluence_for_e2e,
            converter=converter,
            debounce_interval=0.1,
        )

        try:
            # Create test file
            test_file = full_workspace["docs_dir"] / "error_test.md"
            test_file.write_text("# Error Test\n\nThis will cause an error.")

            # First, cause an error during page creation
            mock_confluence_for_e2e.create_page.side_effect = Exception("Confluence error")

            # Process event - should handle error gracefully
            event = SyncEvent("created", test_file)
            sync_engine._process_event(event)

            # File should not be in state due to error
            page_id = sync_engine.state.get_page_id(str(test_file.resolve()))
            assert page_id is None

            # Restore normal behavior
            mock_confluence_for_e2e.create_page.side_effect = None
            mock_confluence_for_e2e.create_page.return_value = {
                "id": "recovery123",
                "title": "Test",
            }

            # Process again - should succeed
            sync_engine._process_event(event)

            # Now should be in state
            page_id = sync_engine.state.get_page_id(str(test_file.resolve()))
            assert page_id == "recovery123"

        finally:
            sync_engine.stop()
            SyncEngine._instance = None

    @pytest.mark.integration
    def test_concurrent_file_operations(self, full_workspace, mock_confluence_for_e2e):
        """Test handling of concurrent file operations."""
        # Clear any existing instance
        SyncEngine._instance = None

        converter = MarkdownConverter()
        sync_engine = SyncEngine.get_instance(
            docs_dir=full_workspace["docs_dir"],
            state_file=full_workspace["state_file"],
            confluence_client=mock_confluence_for_e2e,
            converter=converter,
            debounce_interval=0.1,
        )

        try:
            # Create multiple files simultaneously
            files = []
            for i in range(5):
                test_file = full_workspace["docs_dir"] / f"concurrent_test_{i}.md"
                test_file.write_text(f"# Concurrent Test {i}\n\nContent for file {i}.")
                files.append(test_file)

            # Process all events
            for test_file in files:
                event = SyncEvent("created", test_file)
                sync_engine.enqueue_event(event)

            # Wait for processing
            time.sleep(0.5)

            # Verify all files were processed
            processed_count = 0
            for test_file in files:
                page_id = sync_engine.state.get_page_id(str(test_file.resolve()))
                if page_id is not None:
                    processed_count += 1

            # Should have processed most or all files
            assert processed_count >= 3  # Allow for some timing variations

        finally:
            sync_engine.stop()
            SyncEngine._instance = None


class TestSystemLevelIntegration:
    """Test system-level integration scenarios."""

    @pytest.mark.integration
    def test_logging_integration(self):
        """Test logging integration across components."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logs_dir = Path(temp_dir) / "logs"
            logs_dir.mkdir()

            # Set up logging
            setup_logging(logs_dir=logs_dir)

            # Components should log properly
            import logging

            logger = logging.getLogger("test")
            logger.info("Test logging integration")

            # Verify log file was created
            log_files = list(logs_dir.glob("*.log"))
            assert len(log_files) > 0

    @pytest.mark.integration
    def test_configuration_loading(self):
        """Test configuration loading and validation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "config.json"

            # Create valid config
            config_data = {
                "confluence": {
                    "base_url": "https://test.atlassian.net",
                    "space_key": "TEST",
                    "token_op_item": "test-item",
                },
                "docs_dir": "docs",
                "sync": {"debounce_interval": 2.0},
            }

            config_file.write_text(json.dumps(config_data))

            # Load config
            from src.ui.app import load_config

            loaded_config = load_config(config_file)

            assert loaded_config == config_data

    @pytest.mark.integration
    def test_state_persistence_across_restarts(self, full_workspace, mock_confluence_for_e2e):
        """Test state persistence across application restarts."""
        converter = MarkdownConverter()

        # First session
        SyncEngine._instance = None
        sync_engine1 = SyncEngine.get_instance(
            docs_dir=full_workspace["docs_dir"],
            state_file=full_workspace["state_file"],
            confluence_client=mock_confluence_for_e2e,
            converter=converter,
        )

        # Create and process file
        test_file = full_workspace["docs_dir"] / "persistence_test.md"
        test_file.write_text("# Persistence Test")

        event = SyncEvent("created", test_file)
        sync_engine1._process_event(event)

        page_id1 = sync_engine1.state.get_page_id(str(test_file.resolve()))
        assert page_id1 is not None

        # Stop first session
        sync_engine1.stop()
        SyncEngine._instance = None

        # Second session (simulating restart)
        sync_engine2 = SyncEngine.get_instance(
            docs_dir=full_workspace["docs_dir"],
            state_file=full_workspace["state_file"],
            confluence_client=mock_confluence_for_e2e,
            converter=converter,
        )

        # Verify state was persisted
        page_id2 = sync_engine2.state.get_page_id(str(test_file.resolve()))
        assert page_id2 == page_id1

        sync_engine2.stop()
        SyncEngine._instance = None

    @pytest.mark.slow
    @pytest.mark.integration
    def test_performance_with_many_files(self, full_workspace, mock_confluence_for_e2e):
        """Test performance with many files."""
        # Clear any existing instance
        SyncEngine._instance = None

        converter = MarkdownConverter()
        sync_engine = SyncEngine.get_instance(
            docs_dir=full_workspace["docs_dir"],
            state_file=full_workspace["state_file"],
            confluence_client=mock_confluence_for_e2e,
            converter=converter,
            debounce_interval=0.05,  # Faster for performance test
        )

        try:
            # Create many files
            num_files = 20
            files = []

            start_time = time.time()

            for i in range(num_files):
                test_file = full_workspace["docs_dir"] / f"perf_test_{i:03d}.md"
                content = (
                    f"# Performance Test {i}\n\nContent for file {i} with some **formatting**."
                )
                test_file.write_text(content)
                files.append(test_file)

                # Enqueue event
                event = SyncEvent("created", test_file)
                sync_engine.enqueue_event(event)

            # Wait for all processing to complete
            time.sleep(2.0)

            end_time = time.time()
            processing_time = end_time - start_time

            # Verify files were processed
            processed_count = sum(
                1 for f in files if sync_engine.state.get_page_id(str(f.resolve())) is not None
            )

            # Performance assertions
            assert processed_count >= num_files * 0.8  # At least 80% processed
            assert processing_time < 30.0  # Should complete within 30 seconds

            # Calculate throughput
            throughput = processed_count / processing_time
            assert throughput > 0.5  # At least 0.5 files per second

        finally:
            sync_engine.stop()
            SyncEngine._instance = None
