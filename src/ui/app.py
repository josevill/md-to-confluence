import json
import logging
from pathlib import Path
from typing import Any, Dict

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal
from textual.reactive import reactive
from textual.widgets import DataTable, Footer, Header, Static

from src.config import setup_logging
from src.sync.engine import SyncEngine

# from src.sync.state import SyncState

setup_logging()

"""Main Textual TUI app for md-to-confluence."""


CONFIG_PATH = Path("config.json")


class LogWidget(Static):
    """Widget to display real-time logs."""

    def __init__(self: "LogWidget", max_lines: int = 100, **kwargs: Any) -> None:
        """Initialize the LogWidget."""
        super().__init__(**kwargs)
        self.max_lines = max_lines
        self.lines = []

    def add_log(self: "LogWidget", message: str) -> None:
        """Add a log message to the widget."""
        self.lines.append(message)
        if len(self.lines) > self.max_lines:
            self.lines = self.lines[-self.max_lines :]
        self.update("\n".join(self.lines))


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
        self.set_interval(0.5, self.refresh_logs)

    async def refresh_file_statuses(self: "MDToConfluenceApp") -> None:
        """Refresh the file statuses."""
        self.data_table.clear()
        for file_path in sorted(self.state.get_all_tracked_files()):
            # Placeholder, can be improved with real status
            status = "Synced"
            self.data_table.add_row(file_path, status)

    async def refresh_logs(self: "MDToConfluenceApp") -> None:
        """Read the last N lines from the log file"""
        log_file = Path("logs/md_to_confluence.log")
        if log_file.exists():
            with log_file.open("r", encoding="utf-8") as f:
                lines = f.readlines()[-self.log_widget.max_lines :]
                self.log_widget.lines = [line.rstrip() for line in lines]
                self.log_widget.update("\n".join(self.log_widget.lines))


def load_config(path: Path) -> Dict[str, Any]:
    """Load the config from the given path."""
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    """Entrypoint for running the TUI."""
    logger = logging.getLogger(__name__)
    try:
        logger.info("Starting MDToConfluenceApp...")
        config = load_config(CONFIG_PATH)
        from src.confluence.client import ConfluenceClient
        from src.confluence.converter import MarkdownConverter

        sync_engine = SyncEngine.get_instance(
            docs_dir=Path(config["docs_dir"]),
            state_file=Path(config["state_file"]),
            confluence_client=ConfluenceClient(
                base_url=config["confluence_url"],
                token=config["confluence_pat"],
                space_key=config["space_key"],
            ),
            converter=MarkdownConverter(),
            debounce_interval=1.0,
        )
        app = MDToConfluenceApp(sync_engine)
        app.run()
    except Exception as e:
        logger.exception(f"Fatal error in MDToConfluenceApp: {e}")
        print(f"Fatal error: {e}. See logs/md_to_confluence.log for details.")
