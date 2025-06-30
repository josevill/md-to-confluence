"""Conflict detection and resolution for Confluence page synchronization."""

import logging
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ConflictResolutionStrategy(Enum):
    """Strategies for resolving title conflicts."""

    SKIP = "skip"  # Skip creating the conflicting page
    APPEND_SUFFIX = "append_suffix"  # Add suffix like " (2)" to make unique
    OVERWRITE = "overwrite"  # Replace the existing page
    INTERACTIVE = "interactive"  # Ask user for resolution
    ABORT = "abort"  # Stop sync process entirely


class ConflictType(Enum):
    """Types of conflicts that can occur."""

    TITLE_CONFLICT = "title_conflict"  # Page title already exists
    HIERARCHY_CONFLICT = "hierarchy_conflict"  # Parent-child relationship conflict


class ConflictInfo:
    """Information about a detected conflict."""

    def __init__(
        self,
        conflict_type: ConflictType,
        local_path: Path,
        proposed_title: str,
        existing_page_id: Optional[str] = None,
        existing_title: Optional[str] = None,
        parent_path: Optional[Path] = None,
    ):
        self.conflict_type = conflict_type
        self.local_path = local_path
        self.proposed_title = proposed_title
        self.existing_page_id = existing_page_id
        self.existing_title = existing_title
        self.parent_path = parent_path
        self.resolution: Optional[ConflictResolutionStrategy] = None
        self.resolved_title: Optional[str] = None

    def __str__(self) -> str:
        return (
            f"ConflictInfo(type={self.conflict_type.value!r}, "
            f"path={self.local_path!r}, "
            f"proposed='{self.proposed_title!r}', "
            f"existing_id={self.existing_page_id!r})"
        )


class ConflictDetector:
    """Detects and manages conflicts during synchronization."""

    def __init__(
        self, default_strategy: ConflictResolutionStrategy = ConflictResolutionStrategy.SKIP
    ):
        self.default_strategy = default_strategy
        self.detected_conflicts: List[ConflictInfo] = []
        self.resolution_cache: Dict[str, ConflictResolutionStrategy] = {}

    def detect_title_conflicts(
        self, proposed_pages: Dict[Path, str], existing_titles: Dict[str, str]
    ) -> List[ConflictInfo]:
        """Detect title conflicts between proposed pages and existing pages.

        Args:
            proposed_pages: Dict mapping local paths to proposed page titles
            existing_titles: Dict mapping existing page titles to page IDs

        Returns:
            List of detected conflicts
        """
        conflicts = []

        for local_path, proposed_title in proposed_pages.items():
            if proposed_title in existing_titles:
                conflict = ConflictInfo(
                    conflict_type=ConflictType.TITLE_CONFLICT,
                    local_path=local_path,
                    proposed_title=proposed_title,
                    existing_page_id=existing_titles[proposed_title],
                    existing_title=proposed_title,
                )
                conflicts.append(conflict)
                logger.warning(f"Title conflict detected: {conflict}")

        self.detected_conflicts.extend(conflicts)
        return conflicts

    def resolve_conflicts(
        self, conflicts: List[ConflictInfo], strategy: Optional[ConflictResolutionStrategy] = None
    ) -> Dict[ConflictInfo, str]:
        """Resolve conflicts using the specified strategy.

        Args:
            conflicts: List of conflicts to resolve
            strategy: Resolution strategy to use (defaults to instance default)

        Returns:
            Dict mapping conflicts to their resolved titles (empty if skipped)
        """
        strategy = strategy or self.default_strategy
        resolutions = {}

        for conflict in conflicts:
            resolved_title = self._resolve_single_conflict(conflict, strategy)
            if resolved_title:
                resolutions[conflict] = resolved_title
                conflict.resolution = strategy
                conflict.resolved_title = resolved_title
                logger.info(
                    f"Resolved conflict for '{conflict.proposed_title!r}' -> '{resolved_title!r}'"
                )
            else:
                conflict.resolution = ConflictResolutionStrategy.SKIP
                logger.info(f"Skipped conflicting page: '{conflict.proposed_title!r}'")

        return resolutions

    def _resolve_single_conflict(
        self, conflict: ConflictInfo, strategy: ConflictResolutionStrategy
    ) -> Optional[str]:
        """Resolve a single conflict using the specified strategy.

        Args:
            conflict: The conflict to resolve
            strategy: Resolution strategy to use

        Returns:
            Resolved title or None if skipped
        """
        if strategy == ConflictResolutionStrategy.SKIP:
            return None

        elif strategy == ConflictResolutionStrategy.APPEND_SUFFIX:
            return self._generate_unique_title(conflict.proposed_title)

        elif strategy == ConflictResolutionStrategy.OVERWRITE:
            # Return original title - caller will handle overwriting
            return conflict.proposed_title

        elif strategy == ConflictResolutionStrategy.INTERACTIVE:
            # For now, fall back to append suffix
            # TODO: Implement interactive resolution in UI
            logger.warning("Interactive resolution not yet implemented, using append_suffix")
            return self._generate_unique_title(conflict.proposed_title)

        elif strategy == ConflictResolutionStrategy.ABORT:
            raise RuntimeError(f"Sync aborted due to conflict: {conflict}")

        else:
            logger.error(f"Unknown resolution strategy: {strategy}")
            return None

    def _generate_unique_title(self, base_title: str, max_attempts: int = 100) -> str:
        """Generate a unique title by appending a suffix.

        Args:
            base_title: Base title to make unique
            max_attempts: Maximum number of suffix attempts

        Returns:
            Unique title with suffix
        """
        # For now, just append a timestamp-based suffix
        # In a full implementation, this would check against existing titles
        import time

        suffix = int(time.time()) % 10000
        return f"{base_title} ({suffix})"

    def get_conflict_summary(self) -> Dict[str, int]:
        """Get a summary of detected conflicts.

        Returns:
            Dict with conflict type counts
        """
        summary = {}
        for conflict in self.detected_conflicts:
            conflict_type = conflict.conflict_type.value
            summary[conflict_type] = summary.get(conflict_type, 0) + 1

        return summary

    def clear_conflicts(self) -> None:
        """Clear all detected conflicts."""
        self.detected_conflicts.clear()
        self.resolution_cache.clear()

    def has_unresolved_conflicts(self) -> bool:
        """Check if there are any unresolved conflicts.

        Returns:
            True if there are conflicts without resolutions
        """
        return any(conflict.resolution is None for conflict in self.detected_conflicts)
