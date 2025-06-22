import json
import logging
import shutil
from pathlib import Path
from typing import Optional, Set

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

    def _get_default_state(self: "SyncState") -> dict:
        """Get the default empty state structure.

        Returns:
            Default state dictionary
        """
        return {
            "file_to_page": {},
            "page_to_file": {},
            "last_sync": {},
            "deleted_pages": [],
        }

    def _validate_state(self: "SyncState", state: dict) -> bool:
        """Validate that the state has the required structure.

        Args:
            state: State dictionary to validate

        Returns:
            True if valid, False otherwise
        """
        required_keys = {"file_to_page", "page_to_file", "last_sync", "deleted_pages"}

        if not isinstance(state, dict):
            return False

        if not required_keys.issubset(state.keys()):
            logger.warning(
                f"State missing required keys. Expected: {required_keys}, "
                f"Found: {set(state.keys())}"
            )
            return False

        # Validate data types
        if not isinstance(state["file_to_page"], dict):
            return False
        if not isinstance(state["page_to_file"], dict):
            return False
        if not isinstance(state["last_sync"], dict):
            return False
        if not isinstance(state["deleted_pages"], list):
            return False

        return True

    def _load_state(self: "SyncState") -> dict:
        """Load the state from the JSON file.

        Returns:
            The loaded state or an empty state if file doesn't exist or is corrupted
        """
        if not self.state_file.exists():
            logger.info(f"State file {self.state_file} doesn't exist, creating new state")
            return self._get_default_state()

        try:
            if self.state_file.stat().st_size == 0:
                logger.warning(f"State file {self.state_file} is empty, using default state")
                return self._get_default_state()

            with self.state_file.open("r", encoding="utf-8") as f:
                content = f.read().strip()

                if not content:
                    logger.warning(
                        f"State file {self.state_file} has no content, using default state"
                    )
                    return self._get_default_state()

                state = json.loads(content)

                if not self._validate_state(state):
                    logger.error(
                        f"State file {self.state_file} has invalid structure, using default state"
                    )
                    self._backup_corrupted_file()
                    return self._get_default_state()

                logger.info(f"Successfully loaded sync state from {self.state_file}")
                return state

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON in state file {self.state_file}: {e}")
            self._backup_corrupted_file()
            return self._get_default_state()
        except PermissionError as e:
            logger.error(f"Permission denied accessing state file {self.state_file}: {e}")
            return self._get_default_state()
        except Exception as e:
            logger.error(f"Unexpected error loading state file {self.state_file}: {e}")
            self._backup_corrupted_file()
            return self._get_default_state()

    def _backup_corrupted_file(self: "SyncState") -> None:
        """Backup a corrupted state file for investigation."""
        try:
            backup_path = self.state_file.with_suffix(".corrupted.bak")
            if self.state_file.exists():

                shutil.copy2(self.state_file, backup_path)
                logger.info(f"Backed up corrupted state file to {backup_path}")
        except PermissionError as e:
            logger.warning(f"Permission denied creating backup of corrupted state file: {e}")
        except Exception as e:
            logger.error(f"Failed to backup corrupted state file: {e}")

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
