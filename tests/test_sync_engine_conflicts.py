"""Tests for SyncEngine conflict detection integration."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.confluence.client import ConfluenceClient
from src.confluence.converter import MarkdownConverter
from src.sync.conflict_detector import ConflictResolutionStrategy
from src.sync.engine import SyncEngine, SyncEvent


class TestSyncEngineConflictDetection:
    """Test conflict detection integration in SyncEngine."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)

    @pytest.fixture
    def mock_confluence_client(self):
        """Create a mock ConfluenceClient."""
        with patch.object(ConfluenceClient, "_instance", None):
            client = Mock(spec=ConfluenceClient)
            client.check_title_conflicts.return_value = {}
            client.create_page.return_value = {"id": "12345"}
            client.update_page.return_value = {"id": "12345"}
            yield client

    @pytest.fixture
    def mock_converter(self):
        """Create a mock MarkdownConverter."""
        converter = Mock(spec=MarkdownConverter)
        converter.convert_with_images.return_value = ("<p>Test content</p>", {})
        yield converter

    @pytest.fixture
    def sync_engine(self, temp_dir, mock_confluence_client, mock_converter):
        """Create a SyncEngine instance for testing."""
        with patch.object(SyncEngine, "_instance", None):
            state_file = temp_dir / "state.json"
            engine = SyncEngine.get_instance(
                docs_dir=temp_dir,
                state_file=state_file,
                confluence_client=mock_confluence_client,
                converter=mock_converter,
                conflict_strategy=ConflictResolutionStrategy.SKIP,
            )
            yield engine
            engine.stop()

    def test_sync_engine_initialization_with_conflict_strategy(self, sync_engine):
        """Test that SyncEngine initializes with conflict detection."""
        assert sync_engine.conflict_detector is not None
        assert sync_engine.conflict_detector.default_strategy == ConflictResolutionStrategy.SKIP

    def test_check_and_resolve_conflicts_no_conflicts(self, sync_engine, mock_confluence_client):
        """Test conflict checking when no conflicts exist."""
        mock_confluence_client.check_title_conflicts.return_value = {}

        result = sync_engine._check_and_resolve_conflicts("Test Page", Path("/docs/test.md"))

        assert result == "Test Page"
        mock_confluence_client.check_title_conflicts.assert_called_once_with(["Test Page"])

    def test_check_and_resolve_conflicts_with_skip_resolution(
        self, sync_engine, mock_confluence_client
    ):
        """Test conflict checking with SKIP resolution strategy."""
        mock_confluence_client.check_title_conflicts.return_value = {"Test Page": "12345"}

        result = sync_engine._check_and_resolve_conflicts("Test Page", Path("/docs/test.md"))

        assert result is None
        mock_confluence_client.check_title_conflicts.assert_called_once_with(["Test Page"])

    def test_check_and_resolve_conflicts_with_append_suffix_resolution(
        self, temp_dir, mock_confluence_client, mock_converter
    ):
        """Test conflict checking with APPEND_SUFFIX resolution strategy."""
        with patch.object(SyncEngine, "_instance", None):
            state_file = temp_dir / "state.json"
            engine = SyncEngine.get_instance(
                docs_dir=temp_dir,
                state_file=state_file,
                confluence_client=mock_confluence_client,
                converter=mock_converter,
                conflict_strategy=ConflictResolutionStrategy.APPEND_SUFFIX,
            )

            mock_confluence_client.check_title_conflicts.return_value = {"Test Page": "12345"}

            result = engine._check_and_resolve_conflicts("Test Page", Path("/docs/test.md"))

            assert result is not None
            assert result != "Test Page"
            assert "Test Page" in result

            engine.stop()

    def test_check_and_resolve_conflicts_exception_handling(
        self, sync_engine, mock_confluence_client
    ):
        """Test exception handling in conflict checking."""
        mock_confluence_client.check_title_conflicts.side_effect = Exception("API Error")

        # Should return original title on error to avoid blocking sync
        result = sync_engine._check_and_resolve_conflicts("Test Page", Path("/docs/test.md"))

        assert result == "Test Page"

    def test_scan_for_conflicts_no_untracked_files(self, sync_engine, mock_confluence_client):
        """Test scanning for conflicts when no untracked files exist."""
        # Mock empty directory
        conflicts = sync_engine.scan_for_conflicts()

        assert conflicts == {}
        # Should not call check_title_conflicts if no files to check
        mock_confluence_client.check_title_conflicts.assert_called_once_with([])

    def test_scan_for_conflicts_with_untracked_files(
        self, sync_engine, temp_dir, mock_confluence_client
    ):
        """Test scanning for conflicts with untracked files."""
        # Create some test files
        (temp_dir / "test1.md").write_text("# Test 1")
        (temp_dir / "test2.md").write_text("# Test 2")
        (temp_dir / "subfolder").mkdir()
        (temp_dir / "subfolder" / "test3.md").write_text("# Test 3")

        # Mock conflicts
        mock_confluence_client.check_title_conflicts.return_value = {
            "Test1": "12345",
            "Subfolder": "67890",
        }

        conflicts = sync_engine.scan_for_conflicts()

        assert conflicts == {"Test1": "12345", "Subfolder": "67890"}

        # Verify that titles were checked
        call_args = mock_confluence_client.check_title_conflicts.call_args[0][0]
        assert "Test1" in call_args
        assert "Test2" in call_args
        assert "Test3" in call_args
        assert "Subfolder" in call_args

    def test_scan_for_conflicts_skips_hidden_directories(
        self, sync_engine, temp_dir, mock_confluence_client
    ):
        """Test that scanning skips hidden and system directories."""
        # Create test structure with hidden directories
        (temp_dir / ".git").mkdir()
        (temp_dir / ".git" / "config").write_text("git config")
        (temp_dir / "__pycache__").mkdir()
        (temp_dir / "__pycache__" / "test.pyc").write_text("bytecode")
        (temp_dir / "docs").mkdir()
        (temp_dir / "docs" / "test.md").write_text("# Test")

        mock_confluence_client.check_title_conflicts.return_value = {}

        _ = sync_engine.scan_for_conflicts()

        # Verify that only valid directories/files were checked
        call_args = mock_confluence_client.check_title_conflicts.call_args[0][0]
        assert "Docs" in call_args
        assert "Test" in call_args
        assert ".Git" not in call_args
        assert "__Pycache__" not in call_args

    def test_process_event_file_creation_no_conflicts(
        self, sync_engine, temp_dir, mock_confluence_client, mock_converter
    ):
        """Test processing file creation event with no conflicts."""
        test_file = temp_dir / "test.md"
        test_file.write_text("# Test Content")

        mock_confluence_client.check_title_conflicts.return_value = {}

        event = SyncEvent("created", test_file)
        sync_engine._process_event(event)

        # Verify page was created
        mock_confluence_client.create_page.assert_called_once()
        create_call = mock_confluence_client.create_page.call_args
        assert create_call[1]["title"] == "Test"

    def test_process_event_file_creation_with_conflict_skip(
        self, sync_engine, temp_dir, mock_confluence_client, mock_converter
    ):
        """Test processing file creation event with conflict and SKIP resolution."""
        test_file = temp_dir / "test.md"
        test_file.write_text("# Test Content")

        mock_confluence_client.check_title_conflicts.return_value = {"Test": "12345"}

        event = SyncEvent("created", test_file)
        sync_engine._process_event(event)

        # Verify page was NOT created due to conflict
        mock_confluence_client.create_page.assert_not_called()

    def test_process_event_folder_creation_no_conflicts(
        self, sync_engine, temp_dir, mock_confluence_client
    ):
        """Test processing folder creation event with no conflicts."""
        test_folder = temp_dir / "test_folder"
        test_folder.mkdir()

        mock_confluence_client.check_title_conflicts.return_value = {}

        event = SyncEvent("folder_created", test_folder)
        sync_engine._process_event(event)

        # Verify folder page was created
        mock_confluence_client.create_page.assert_called_once()
        create_call = mock_confluence_client.create_page.call_args
        assert create_call[1]["title"] == "Test Folder"

    def test_process_event_folder_creation_with_conflict_skip(
        self, sync_engine, temp_dir, mock_confluence_client
    ):
        """Test processing folder creation event with conflict and SKIP resolution."""
        test_folder = temp_dir / "test_folder"
        test_folder.mkdir()

        mock_confluence_client.check_title_conflicts.return_value = {"Test Folder": "12345"}

        event = SyncEvent("folder_created", test_folder)
        sync_engine._process_event(event)

        # Verify folder page was NOT created due to conflict
        mock_confluence_client.create_page.assert_not_called()

    def test_get_conflict_summary(self, sync_engine):
        """Test getting conflict summary from SyncEngine."""
        # Add some mock conflicts to the detector
        from src.sync.conflict_detector import ConflictInfo, ConflictType

        conflict = ConflictInfo(
            conflict_type=ConflictType.TITLE_CONFLICT,
            local_path=Path("/docs/test.md"),
            proposed_title="Test Page",
            existing_page_id="12345",
        )
        sync_engine.conflict_detector.detected_conflicts.append(conflict)

        summary = sync_engine.get_conflict_summary()

        assert summary == {"title_conflict": 1}

    def test_process_event_update_existing_page_no_conflict_check(
        self, sync_engine, temp_dir, mock_confluence_client, mock_converter
    ):
        """Test that updating existing pages doesn't trigger conflict checking."""
        test_file = temp_dir / "test.md"
        test_file.write_text("# Updated Content")

        # Simulate existing page mapping using resolved path (same as SyncEvent)
        resolved_path = test_file.resolve()
        sync_engine.state.add_mapping(str(resolved_path), "12345", 1234567890)

        # Verify the mapping exists before processing
        page_id = sync_engine.state.get_page_id(str(resolved_path))
        assert page_id == "12345", f"Expected page_id '12345', got '{page_id!r}'"

        event = SyncEvent("modified", test_file)
        sync_engine._process_event(event)

        # Verify conflict checking was not called for existing pages
        mock_confluence_client.check_title_conflicts.assert_not_called()
        # Verify page was updated
        mock_confluence_client.update_page.assert_called_once()


class TestSyncEngineConflictDetectionIntegration:
    """Integration tests for SyncEngine conflict detection."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)

    def test_full_conflict_workflow_with_append_suffix(self, temp_dir):
        """Test complete conflict detection workflow with APPEND_SUFFIX strategy."""
        # Create test files
        (temp_dir / "existing_page.md").write_text("# Existing Page")
        (temp_dir / "new_page.md").write_text("# New Page")

        # Mock ConfluenceClient
        with patch.object(ConfluenceClient, "_instance", None):
            mock_client = Mock(spec=ConfluenceClient)
            mock_client.check_title_conflicts.side_effect = [
                {"Existing Page": "12345"},  # First call - conflict
                {},  # Second call - no conflict
            ]
            mock_client.create_page.return_value = {"id": "67890"}

            # Mock MarkdownConverter
            mock_converter = Mock(spec=MarkdownConverter)
            mock_converter.convert_with_images.return_value = ("<p>Content</p>", {})

            # Create SyncEngine with APPEND_SUFFIX strategy
            with patch.object(SyncEngine, "_instance", None):
                state_file = temp_dir / "state.json"
                engine = SyncEngine.get_instance(
                    docs_dir=temp_dir,
                    state_file=state_file,
                    confluence_client=mock_client,
                    converter=mock_converter,
                    conflict_strategy=ConflictResolutionStrategy.APPEND_SUFFIX,
                )

                # Process events
                existing_file = temp_dir / "existing_page.md"
                new_file = temp_dir / "new_page.md"

                engine._process_event(SyncEvent("created", existing_file))
                engine._process_event(SyncEvent("created", new_file))

                # Verify conflict checking was called
                assert mock_client.check_title_conflicts.call_count == 2

                # Verify pages were created
                assert mock_client.create_page.call_count == 2

                # Verify first page was created with modified title
                first_call = mock_client.create_page.call_args_list[0]
                first_title = first_call[1]["title"]
                assert first_title != "Existing Page"
                assert "Existing Page" in first_title

                # Verify second page was created with original title
                second_call = mock_client.create_page.call_args_list[1]
                second_title = second_call[1]["title"]
                assert second_title == "New Page"

                engine.stop()

    def test_scan_for_conflicts_comprehensive(self, temp_dir):
        """Test comprehensive conflict scanning with various file types."""
        # Create complex directory structure
        (temp_dir / "docs").mkdir()
        (temp_dir / "docs" / "getting_started.md").write_text("# Getting Started")
        (temp_dir / "docs" / "user_guide.md").write_text("# User Guide")

        (temp_dir / "api").mkdir()
        (temp_dir / "api" / "reference.md").write_text("# API Reference")
        (temp_dir / "api" / "examples").mkdir()
        (temp_dir / "api" / "examples" / "basic.md").write_text("# Basic Examples")

        # Mock ConfluenceClient
        with patch.object(ConfluenceClient, "_instance", None):
            mock_client = Mock(spec=ConfluenceClient)
            mock_client.check_title_conflicts.return_value = {
                "Getting Started": "12345",
                "Api": "67890",
            }

            mock_converter = Mock(spec=MarkdownConverter)

            # Create SyncEngine
            with patch.object(SyncEngine, "_instance", None):
                state_file = temp_dir / "state.json"
                engine = SyncEngine.get_instance(
                    docs_dir=temp_dir,
                    state_file=state_file,
                    confluence_client=mock_client,
                    converter=mock_converter,
                )

                # Scan for conflicts
                conflicts = engine.scan_for_conflicts()

                # Verify results
                assert conflicts == {"Getting Started": "12345", "Api": "67890"}

                # Verify all expected titles were checked
                call_args = mock_client.check_title_conflicts.call_args[0][0]
                expected_titles = {
                    "Docs",
                    "Getting Started",
                    "User Guide",
                    "Api",
                    "Reference",
                    "Examples",
                    "Basic",
                }
                assert set(call_args) == expected_titles

                engine.stop()
