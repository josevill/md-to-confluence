import json
import logging
from pathlib import Path
from typing import Dict, Optional, Set

logger = logging.getLogger(__name__)


class SyncState:
    """
    Manages the state of synchronization between
    local files and Confluence pages.
    """

    def __init__(self: "SyncState", state_file: Path) -> None:
        """Initialize the sync state manager.

        Args:
            state_file: Path to the JSON file for storing state
        """
        self.state_file = state_file
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self._state = self._load_state()

    def _load_state(self: "SyncState") -> dict:
        """Load the state from the JSON file.

        Returns:
            The loaded state or an empty state if file doesn't exist
        """
        if not self.state_file.exists():
            return {
                "file_to_page": {},  # Maps file paths to page IDs
                "page_to_file": {},  # Reverse mapping for quick lookups
                "last_sync": {},  # Last sync timestamp for each file
                "deleted_pages": [],  # Track deleted pages to handle conflicts
            }

        try:
            with self.state_file.open("r", encoding="utf-8") as f:
                state = json.load(f)
                logger.info(f"Loaded sync state from {self.state_file}")
                return state
        except json.JSONDecodeError:
            logger.error(f"Failed to parse state file: {self.state_file}")
            # Return empty state on error
            return self._load_state()
        except Exception as e:
            logger.error(f"Error loading state file: {e}")
            # Return empty state on error
            return self._load_state()

    def _save_state(self: "SyncState") -> None:
        """Save the current state to the JSON file."""
        try:
            with self.state_file.open("w", encoding="utf-8") as f:
                json.dump(self._state, f, indent=2)
            logger.debug(f"Saved sync state to {self.state_file}")
        except Exception as e:
            logger.error(f"Failed to save state file: {e}")

    def get_page_id(self: "SyncState", file_path: str) -> Optional[str]:
        """Get the Confluence page ID for a local file.

        Args:
            file_path: Path to the local file

        Returns:
            The page ID if found, None otherwise
        """
        return self._state["file_to_page"].get(str(file_path))

    def get_file_path(self: "SyncState", page_id: str) -> Optional[str]:
        """Get the local file path for a Confluence page ID.

        Args:
            page_id: The Confluence page ID

        Returns:
            The file path if found, None otherwise
        """
        return self._state["page_to_file"].get(page_id)

    def add_mapping(self: "SyncState", file_path: str, page_id: str, sync_time: float) -> None:
        """Add a mapping between a local file and a Confluence page.

        Args:
            file_path: Path to the local file
            page_id: The Confluence page ID
            sync_time: Timestamp of the sync
        """
        file_path = str(file_path)  # Convert Path to string if needed
        self._state["file_to_page"][file_path] = page_id
        self._state["page_to_file"][page_id] = file_path
        self._state["last_sync"][file_path] = sync_time
        self._save_state()
        logger.info(f"Added mapping: {file_path} -> {page_id}")

    def remove_mapping(self: "SyncState", file_path: str) -> Optional[str]:
        """Remove a mapping for a local file.

        Args:
            file_path: Path to the local file

        Returns:
            The removed page ID if found, None otherwise
        """
        file_path = str(file_path)
        page_id = self._state["file_to_page"].pop(file_path, None)
        if page_id:
            self._state["page_to_file"].pop(page_id, None)
            self._state["last_sync"].pop(file_path, None)
            self._state["deleted_pages"].append(page_id)
            self._save_state()
            logger.info(f"Removed mapping: {file_path} -> {page_id}")
        return page_id

    def get_last_sync_time(self: "SyncState", file_path: str) -> Optional[float]:
        """Get the last sync time for a file.

        Args:
            file_path: Path to the local file

        Returns:
            The last sync timestamp if found, None otherwise
        """
        return self._state["last_sync"].get(str(file_path))

    def update_sync_time(self: "SyncState", file_path: str, sync_time: float) -> None:
        """Update the last sync time for a file.

        Args:
            file_path: Path to the local file
            sync_time: New sync timestamp
        """
        file_path = str(file_path)
        self._state["last_sync"][file_path] = sync_time
        self._save_state()
        logger.debug(f"Updated sync time for {file_path}: {sync_time}")

    def is_page_deleted(self: "SyncState", page_id: str) -> bool:
        """Check if a page was previously deleted.

        Args:
            page_id: The Confluence page ID

        Returns:
            True if the page was deleted, False otherwise
        """
        return page_id in self._state["deleted_pages"]

    def get_all_tracked_files(self: "SyncState") -> Set[str]:
        """Get all tracked file paths.

        Returns:
            Set of tracked file paths
        """
        return set(self._state["file_to_page"].keys())

    def get_all_tracked_pages(self: "SyncState") -> Set[str]:
        """Get all tracked page IDs.

        Returns:
            Set of tracked page IDs
        """
        return set(self._state["page_to_file"].keys())

    def clear_deleted_pages(self: "SyncState") -> None:
        """Clear the list of deleted pages."""
        self._state["deleted_pages"] = []
        self._save_state()
        logger.info("Cleared deleted pages history")
