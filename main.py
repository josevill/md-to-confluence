"""Main entry point for the md-to-confluence application."""

import json
import logging
from pathlib import Path

from src.config import get_confluence_pat_1password, setup_logging
from src.confluence.client import ConfluenceClient
from src.confluence.converter import MarkdownConverter
from src.monitor.file_watcher import FileMonitor
from src.sync.engine import SyncEngine
from src.ui.app import MDToConfluenceApp

# Initialize logging
setup_logging()
logger = logging.getLogger(__name__)


def load_config(path: Path) -> dict:
    """Load configuration from JSON file."""
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    """Main entry point for the application."""
    try:
        logger.info("Starting md-to-confluence...")

        config = load_config(Path("config.json"))
        pat_token = get_confluence_pat_1password()

        confluence_client = ConfluenceClient.get_instance(
            base_url=config["confluence_url"],
            token=pat_token,
            space_key=config["space_key"],
        )

        markdown_converter = MarkdownConverter()

        sync_engine = SyncEngine.get_instance(
            docs_dir=Path(config["docs_dir"]),
            state_file=Path(config["state_file"]),
            confluence_client=confluence_client,
            converter=markdown_converter,
            debounce_interval=1.0,
        )

        file_monitor = FileMonitor(
            docs_dir=Path(config["docs_dir"]),
            sync_engine=sync_engine,
            debounce_interval=1.0,
        )
        file_monitor.start()

        app = MDToConfluenceApp(sync_engine)
        app.run()

    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        raise
    finally:
        # Cleanup
        if "file_monitor" in locals():
            file_monitor.stop()
        if "sync_engine" in locals():
            sync_engine.stop()
        logger.info("Application shutdown complete.")


if __name__ == "__main__":
    main()
