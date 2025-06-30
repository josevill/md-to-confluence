"""Widget for displaying conflict notifications and resolution options."""

import logging
from typing import Dict, List

from textual.containers import Container, Horizontal
from textual.reactive import reactive
from textual.widgets import Button, DataTable, Label, Static

from src.sync.conflict_detector import ConflictInfo, ConflictResolutionStrategy

logger = logging.getLogger(__name__)


class ConflictNotificationWidget(Static):
    """Widget to display conflict notifications."""

    conflicts_count = reactive(0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.conflicts: List[ConflictInfo] = []

    def compose(self):
        """Compose the conflict notification widget."""
        with Container(id="conflict-container"):
            yield Label("Conflicts Detected", id="conflict-title")
            yield Label("No conflicts detected", id="conflict-status")
            yield DataTable(id="conflict-table")

    def update_conflicts(self, conflicts: List[ConflictInfo]) -> None:
        """Update the displayed conflicts.

        Args:
            conflicts: List of detected conflicts
        """
        self.conflicts = conflicts
        self.conflicts_count = len(conflicts)

        # Update status label
        status_label = self.query_one("#conflict-status", Label)
        if conflicts:
            status_label.update(f"{len(conflicts)} conflicts detected")
            status_label.add_class("warning")
        else:
            status_label.update("No conflicts detected")
            status_label.remove_class("warning")

        # Update conflicts table
        table = self.query_one("#conflict-table", DataTable)
        table.clear()

        if conflicts:
            # Add table headers
            table.add_columns("File Path", "Proposed Title", "Existing Page ID", "Resolution")

            # Add conflict rows
            for conflict in conflicts:
                resolution = conflict.resolution.value if conflict.resolution else "Pending"
                table.add_row(
                    str(conflict.local_path.name),
                    conflict.proposed_title,
                    conflict.existing_page_id or "N/A",
                    resolution,
                )


class ConflictSummaryWidget(Static):
    """Widget to display conflict summary statistics."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.summary: Dict[str, int] = {}

    def compose(self):
        """Compose the conflict summary widget."""
        with Container(id="summary-container"):
            yield Label("Conflict Summary", id="summary-title")
            yield Label("No conflicts", id="summary-content")

    def update_summary(self, summary: Dict[str, int]) -> None:
        """Update the conflict summary.

        Args:
            summary: Dict with conflict type counts
        """
        self.summary = summary

        content_label = self.query_one("#summary-content", Label)

        if not summary:
            content_label.update("No conflicts")
            content_label.remove_class("warning")
        else:
            summary_text = []
            try:
                total_conflicts = sum(v for v in summary.values() if isinstance(v, (int, float)))
                summary_text.append(f"Total: {total_conflicts}")
            except (TypeError, ValueError):
                pass

            for conflict_type, count in summary.items():
                summary_text.append(f"{conflict_type.replace('_', ' ').title()}: {count}")

            content_label.update(" | ".join(summary_text))
            content_label.add_class("warning")


class ConflictResolutionWidget(Static):
    """Widget for interactive conflict resolution."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.current_conflict: ConflictInfo = None

    def compose(self):
        """Compose the conflict resolution widget."""
        with Container(id="resolution-container"):
            yield Label("Conflict Resolution", id="resolution-title")
            yield Label("No active conflict", id="resolution-details")
            with Horizontal(id="resolution-buttons"):
                yield Button("Skip", id="btn-skip", variant="default")
                yield Button("Append Suffix", id="btn-suffix", variant="primary")
                yield Button("Overwrite", id="btn-overwrite", variant="warning")

    def show_conflict(self, conflict: ConflictInfo) -> None:
        """Show a conflict for resolution.

        Args:
            conflict: The conflict to resolve
        """
        self.current_conflict = conflict

        details_label = self.query_one("#resolution-details", Label)
        details_text = (
            f"File: {conflict.local_path.name!r}\n"
            f"Proposed: '{conflict.proposed_title!r}'\n"
            f"Conflicts with existing page ID: {conflict.existing_page_id!r}"
        )
        details_label.update(details_text)

        # Enable resolution buttons
        for button_id in ["btn-skip", "btn-suffix", "btn-overwrite"]:
            button = self.query_one(f"#{button_id}", Button)
            button.disabled = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle resolution button presses."""
        if not self.current_conflict:
            return

        strategy_map = {
            "btn-skip": ConflictResolutionStrategy.SKIP,
            "btn-suffix": ConflictResolutionStrategy.APPEND_SUFFIX,
            "btn-overwrite": ConflictResolutionStrategy.OVERWRITE,
        }

        strategy = strategy_map.get(event.button.id)
        if strategy:
            self.current_conflict.resolution = strategy
            logger.info(f"User resolved conflict with strategy: {strategy.value}")

            # Disable buttons after resolution
            for button_id in ["btn-skip", "btn-suffix", "btn-overwrite"]:
                button = self.query_one(f"#{button_id}", Button)
                button.disabled = True

            # Update details
            details_label = self.query_one("#resolution-details", Label)
            details_label.update(f"Resolved with: {strategy.value}")

            # Clear current conflict
            self.current_conflict = None
