"""Tests for conflict detection and resolution system."""

from pathlib import Path

import pytest

from src.sync.conflict_detector import (
    ConflictDetector,
    ConflictInfo,
    ConflictResolutionStrategy,
    ConflictType,
)


class TestConflictInfo:
    """Test ConflictInfo class."""

    def test_conflict_info_creation(self):
        """Test creating a ConflictInfo instance."""
        local_path = Path("/docs/test.md")
        conflict = ConflictInfo(
            conflict_type=ConflictType.TITLE_CONFLICT,
            local_path=local_path,
            proposed_title="Test Page",
            existing_page_id="12345",
            existing_title="Test Page",
        )

        assert conflict.conflict_type == ConflictType.TITLE_CONFLICT
        assert conflict.local_path == local_path
        assert conflict.proposed_title == "Test Page"
        assert conflict.existing_page_id == "12345"
        assert conflict.existing_title == "Test Page"
        assert conflict.resolution is None
        assert conflict.resolved_title is None

    def test_conflict_info_str(self):
        """Test string representation of ConflictInfo."""
        conflict = ConflictInfo(
            conflict_type=ConflictType.TITLE_CONFLICT,
            local_path=Path("/docs/test.md"),
            proposed_title="Test Page",
            existing_page_id="12345",
        )

        str_repr = str(conflict)
        assert "title_conflict" in str_repr
        assert "test.md" in str_repr
        assert "Test Page" in str_repr
        assert "12345" in str_repr


class TestConflictDetector:
    """Test ConflictDetector class."""

    def test_detector_initialization(self):
        """Test ConflictDetector initialization."""
        detector = ConflictDetector()
        assert detector.default_strategy == ConflictResolutionStrategy.SKIP
        assert detector.detected_conflicts == []
        assert detector.resolution_cache == {}

    def test_detector_custom_strategy(self):
        """Test ConflictDetector with custom default strategy."""
        detector = ConflictDetector(default_strategy=ConflictResolutionStrategy.APPEND_SUFFIX)
        assert detector.default_strategy == ConflictResolutionStrategy.APPEND_SUFFIX

    def test_detect_title_conflicts_no_conflicts(self):
        """Test detecting title conflicts when none exist."""
        detector = ConflictDetector()
        proposed_pages = {Path("/docs/page1.md"): "Page One", Path("/docs/page2.md"): "Page Two"}
        existing_titles = {"Existing Page": "12345", "Another Page": "67890"}

        conflicts = detector.detect_title_conflicts(proposed_pages, existing_titles)

        assert len(conflicts) == 0
        assert len(detector.detected_conflicts) == 0

    def test_detect_title_conflicts_with_conflicts(self):
        """Test detecting title conflicts when they exist."""
        detector = ConflictDetector()
        proposed_pages = {
            Path("/docs/page1.md"): "Page One",
            Path("/docs/page2.md"): "Existing Page",
        }
        existing_titles = {"Existing Page": "12345", "Another Page": "67890"}

        conflicts = detector.detect_title_conflicts(proposed_pages, existing_titles)

        assert len(conflicts) == 1
        assert len(detector.detected_conflicts) == 1

        conflict = conflicts[0]
        assert conflict.conflict_type == ConflictType.TITLE_CONFLICT
        assert conflict.local_path == Path("/docs/page2.md")
        assert conflict.proposed_title == "Existing Page"
        assert conflict.existing_page_id == "12345"

    def test_resolve_conflicts_skip_strategy(self):
        """Test resolving conflicts with SKIP strategy."""
        detector = ConflictDetector(default_strategy=ConflictResolutionStrategy.SKIP)

        conflict = ConflictInfo(
            conflict_type=ConflictType.TITLE_CONFLICT,
            local_path=Path("/docs/test.md"),
            proposed_title="Test Page",
            existing_page_id="12345",
        )

        resolutions = detector.resolve_conflicts([conflict])

        assert len(resolutions) == 0
        assert conflict.resolution == ConflictResolutionStrategy.SKIP
        assert conflict.resolved_title is None

    def test_resolve_conflicts_append_suffix_strategy(self):
        """Test resolving conflicts with APPEND_SUFFIX strategy."""
        detector = ConflictDetector(default_strategy=ConflictResolutionStrategy.APPEND_SUFFIX)

        conflict = ConflictInfo(
            conflict_type=ConflictType.TITLE_CONFLICT,
            local_path=Path("/docs/test.md"),
            proposed_title="Test Page",
            existing_page_id="12345",
        )

        resolutions = detector.resolve_conflicts([conflict])

        assert len(resolutions) == 1
        assert conflict in resolutions
        assert conflict.resolution == ConflictResolutionStrategy.APPEND_SUFFIX
        assert conflict.resolved_title is not None
        assert conflict.resolved_title != "Test Page"
        assert "Test Page" in conflict.resolved_title

    def test_resolve_conflicts_overwrite_strategy(self):
        """Test resolving conflicts with OVERWRITE strategy."""
        detector = ConflictDetector(default_strategy=ConflictResolutionStrategy.OVERWRITE)

        conflict = ConflictInfo(
            conflict_type=ConflictType.TITLE_CONFLICT,
            local_path=Path("/docs/test.md"),
            proposed_title="Test Page",
            existing_page_id="12345",
        )

        resolutions = detector.resolve_conflicts([conflict])

        assert len(resolutions) == 1
        assert conflict in resolutions
        assert conflict.resolution == ConflictResolutionStrategy.OVERWRITE
        assert conflict.resolved_title == "Test Page"

    def test_resolve_conflicts_abort_strategy(self):
        """Test resolving conflicts with ABORT strategy."""
        detector = ConflictDetector(default_strategy=ConflictResolutionStrategy.ABORT)

        conflict = ConflictInfo(
            conflict_type=ConflictType.TITLE_CONFLICT,
            local_path=Path("/docs/test.md"),
            proposed_title="Test Page",
            existing_page_id="12345",
        )

        with pytest.raises(RuntimeError, match="Sync aborted due to conflict"):
            detector.resolve_conflicts([conflict])

    def test_generate_unique_title(self):
        """Test generating unique titles."""
        detector = ConflictDetector()

        unique_title = detector._generate_unique_title("Test Page")

        assert unique_title != "Test Page"
        assert "Test Page" in unique_title
        assert "(" in unique_title and ")" in unique_title

    def test_get_conflict_summary_empty(self):
        """Test getting conflict summary when no conflicts exist."""
        detector = ConflictDetector()

        summary = detector.get_conflict_summary()

        assert summary == {}

    def test_get_conflict_summary_with_conflicts(self):
        """Test getting conflict summary with conflicts."""
        detector = ConflictDetector()

        # Add some conflicts
        conflicts = [
            ConflictInfo(
                conflict_type=ConflictType.TITLE_CONFLICT,
                local_path=Path("/docs/test1.md"),
                proposed_title="Test Page 1",
                existing_page_id="12345",
            ),
            ConflictInfo(
                conflict_type=ConflictType.TITLE_CONFLICT,
                local_path=Path("/docs/test2.md"),
                proposed_title="Test Page 2",
                existing_page_id="67890",
            ),
        ]

        detector.detected_conflicts.extend(conflicts)
        summary = detector.get_conflict_summary()

        assert summary == {"title_conflict": 2}

    def test_clear_conflicts(self):
        """Test clearing all conflicts."""
        detector = ConflictDetector()

        # Add some conflicts
        conflict = ConflictInfo(
            conflict_type=ConflictType.TITLE_CONFLICT,
            local_path=Path("/docs/test.md"),
            proposed_title="Test Page",
            existing_page_id="12345",
        )
        detector.detected_conflicts.append(conflict)
        detector.resolution_cache["test"] = ConflictResolutionStrategy.SKIP

        detector.clear_conflicts()

        assert detector.detected_conflicts == []
        assert detector.resolution_cache == {}

    def test_has_unresolved_conflicts_none(self):
        """Test checking for unresolved conflicts when none exist."""
        detector = ConflictDetector()

        assert not detector.has_unresolved_conflicts()

    def test_has_unresolved_conflicts_all_resolved(self):
        """Test checking for unresolved conflicts when all are resolved."""
        detector = ConflictDetector()

        conflict = ConflictInfo(
            conflict_type=ConflictType.TITLE_CONFLICT,
            local_path=Path("/docs/test.md"),
            proposed_title="Test Page",
            existing_page_id="12345",
        )
        conflict.resolution = ConflictResolutionStrategy.SKIP
        detector.detected_conflicts.append(conflict)

        assert not detector.has_unresolved_conflicts()

    def test_has_unresolved_conflicts_some_unresolved(self):
        """Test checking for unresolved conflicts when some exist."""
        detector = ConflictDetector()

        conflict = ConflictInfo(
            conflict_type=ConflictType.TITLE_CONFLICT,
            local_path=Path("/docs/test.md"),
            proposed_title="Test Page",
            existing_page_id="12345",
        )
        # No resolution set
        detector.detected_conflicts.append(conflict)

        assert detector.has_unresolved_conflicts()


class TestConflictDetectorIntegration:
    """Integration tests for ConflictDetector."""

    def test_full_workflow(self):
        """Test complete conflict detection and resolution workflow."""
        detector = ConflictDetector(default_strategy=ConflictResolutionStrategy.APPEND_SUFFIX)

        # Simulate proposed pages and existing titles
        proposed_pages = {
            Path("/docs/page1.md"): "New Page",
            Path("/docs/page2.md"): "Existing Page",
            Path("/docs/page3.md"): "Another Existing Page",
        }
        existing_titles = {
            "Existing Page": "12345",
            "Another Existing Page": "67890",
            "Different Page": "11111",
        }

        # Detect conflicts
        conflicts = detector.detect_title_conflicts(proposed_pages, existing_titles)

        assert len(conflicts) == 2
        assert len(detector.detected_conflicts) == 2

        # Resolve conflicts
        resolutions = detector.resolve_conflicts(conflicts)

        assert len(resolutions) == 2

        # Check that all conflicts are resolved
        assert not detector.has_unresolved_conflicts()

        # Check summary
        summary = detector.get_conflict_summary()
        assert summary == {"title_conflict": 2}

        # Verify resolutions
        for conflict in conflicts:
            assert conflict.resolution == ConflictResolutionStrategy.APPEND_SUFFIX
            assert conflict.resolved_title is not None
            assert conflict.resolved_title != conflict.proposed_title
