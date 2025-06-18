"""FileMonitor: Watches the docs/ directory for .md file changes."""

import logging
import threading
import time
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from src.sync.engine import SyncEngine, SyncEvent

# from queue import Queue

logger = logging.getLogger(__name__)


class MarkdownFileEventHandler(FileSystemEventHandler):
    """EventHandler for .md files."""

    def __init__(
        self: "MarkdownFileEventHandler",
        event_callback: Callable[[SyncEvent], None],
        debounce_interval: float = 1.0,
    ) -> None:
        """Initialize the MarkdownFileEventHandler."""
        self.event_callback = event_callback
        self.debounce_interval = debounce_interval
        self._last_event_time = {}
        self._lock = threading.Lock()

    def _should_process(self: "MarkdownFileEventHandler", file_path: Path) -> bool:
        """Check if the file should be processed."""
        if file_path.suffix != ".md":
            return False
        now = time.time()
        with self._lock:
            last_time = self._last_event_time.get(file_path, 0)
            if now - last_time < self.debounce_interval:
                return False
            self._last_event_time[file_path] = now
        return True

    def on_created(self: "MarkdownFileEventHandler", event: FileSystemEvent) -> None:
        """Handle file creation event."""
        if not event.is_directory:
            file_path = Path(event.src_path)
            if self._should_process(file_path):
                self.event_callback(SyncEvent("created", file_path))

    def on_modified(self: "MarkdownFileEventHandler", event: FileSystemEvent) -> None:
        """Handle file modification event."""
        if not event.is_directory:
            file_path = Path(event.src_path)
            if self._should_process(file_path):
                self.event_callback(SyncEvent("modified", file_path))

    def on_deleted(self: "MarkdownFileEventHandler", event: FileSystemEvent) -> None:
        """Handle file deletion event."""
        if not event.is_directory:
            file_path = Path(event.src_path)
            # No debounce for deletes
            self.event_callback(SyncEvent("deleted", file_path))


class FileMonitor:
    """FileMonitor: Watches the docs/ directory for .md file changes."""

    def __init__(
        self: "FileMonitor",
        docs_dir: Path,
        sync_engine: SyncEngine,
        debounce_interval: float = 1.0,
    ) -> None:
        """Initialize the FileMonitor."""
        self.docs_dir = docs_dir
        self.sync_engine = sync_engine
        self.debounce_interval = debounce_interval
        self._observer = Observer()
        self._event_handler = MarkdownFileEventHandler(
            event_callback=self.sync_engine.enqueue_event,
            debounce_interval=self.debounce_interval,
        )
        self._thread = None
        self._stop_event = threading.Event()

    def start(self: "FileMonitor") -> None:
        """Start the FileMonitor."""
        logger.info(f"Starting FileMonitor for {self.docs_dir}")
        docs_dir_str = str(self.docs_dir)
        self._observer.schedule(self._event_handler, docs_dir_str, recursive=True)
        self._observer.start()
        # Initial scan for untracked files
        self.sync_engine.initial_scan()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self: "FileMonitor") -> None:
        """Run the FileMonitor."""
        try:
            while not self._stop_event.is_set():
                time.sleep(0.5)
        except Exception as e:
            logger.error(f"FileMonitor error: {e}")

    def stop(self: "FileMonitor") -> None:
        """Stop the FileMonitor."""
        logger.info("Stopping FileMonitor...")
        self._stop_event.set()
        self._observer.stop()
        self._observer.join()
        if self._thread:
            self._thread.join()
        logger.info("FileMonitor stopped.")
