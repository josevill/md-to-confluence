"""SyncEngine: Orchestrates file events and synchronizes with Confluence."""

import logging
import threading
import time
from pathlib import Path
from queue import Empty, Queue
from typing import Any, Dict, Optional

from src.confluence.client import ConfluenceClient
from src.confluence.converter import MarkdownConverter
from src.sync.state import SyncState

logger = logging.getLogger(__name__)


class SyncEvent:
    """Event for file synchronization."""

    def __init__(self, event_type: str, file_path: Path):
        """Initialize the SyncEvent."""
        self.event_type = event_type  # 'created', 'modified', 'deleted'
        self.file_path = file_path
        self.timestamp = time.time()

    def __repr__(self):
        """Return a string representation of the SyncEvent."""
        return f"<SyncEvent {self.event_type} {self.file_path}>"


class SyncEngine:
    """Orchestrates file events and synchronizes with Confluence."""

    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls: type["SyncEngine"], *args: Any, **kwargs: Any) -> "SyncEngine":
        """Get the instance of the SyncEngine."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(*args, **kwargs)
            return cls._instance

    def __init__(
        self: "SyncEngine",
        docs_dir: Path,
        state_file: Path,
        confluence_client: ConfluenceClient,
        converter: MarkdownConverter,
        debounce_interval: float = 1.0,
    ) -> None:
        """Initialize the SyncEngine."""
        if SyncEngine._instance is not None:
            raise Exception("SyncEngine is a singleton. Use get_instance().")
        self.docs_dir = docs_dir
        self.state = SyncState(state_file)
        self.confluence = confluence_client
        self.converter = converter
        self.debounce_interval = debounce_interval
        self.event_queue = Queue()
        self._stop_event = threading.Event()
        self._worker_thread = threading.Thread(target=self._worker, daemon=True)
        self._worker_thread.start()
        logger.info("SyncEngine started.")

    def enqueue_event(self: "SyncEngine", event: SyncEvent) -> None:
        """Send event to the event queue."""
        logger.debug(f"Enqueuing event: {event}")
        self.event_queue.put(event)

    def _worker(self: "SyncEngine") -> None:
        """Worker thread for processing events."""
        last_event: Dict[Path, SyncEvent] = {}
        last_processed: Dict[Path, float] = {}
        while not self._stop_event.is_set():
            try:
                event: SyncEvent = self.event_queue.get(timeout=0.2)
                now = time.time()
                # Debounce: Only process if enough time has passed since last
                # event for this file
                last = last_processed.get(event.file_path, 0)
                if now - last < self.debounce_interval:
                    # Replace with the latest event for this file
                    last_event[event.file_path] = event
                    continue
                # Process event
                self._process_event(event)
                last_processed[event.file_path] = now
                # If there was a debounced event
                # process it after debounce interval
                if event.file_path in last_event:
                    time.sleep(self.debounce_interval)
                    self._process_event(last_event.pop(event.file_path))
                    last_processed[event.file_path] = time.time()
            except Empty:
                continue
            except Exception as e:
                logger.error(f"Error in SyncEngine worker: {e}")

    def _process_event(self: "SyncEngine", event: SyncEvent) -> None:
        """Process the event."""
        logger.info(f"Processing event: {event}")
        file_path = event.file_path
        if event.event_type == "created" or event.event_type == "modified":
            if not file_path.exists():
                logger.warning(f"File not found: {file_path}")
                return
            # Convert markdown to Confluence storage format
            content = file_path.read_text(encoding="utf-8")
            storage_format = self.converter.convert(content, base_path=file_path.parent)
            page_id = self.state.get_page_id(str(file_path))
            title = file_path.stem.replace("_", " ").replace("-", " ").title()
            parent_id = self._get_parent_page_id(file_path)
            if page_id:
                # Update existing page
                self.confluence.update_page(
                    page_id=page_id,
                    title=title,
                    body=storage_format,
                )
                logger.info(f"Updated page for {file_path}")
            else:
                # Create new page
                page = self.confluence.create_page(
                    title=title,
                    body=storage_format,
                    parent_id=parent_id,
                )
                page_id = page["id"]
                logger.info(f"Created page for {file_path} with ID {page_id}")
            self.state.add_mapping(str(file_path), page_id, time.time())
        elif event.event_type == "deleted":
            page_id = self.state.get_page_id(str(file_path))
            if page_id:
                self.confluence.delete_page(page_id)
                self.state.remove_mapping(str(file_path))
                logger.info(f"Deleted page for {file_path}")
            else:
                logger.warning(f"No page mapping found for deleted file: {file_path}")

    def _get_parent_page_id(self: "SyncEngine", file_path: Path) -> Optional[str]:
        # Determine parent page ID based on directory structure
        rel_path = file_path.relative_to(self.docs_dir)
        if rel_path.parent == Path("."):
            # Top-level file, parent is the root page (should be configured)
            # For now, return None (should be set in config)
            return None
        parent_dir = self.docs_dir / rel_path.parent
        return self.state.get_page_id(str(parent_dir))

    def initial_scan(self: "SyncEngine") -> None:
        """
        Scan docs_dir for .md files
        and enqueue 'created' events for untracked files.
        """
        for file_path in self.docs_dir.rglob("*.md"):
            if not self.state.get_page_id(str(file_path)):
                self.enqueue_event(SyncEvent("created", file_path))

    def stop(self: "SyncEngine") -> None:
        self._stop_event.set()
        self._worker_thread.join()
        logger.info("SyncEngine stopped.")
