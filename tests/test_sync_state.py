"""Tests for SyncState."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.sync.state import SyncState


class TestSyncState:
    """Test suite for SyncState."""

    @pytest.fixture
    def temp_state_file(self):
        """Create a temporary state file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_path = Path(f.name)
        yield temp_path
        # Clean up
        if temp_path.exists():
            temp_path.unlink()

    @pytest.fixture
    def state(self, temp_state_file):
        """Create a SyncState instance with temporary file."""
        return SyncState(temp_state_file)

    def test_initialization_creates_new_state(self, temp_state_file):
        """Test initialization with non-existent state file."""
        # Remove the file to test creation
        if temp_state_file.exists():
            temp_state_file.unlink()

        state = SyncState(temp_state_file)

        assert state.state_file == temp_state_file
        assert state._state == {
            "file_to_page": {},
            "page_to_file": {},
            "last_sync": {},
            "deleted_pages": [],
        }

    def test_initialization_loads_existing_state(self, temp_state_file):
        """Test initialization with existing valid state file."""
        existing_state = {
            "file_to_page": {"test.md": "123"},
            "page_to_file": {"123": "test.md"},
            "last_sync": {"test.md": 1234567890.0},
            "deleted_pages": [],
        }

        with temp_state_file.open("w") as f:
            json.dump(existing_state, f)

        state = SyncState(temp_state_file)

        assert state._state == existing_state

    def test_validate_state_valid(self, state):
        """Test validation of valid state structure."""
        valid_state = {
            "file_to_page": {"test.md": "123"},
            "page_to_file": {"123": "test.md"},
            "last_sync": {"test.md": 1234567890.0},
            "deleted_pages": ["456"],
        }

        assert state._validate_state(valid_state) is True

    def test_validate_state_invalid_missing_keys(self, state):
        """Test validation fails for missing keys."""
        invalid_state = {
            "file_to_page": {},
            "page_to_file": {},
            # Missing last_sync and deleted_pages
        }

        assert state._validate_state(invalid_state) is False

    def test_validate_state_invalid_wrong_types(self, state):
        """Test validation fails for wrong data types."""
        invalid_state = {
            "file_to_page": "not_a_dict",
            "page_to_file": {},
            "last_sync": {},
            "deleted_pages": [],
        }

        assert state._validate_state(invalid_state) is False

    def test_validate_state_not_dict(self, state):
        """Test validation fails for non-dict input."""
        assert state._validate_state("not_a_dict") is False
        assert state._validate_state([]) is False
        assert state._validate_state(None) is False

    def test_load_state_empty_file(self, temp_state_file):
        """Test loading from empty file."""
        # Create empty file
        temp_state_file.write_text("")

        state = SyncState(temp_state_file)

        assert state._state == state._get_default_state()

    def test_load_state_corrupted_json(self, temp_state_file):
        """Test loading from corrupted JSON file."""
        # Write invalid JSON
        temp_state_file.write_text("{ invalid json }")

        state = SyncState(temp_state_file)

        assert state._state == state._get_default_state()
        # Check that backup file was created
        backup_file = temp_state_file.with_suffix(".corrupted.bak")
        assert backup_file.exists()
        backup_file.unlink()  # Clean up

    def test_load_state_invalid_structure(self, temp_state_file):
        """Test loading from file with invalid structure."""
        invalid_state = {"wrong": "structure"}

        with temp_state_file.open("w") as f:
            json.dump(invalid_state, f)

        state = SyncState(temp_state_file)

        assert state._state == state._get_default_state()
        # Check that backup file was created
        backup_file = temp_state_file.with_suffix(".corrupted.bak")
        assert backup_file.exists()
        backup_file.unlink()  # Clean up

    @patch("builtins.open", side_effect=PermissionError("Permission denied"))
    def test_load_state_permission_error(self, mock_file, temp_state_file):
        """Test handling of permission errors."""
        state = SyncState(temp_state_file)

        assert state._state == state._get_default_state()

    def test_backup_corrupted_file(self, temp_state_file):
        """Test backup creation for corrupted files."""
        # Create a file with content
        temp_state_file.write_text("corrupted content")

        state = SyncState(temp_state_file)
        state._backup_corrupted_file()

        backup_file = temp_state_file.with_suffix(".corrupted.bak")
        assert backup_file.exists()
        assert backup_file.read_text() == "corrupted content"
        backup_file.unlink()  # Clean up

    def test_backup_corrupted_file_permission_error(self, temp_state_file):
        """Test backup when rename fails."""
        temp_state_file.write_text("content")

        state = SyncState(temp_state_file)

        # Mock the shutil.move function at the module level
        with patch("shutil.move", side_effect=PermissionError()):
            # This should handle the permission error gracefully
            state._backup_corrupted_file()

        # The file should still exist since backup failed
        assert temp_state_file.exists()

    def test_save_state(self, state):
        """Test saving state to file."""
        state._state["file_to_page"]["test.md"] = "123"

        state._save_state()

        # Read the file and verify content
        with state.state_file.open("r") as f:
            saved_state = json.load(f)

        assert saved_state == state._state

    def test_save_state_permission_error(self, state):
        """Test save with permission error."""
        with patch("builtins.open", side_effect=PermissionError("Permission denied")):
            state._save_state()  # Should not raise exception

    def test_get_page_id(self, state):
        """Test getting page ID for file path."""
        state._state["file_to_page"]["test.md"] = "123"

        assert state.get_page_id("test.md") == "123"
        assert state.get_page_id("nonexistent.md") is None

    def test_get_file_path(self, state):
        """Test getting file path for page ID."""
        state._state["page_to_file"]["123"] = "test.md"

        assert state.get_file_path("123") == "test.md"
        assert state.get_file_path("nonexistent") is None

    def test_add_mapping(self, state):
        """Test adding file-to-page mapping."""
        with patch.object(state, "_save_state") as mock_save:
            state.add_mapping("test.md", "123", 1234567890.0)

        assert state._state["file_to_page"]["test.md"] == "123"
        assert state._state["page_to_file"]["123"] == "test.md"
        assert state._state["last_sync"]["test.md"] == 1234567890.0
        mock_save.assert_called_once()

    def test_add_mapping_path_object(self, state):
        """Test adding mapping with Path object."""
        file_path = Path("test.md")

        with patch.object(state, "_save_state") as mock_save:
            state.add_mapping(file_path, "123", 1234567890.0)

        assert state._state["file_to_page"]["test.md"] == "123"
        mock_save.assert_called_once()

    def test_remove_mapping(self, state):
        """Test removing file-to-page mapping."""
        # Set up existing mapping
        state._state["file_to_page"]["test.md"] = "123"
        state._state["page_to_file"]["123"] = "test.md"
        state._state["last_sync"]["test.md"] = 1234567890.0

        with patch.object(state, "_save_state") as mock_save:
            removed_page_id = state.remove_mapping("test.md")

        assert removed_page_id == "123"
        assert "test.md" not in state._state["file_to_page"]
        assert "123" not in state._state["page_to_file"]
        assert "test.md" not in state._state["last_sync"]
        assert "123" in state._state["deleted_pages"]
        mock_save.assert_called_once()

    def test_remove_mapping_nonexistent(self, state):
        """Test removing non-existent mapping."""
        with patch.object(state, "_save_state") as mock_save:
            removed_page_id = state.remove_mapping("nonexistent.md")

        assert removed_page_id is None
        mock_save.assert_not_called()

    def test_get_last_sync_time(self, state):
        """Test getting last sync time."""
        state._state["last_sync"]["test.md"] = 1234567890.0

        assert state.get_last_sync_time("test.md") == 1234567890.0
        assert state.get_last_sync_time("nonexistent.md") is None

    def test_update_sync_time(self, state):
        """Test updating sync time."""
        with patch.object(state, "_save_state") as mock_save:
            state.update_sync_time("test.md", 1234567890.0)

        assert state._state["last_sync"]["test.md"] == 1234567890.0
        mock_save.assert_called_once()

    def test_is_page_deleted(self, state):
        """Test checking if page is deleted."""
        state._state["deleted_pages"] = ["123", "456"]

        assert state.is_page_deleted("123") is True
        assert state.is_page_deleted("789") is False

    def test_get_all_tracked_files(self, state):
        """Test getting all tracked files."""
        state._state["file_to_page"] = {
            "test1.md": "123",
            "test2.md": "456",
            "subfolder/test3.md": "789",
        }

        tracked_files = state.get_all_tracked_files()

        expected = {"test1.md", "test2.md", "subfolder/test3.md"}
        assert tracked_files == expected

    def test_get_all_tracked_pages(self, state):
        """Test getting all tracked pages."""
        state._state["page_to_file"] = {
            "123": "test1.md",
            "456": "test2.md",
            "789": "subfolder/test3.md",
        }

        tracked_pages = state.get_all_tracked_pages()

        expected = {"123", "456", "789"}
        assert tracked_pages == expected

    def test_clear_deleted_pages(self, state):
        """Test clearing deleted pages list."""
        state._state["deleted_pages"] = ["123", "456", "789"]

        with patch.object(state, "_save_state") as mock_save:
            state.clear_deleted_pages()

        assert state._state["deleted_pages"] == []
        mock_save.assert_called_once()

    def test_state_persistence_across_instances(self, temp_state_file):
        """Test that state persists across different instances."""
        # Create first instance and add mapping
        state1 = SyncState(temp_state_file)
        state1.add_mapping("test.md", "123", 1234567890.0)

        # Create second instance and verify mapping exists
        state2 = SyncState(temp_state_file)

        assert state2.get_page_id("test.md") == "123"
        assert state2.get_file_path("123") == "test.md"
        assert state2.get_last_sync_time("test.md") == 1234567890.0

    def test_concurrent_access_safety(self, state):
        """Test basic safety for concurrent access."""
        import threading

        results = []
        errors = []

        def add_mapping(file_num):
            try:
                state.add_mapping(f"test{file_num}.md", f"page{file_num}", float(file_num))
                results.append(file_num)
            except Exception as e:
                errors.append(e)

        # Create multiple threads
        threads = [threading.Thread(target=add_mapping, args=[i]) for i in range(10)]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # Should have no errors and all mappings
        assert len(errors) == 0
        assert len(results) == 10
        assert len(state._state["file_to_page"]) == 10

    @pytest.mark.unit
    def test_default_state_structure(self, state):
        """Test default state has correct structure."""
        default_state = state._get_default_state()

        assert isinstance(default_state, dict)
        assert "file_to_page" in default_state
        assert "page_to_file" in default_state
        assert "last_sync" in default_state
        assert "deleted_pages" in default_state

        assert isinstance(default_state["file_to_page"], dict)
        assert isinstance(default_state["page_to_file"], dict)
        assert isinstance(default_state["last_sync"], dict)
        assert isinstance(default_state["deleted_pages"], list)

    @pytest.mark.integration
    def test_full_workflow(self, state):
        """Test complete workflow of state management."""
        # Add initial mapping
        state.add_mapping("docs/test.md", "123", 1234567890.0)

        # Verify mapping exists
        assert state.get_page_id("docs/test.md") == "123"
        assert state.get_file_path("123") == "docs/test.md"
        assert state.get_last_sync_time("docs/test.md") == 1234567890.0

        # Update sync time
        state.update_sync_time("docs/test.md", 1234567900.0)
        assert state.get_last_sync_time("docs/test.md") == 1234567900.0

        # Add another mapping
        state.add_mapping("docs/other.md", "456", 1234567910.0)

        # Check all tracked files and pages
        assert len(state.get_all_tracked_files()) == 2
        assert len(state.get_all_tracked_pages()) == 2

        # Remove a mapping
        removed_id = state.remove_mapping("docs/test.md")
        assert removed_id == "123"
        assert state.is_page_deleted("123") is True

        # Verify only one mapping remains
        assert len(state.get_all_tracked_files()) == 1
        assert state.get_page_id("docs/other.md") == "456"

        # Clear deleted pages
        state.clear_deleted_pages()
        assert not state.is_page_deleted("123")
