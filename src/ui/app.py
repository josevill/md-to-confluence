import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from textual.app import App, ComposeResult
from textual.containers import Container, Vertical
from textual.reactive import reactive
from textual.widgets import DataTable, Footer, Header, RichLog

from src.sync.engine import SyncEngine
from src.ui.widgets.conflict_widget import ConflictSummaryWidget

"""Main Textual TUI app for md-to-confluence."""


CONFIG_PATH = Path("config.json")


class LogWidget(RichLog):
    """Widget to display real-time logs with scrolling support."""

    def __init__(self: "LogWidget", max_lines: int = 1000, **kwargs: Any) -> None:
        """Initialize the LogWidget."""
        super().__init__(max_lines=max_lines, **kwargs)
        self.session_start_time = None
        self.last_file_size = 0
        self._find_session_start()

    def _find_session_start(self: "LogWidget") -> None:
        """Find the start time of the current session from the log file."""
        log_file = Path("logs/md_to_confluence.log")
        if not log_file.exists():
            return

        try:
            with log_file.open("r", encoding="utf-8") as f:
                for line in f:
                    if "New session started at" in line:
                        timestamp_str = line.split(" - ")[0]
                        self.session_start_time = datetime.strptime(
                            timestamp_str, "%Y-%m-%d %H:%M:%S"
                        )
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Error finding session start time: {e}")

    def _is_current_session(self: "LogWidget", log_line: str) -> bool:
        """Check if a log line belongs to the current session.

        Args:
            log_line: The log line to check

        Returns:
            True if the log line is from the current session, False otherwise
        """
        if not self.session_start_time:
            return True  # If we can't determine session, show all logs

        try:
            # Extract timestamp from the log line
            timestamp_str = log_line.split(" - ")[0]
            log_time = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
            return log_time >= self.session_start_time
        except Exception:
            return True  # If we can't parse the timestamp, include the line

    def add_log(self: "LogWidget", message: str) -> None:
        """Add a log message to the widget."""
        self.write(message)

    async def refresh_logs(self: "LogWidget") -> None:
        """Read new lines from the log file for the current session."""
        log_file = Path("logs/md_to_confluence.log")
        if not log_file.exists():
            return

        try:
            current_size = log_file.stat().st_size
            if current_size == self.last_file_size:
                return  # No new content

            with log_file.open("r", encoding="utf-8") as f:
                # If file is smaller than last size, it was truncated - reload all
                if current_size < self.last_file_size:
                    self.clear()
                    lines = f.readlines()
                else:
                    # Seek to where we left off
                    f.seek(self.last_file_size)
                    lines = f.readlines()

                # Filter and add current session lines
                for line in lines:
                    if self._is_current_session(line.rstrip()):
                        self.write(line.rstrip())

                self.last_file_size = current_size

        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Error refreshing logs: {e}")

    async def on_mount(self: "LogWidget") -> None:
        """Load initial logs when the widget mounts."""
        log_file = Path("logs/md_to_confluence.log")
        if log_file.exists():
            try:
                with log_file.open("r", encoding="utf-8") as f:
                    lines = f.readlines()
                    # Load current session lines
                    for line in lines:
                        if self._is_current_session(line.rstrip()):
                            self.write(line.rstrip())

                    self.last_file_size = log_file.stat().st_size
            except Exception as e:
                logger = logging.getLogger(__name__)
                logger.error(f"Error loading initial logs: {e}")


class MDToConfluenceApp(App):
    """Main Textual TUI app for md-to-confluence."""

    CSS = """
    LogWidget {
        border: solid $primary;
        height: 1fr;
        width: 1fr;
        margin: 1;
    }

    DataTable {
        border: solid $primary;
        height: 1fr;
        width: 1fr;
        margin: 1;
    }

    ConflictSummaryWidget {
        border: solid $warning;
        height: auto;
        width: 1fr;
        margin: 1;
        padding: 1;
    }

    .warning {
        color: $warning;
        text-style: bold;
    }

    .hidden {
        display: none;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("ctrl+c", "clear_logs", "Clear Logs"),
        ("ctrl+s", "scan_conflicts", "Scan Conflicts"),
    ]

    file_statuses: reactive[Dict[str, str]] = reactive({})

    def __init__(self: "MDToConfluenceApp", sync_engine: SyncEngine, **kwargs: Any) -> None:
        """Initialize the MDToConfluenceApp."""
        super().__init__(**kwargs)
        self.sync_engine = sync_engine
        self.state = sync_engine.state
        self.log_widget = LogWidget()
        self.data_table = DataTable()
        self.conflict_widget = ConflictSummaryWidget()
        self.main_container = None
        self.conflict_widget_visible = False

    def compose(self: "MDToConfluenceApp") -> ComposeResult:
        """Compose the app."""
        yield Header(show_clock=True)
        with Container() as container:
            self.main_container = container
            with Vertical():
                yield self.data_table
                yield self.log_widget
        yield Footer()

    async def on_mount(self: "MDToConfluenceApp") -> None:
        """On mount."""
        self.data_table.add_columns("File", "Status")
        await self.refresh_file_statuses()
        await self.refresh_conflict_summary()
        self.set_interval(2, self.refresh_file_statuses)
        self.set_interval(0.5, self.log_widget.refresh_logs)
        self.set_interval(5, self.refresh_conflict_summary)

    async def refresh_file_statuses(self: "MDToConfluenceApp") -> None:
        """Refresh the file statuses."""
        try:
            self.data_table.clear()
            for file_path in sorted(self.state.get_all_tracked_files()):
                # Placeholder, to be implemented with proper statuses in case of
                # Retries, errors, etc :D
                status = "Synced"
                self.data_table.add_row(file_path, status)
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Error refreshing file statuses: {e}")

    async def refresh_conflict_summary(self: "MDToConfluenceApp") -> None:
        """Refresh the conflict summary and show/hide widget as needed."""
        try:
            summary = self.sync_engine.get_conflict_summary()

            # Check if there are any conflicts
            has_conflicts = summary and any(count > 0 for count in summary.values())

            if has_conflicts and not self.conflict_widget_visible:
                # Show conflict widget
                await self._show_conflict_widget()
                self.conflict_widget.update_summary(summary)
            elif not has_conflicts and self.conflict_widget_visible:
                # Hide conflict widget
                await self._hide_conflict_widget()
            elif has_conflicts and self.conflict_widget_visible:
                # Update existing widget
                self.conflict_widget.update_summary(summary)

        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Error refreshing conflict summary: {e}")

    async def _show_conflict_widget(self: "MDToConfluenceApp") -> None:
        """Show the conflict widget by adding it to the layout."""
        if not self.conflict_widget_visible and self.main_container:
            # Insert conflict widget at the top of the vertical layout
            vertical_container = self.main_container.children[0]
            await vertical_container.mount(self.conflict_widget, before=self.data_table)
            self.conflict_widget_visible = True
            logger = logging.getLogger(__name__)
            logger.info("Conflict widget shown due to detected conflicts")

    async def _hide_conflict_widget(self: "MDToConfluenceApp") -> None:
        """Hide the conflict widget by removing it from the layout."""
        if self.conflict_widget_visible:
            await self.conflict_widget.remove()
            self.conflict_widget_visible = False
            logger = logging.getLogger(__name__)
            logger.info("Conflict widget hidden - no conflicts detected")

    def action_clear_logs(self: "MDToConfluenceApp") -> None:
        """Clear the log widget."""
        self.log_widget.clear()

    async def action_scan_conflicts(self: "MDToConfluenceApp") -> None:
        """Scan for conflicts and update the display."""
        try:
            conflicts = self.sync_engine.scan_for_conflicts()
            if conflicts:
                logger = logging.getLogger(__name__)
                logger.warning(f"Found {len(conflicts)} potential conflicts")
                for title, page_id in conflicts.items():
                    logger.warning(f"Conflict: '{title!r}' -> Page ID: {page_id}")
            await self.refresh_conflict_summary()
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Error scanning for conflicts: {e}")


def load_config(path: Path) -> Dict[str, Any]:
    """Load the config from the given path."""
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    """Entrypoint for running the TUI."""
    from src.config import setup_logging
    from src.confluence.client import ConfluenceClient
    from src.confluence.converter import MarkdownConverter

    logger = logging.getLogger(__name__)
    try:
        # Setup logging first
        setup_logging()

        logger.info("Starting MDToConfluenceApp...")
        config = load_config(CONFIG_PATH)

        # Initialize components using singletons
        confluence_client = ConfluenceClient.get_instance(
            base_url=config["confluence_url"],
            token=config["confluence_pat"],
            space_key=config["space_key"],
        )

        sync_engine = SyncEngine.get_instance(
            docs_dir=Path(config["docs_dir"]),
            state_file=Path(config["state_file"]),
            confluence_client=confluence_client,
            converter=MarkdownConverter(),
            debounce_interval=1.0,
        )

        app = MDToConfluenceApp(sync_engine)
        app.run()
    except Exception as e:
        logger.exception(f"Fatal error in MDToConfluenceApp: {e}")
        print(f"Fatal error: {e}. See logs/md_to_confluence.log for details.")
