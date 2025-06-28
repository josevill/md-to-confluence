"""FileMonitor: Watches the docs/ directory for .md file changes and folder operations."""

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
    """EventHandler for .md files and folders."""

    def __init__(
        self: "MarkdownFileEventHandler",
        docs_dir: Path,
        event_callback: Callable[[SyncEvent], None],
        debounce_interval: float = 1.0,
    ) -> None:
        """Initialize the MarkdownFileEventHandler."""
        self.docs_dir = docs_dir.resolve()
        self.event_callback = event_callback
        self.debounce_interval = debounce_interval
        self._last_event_time = {}
        self._lock = threading.Lock()

    def _should_process_file(self: "MarkdownFileEventHandler", file_path: Path) -> bool:
        """Check if the file should be processed."""
        try:
            # Check if file is under docs_dir
            file_path.relative_to(self.docs_dir)
        except ValueError:
            logger.warning(f"File '{file_path!r}' is not in directory '{self.docs_dir!r}'")
            return False

        if file_path.suffix != ".md":
            return False

        now = time.time()
        with self._lock:
            last_time = self._last_event_time.get(file_path, 0)
            if now - last_time < self.debounce_interval:
                return False
            self._last_event_time[file_path] = now
        return True

    def _should_process_folder(self: "MarkdownFileEventHandler", folder_path: Path) -> bool:
        """Check if the folder should be processed."""
        try:
            folder_path.relative_to(self.docs_dir)
        except ValueError:
            logger.warning(f"Folder '{folder_path!r}' is not in directory '{self.docs_dir!r}'")
            return False

        if any(part.startswith(".") for part in folder_path.parts):
            return False

        skip_folders = {"__pycache__", ".git", ".vscode", ".idea", "node_modules", ".pytest_cache"}
        if any(part in skip_folders for part in folder_path.parts):
            return False

        now = time.time()
        with self._lock:
            last_time = self._last_event_time.get(folder_path, 0)
            if now - last_time < self.debounce_interval:
                return False
            self._last_event_time[folder_path] = now
        return True

    def on_created(self: "MarkdownFileEventHandler", event: FileSystemEvent) -> None:
        """Handle file/folder creation event."""
        path = Path(event.src_path).resolve()

        if event.is_directory:
            if self._should_process_folder(path):
                logger.debug(f"Folder created: {path}")
                self.event_callback(SyncEvent("folder_created", path))
        else:
            if self._should_process_file(path):
                logger.debug(f"File created: {path}")
                self.event_callback(SyncEvent("created", path))

    def on_modified(self: "MarkdownFileEventHandler", event: FileSystemEvent) -> None:
        """Handle file modification event."""
        if not event.is_directory:
            file_path = Path(event.src_path).resolve()
            if self._should_process_file(file_path):
                logger.debug(f"File modified: {file_path}")
                self.event_callback(SyncEvent("modified", file_path))

    def on_deleted(self: "MarkdownFileEventHandler", event: FileSystemEvent) -> None:
        """Handle file/folder deletion event."""
        path = Path(event.src_path).resolve()

        if event.is_directory:
            try:
                path.relative_to(self.docs_dir)
                logger.debug(f"Folder deleted: {path}")
                self.event_callback(SyncEvent("folder_deleted", path))
            except ValueError:
                logger.warning(f"Ignoring delete event for folder outside docs directory: {path}")
        else:
            # No debounce for deletes, but still check if it's under docs_dir
            try:
                path.relative_to(self.docs_dir)
                logger.debug(f"File deleted: {path}")
                self.event_callback(SyncEvent("deleted", path))
            except ValueError:
                logger.warning(f"Ignoring delete event for file outside docs directory: {path}")

    def on_moved(self: "MarkdownFileEventHandler", event: FileSystemEvent) -> None:
        """Handle file/folder move/rename event."""
        old_path = Path(event.src_path).resolve()
        new_path = Path(event.dest_path).resolve()

        if event.is_directory:
            try:
                old_path.relative_to(self.docs_dir)
                new_path.relative_to(self.docs_dir)
                logger.debug(f"Folder moved: {old_path} -> {new_path}")
                # Treat as delete old + create new for simplicity
                self.event_callback(SyncEvent("folder_deleted", old_path))
                if self._should_process_folder(new_path):
                    self.event_callback(SyncEvent("folder_created", new_path))
            except ValueError:
                logger.warning(
                    f"Ignoring move event for folder outside docs directory: {old_path} -> {new_path}"
                )
        else:
            try:
                old_path.relative_to(self.docs_dir)
                new_path.relative_to(self.docs_dir)
                if old_path.suffix == ".md" or new_path.suffix == ".md":
                    logger.debug(f"File moved: {old_path} -> {new_path}")
                    # Treat as delete old + create new for simplicity
                    self.event_callback(SyncEvent("deleted", old_path))
                    if self._should_process_file(new_path):
                        self.event_callback(SyncEvent("created", new_path))
            except ValueError:
                logger.warning(
                    f"Ignoring move event for file outside docs directory: {old_path} -> {new_path}"
                )


class FileMonitor:
    """FileMonitor: Watches the docs/ directory for .md file changes."""

    def __init__(
        self: "FileMonitor",
        docs_dir: Path,
        sync_engine: SyncEngine,
        debounce_interval: float = 1.0,
    ) -> None:
        """Initialize the FileMonitor."""
        self.docs_dir = docs_dir.resolve()
        self.sync_engine = sync_engine
        self.debounce_interval = debounce_interval
        self._observer = Observer()
        self._event_handler = MarkdownFileEventHandler(
            docs_dir=self.docs_dir,
            event_callback=self.sync_engine.enqueue_event,
            debounce_interval=self.debounce_interval,
        )
        self._thread = None
        self._stop_event = threading.Event()

    def start(self: "FileMonitor") -> None:
        """Start the FileMonitor."""
        logger.info(f"Starting FileMonitor for {self.docs_dir}")
        self._observer.schedule(self._event_handler, str(self.docs_dir), recursive=True)
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
