import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal
from textual.reactive import reactive
from textual.widgets import DataTable, Footer, Header, Static

from src.sync.engine import SyncEngine

"""Main Textual TUI app for md-to-confluence."""


CONFIG_PATH = Path("config.json")


class LogWidget(Static):
    """Widget to display real-time logs."""

    def __init__(self: "LogWidget", max_lines: int = 100, **kwargs: Any) -> None:
        """Initialize the LogWidget."""
        super().__init__(**kwargs)
        self.max_lines = max_lines
        self.lines = []
        self.session_start_time = None
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
        self.lines.append(message)
        if len(self.lines) > self.max_lines:
            self.lines = self.lines[-self.max_lines :]
        self.update("\n".join(self.lines))

    async def refresh_logs(self: "LogWidget") -> None:
        """Read the last N lines from the log file for the current session."""
        log_file = Path("logs/md_to_confluence.log")
        if log_file.exists():
            try:
                with log_file.open("r", encoding="utf-8") as f:
                    # Read all lines but only keep current session
                    all_lines = [
                        line.rstrip() for line in f.readlines() if self._is_current_session(line)
                    ]
                    # Keep only the last max_lines
                    self.lines = all_lines[-self.max_lines :]
                    self.update("\n".join(self.lines))
            except Exception as e:
                logger = logging.getLogger(__name__)
                logger.error(f"Error refreshing logs: {e}")


class MDToConfluenceApp(App):
    """Main Textual TUI app for md-to-confluence."""

    CSS_PATH = None
    BINDINGS = [
        ("q", "quit", "Quit"),
    ]

    file_statuses: reactive[Dict[str, str]] = reactive({})

    def __init__(self: "MDToConfluenceApp", sync_engine: SyncEngine, **kwargs: Any) -> None:
        """Initialize the MDToConfluenceApp."""
        super().__init__(**kwargs)
        self.sync_engine = sync_engine
        self.state = sync_engine.state
        self.log_widget = LogWidget()
        self.data_table = DataTable()

    def compose(self: "MDToConfluenceApp") -> ComposeResult:
        """Compose the app."""
        yield Header(show_clock=True)
        with Container():
            with Horizontal():
                yield self.data_table
                yield self.log_widget
        yield Footer()

    async def on_mount(self: "MDToConfluenceApp") -> None:
        """On mount."""
        self.data_table.add_columns("File", "Status")
        await self.refresh_file_statuses()
        self.set_interval(2, self.refresh_file_statuses)
        self.set_interval(0.5, self.log_widget.refresh_logs)

    async def refresh_file_statuses(self: "MDToConfluenceApp") -> None:
        """Refresh the file statuses."""
        self.data_table.clear()
        for file_path in sorted(self.state.get_all_tracked_files()):
            # Placeholder, can be improved with real status
            status = "Synced"
            self.data_table.add_row(file_path, status)


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
