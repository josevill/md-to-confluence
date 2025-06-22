# MD-to-Confluence Implementation Tasks

## Project Setup

- [x] Initialize Python project with pyproject.toml
- [x] Set up basic dependencies
- [x] Create project directory structure
  - [x] Create src/ directory with module structure
  - [x] Set up tests/ directory
  - [x] Create initial `__init__.py` files
- [x] Set up development environment
  - [x] Configure pre-commit hooks
    - [x] Configure Black formatter
    - [x] Configure flake8 with extended line length (88)
    - [x] Add type annotation checks
  - [x] Set up pytest configuration
  - [x] Add .gitignore rules
  - [x] Configure logging with rotation and session tracking

## Phase 1: Core Components

### Configuration Module (src/config.py)

- [x] Implement configuration management
  - [x] Set up logging configuration with rotation
  - [x] Add 1Password CLI integration for PAT tokens
  - [x] Configure project paths and constants
  - [x] Add session tracking in logs
  - [x] Add type annotations

### Confluence Client (src/confluence/client.py)

- [x] Implement ConfluenceClient class
  - [x] Add PAT authentication
  - [x] Implement page CRUD operations
  - [x] Add rate limiting logic
  - [x] Implement retry mechanism with exponential backoff
  - [x] Add comprehensive error handling
  - [x] Add type annotations
  - [x] Implement singleton pattern
  - [x] __FIXED__: Modified create_page and update_page to use direct HTTP requests instead of atlassian library methods for better Confluence Server compatibility
- [x] __NEW__: Implement attachment upload functionality
  - [x] Add upload_attachment method for file uploads
  - [x] Handle existing attachment deletion to prevent duplicates
  - [x] Support for binary file uploads with proper headers
  - [x] Error handling for attachment operations
  - [x] Integration with Confluence attachment API
- [ ] Write tests for ConfluenceClient
  - [ ] Authentication tests
  - [ ] CRUD operation tests
  - [ ] Rate limiting tests
  - [ ] Error handling tests
  - [ ] Singleton pattern tests
  - [ ] Attachment upload tests

### Markdown Converter (src/confluence/converter.py)

- [x] Implement markdown to XHTML conversion
  - [x] Basic Markdown syntax conversion with multiple extensions
  - [x] Code block handling with Confluence macros
  - [x] Table conversion
  - [x] Image handling with path resolution
  - [x] Link processing
  - [x] Admonition support (info, note, warning macros)
  - [x] Add type annotations
  - [x] Fix f-string formatting
  - [x] __FIXED__: Escape Confluence macro syntax in documentation text to prevent malformed XHTML
- [x] __NEW__: Implement advanced image handling with Confluence attachments
  - [x] Extract local images from markdown content
  - [x] Support for multiple image formats (.png, .jpg, .jpeg, .gif, .svg, .webp)
  - [x] Create placeholders for local images during conversion
  - [x] Generate Confluence attachment macros for uploaded images
  - [x] Implement fallback handling for failed image uploads
  - [x] Add two-step conversion process (extract images, then finalize content)
- [x] Add debugging utilities
  - [x] Created debug_converter.py for troubleshooting
  - [x] XHTML validation checking
  - [x] Common issue detection
- [ ] Write converter tests
  - [ ] Basic syntax tests
  - [ ] Complex element tests
  - [ ] Edge case handling
  - [ ] Confluence macro tests
  - [ ] Image handling tests

### State Management (src/sync/state.py)

- [x] Implement state persistence
  - [x] Create JSON storage
  - [x] Implement path-to-ID mapping with bidirectional lookup
  - [x] Add state recovery logic
  - [x] Add type annotations
  - [x] __FIXED__: Improved error handling for corrupted/empty state files
    - [x] Fixed infinite recursion bug when state file is corrupted
    - [x] Added validation for state structure
    - [x] Added backup mechanism for corrupted files
    - [x] Added comprehensive error handling for empty files, invalid JSON, and permission errors
- [x] Write state management tests
  - [x] Error handling tests (empty files, corrupted JSON, invalid structure)
  - [ ] Storage tests
  - [ ] Recovery tests
  - [ ] Edge case handling

## Phase 2: File Monitoring

### File Watcher (src/monitor/file_watcher.py)

- [x] Implement FileMonitor class
  - [x] Set up Watchdog integration
  - [x] Add event debouncing with threading locks
  - [x] Implement directory scanning
  - [x] Add change detection logic for .md files only
  - [x] Add path validation (files must be under docs_dir)
  - [x] Add type annotations
- [ ] Write file monitoring tests
  - [ ] Event handling tests
  - [ ] Debouncing tests
  - [ ] Scanner tests
  - [ ] Path validation tests

## Phase 3: Sync Engine

### Core Sync Logic (src/sync/engine.py)

- [x] Implement SyncEngine class
  - [x] Create event queue processing with worker thread
  - [x] Add hierarchy management with parent page detection
  - [x] Implement comprehensive error handling
  - [x] Add recovery mechanisms
  - [x] Add debouncing logic
  - [x] Implement initial scan for untracked files
  - [x] Add singleton pattern
  - [x] Add type annotations
- [x] __NEW__: Integrate image upload workflow
  - [x] Modified _process_event to use two-step conversion process
  - [x] Added _upload_images method for batch image uploading
  - [x] Implemented fallback handling for failed image uploads
  - [x] Added final content update with image macros
  - [x] Enhanced error handling for image operations
- [ ] Write sync engine tests
  - [ ] Queue processing tests
  - [ ] Hierarchy tests
  - [ ] Error recovery tests
  - [ ] Debouncing tests
  - [ ] Image upload integration tests

## Phase 4: TUI Development

### Basic UI Structure (src/ui/app.py)

- [x] Create main application layout
  - [x] Implement base app class with Textual
  - [x] Add screen management with header/footer
  - [x] Create navigation logic
  - [x] Add real-time log viewing with session filtering
  - [x] Add file status table with live updates
  - [x] Add keyboard shortcuts (quit, clear logs)
  - [x] Add type annotations
- [ ] Write UI tests
  - [ ] Layout tests
  - [ ] Navigation tests
  - [ ] Log widget tests

### UI Components (src/ui/widgets/)

- [x] Implement status indicators
  - [x] Create file status table with DataTable
  - [x] Add real-time log viewer with LogWidget
  - [x] Implement session-based log filtering
  - [x] Add automatic refresh intervals
- [ ] Create configuration screens
  - [ ] Settings management UI
  - [ ] Confirmation dialogs
  - [ ] Connection testing interface
- [ ] Write widget tests
  - [ ] Component tests
  - [ ] Integration tests

## Phase 5: Integration and Polish

### Integration

- [x] Connect all components
  - [x] Wire up UI to sync engine
  - [x] Connect file monitor to sync engine
  - [x] Integrate state management across all components
  - [x] Create main entry point with proper initialization
- [x] Add comprehensive logging
  - [x] Set up log levels with rotating file handler
  - [x] Add contextual logging throughout application
  - [x] Implement log rotation (10MB, 5 backups)
  - [x] Add session markers in logs

### Configuration

- [x] Implement configuration system
  - [x] JSON-based configuration (config.json)
  - [x] 1Password integration for secure token storage
  - [x] Environment-specific settings
- [ ] Improve configuration management
  - [ ] Add configuration validation
  - [ ] Add default configuration creation
  - [ ] Add environment variable support
  - [ ] Add configuration file documentation

### Documentation

- [x] Create project documentation
  - [x] Project overview document exists
- [ ] Write user documentation
  - [ ] Installation guide
  - [ ] Configuration guide
  - [ ] Usage examples
  - [ ] Troubleshooting guide
- [ ] Create developer documentation
  - [ ] Architecture overview
  - [ ] API documentation
  - [ ] Contributing guide
  - [ ] Code organization guide

### Testing and Refinement

- [x] __CRITICAL - COMPLETED__: Write comprehensive test suite for Phase 1 & 2
  - [x] __COMPLETED__: ConfluenceClient tests (tests/test_confluence_client.py)
    - [x] Singleton pattern implementation and thread safety
    - [x] Authentication and initialization
    - [x] CRUD operations (create, read, update, delete pages)
    - [x] Rate limiting and retry logic with exponential backoff
    - [x] Error handling for various HTTP errors
    - [x] Attachment upload functionality
    - [x] Direct HTTP request methods
    - [x] Thread safety and concurrent request handling
    - [x] Full workflow integration tests
  - [x] __COMPLETED__: MarkdownConverter tests (tests/test_markdown_converter.py)
    - [x] Basic markdown to XHTML conversion (headings, lists, emphasis, etc.)
    - [x] Code block extraction and restoration with Confluence macros
    - [x] Table conversion
    - [x] Image handling (local image extraction, supported formats, attachment macros)
    - [x] Admonition processing (info, note, warning blocks)
    - [x] Confluence syntax escaping
    - [x] Two-step image conversion workflow
    - [x] Edge cases (empty content, special characters)
    - [x] Full conversion workflows
  - [x] __COMPLETED__: SyncState tests (tests/test_sync_state.py)
    - [x] State file initialization and loading
    - [x] JSON validation and error handling
    - [x] Corrupted file backup mechanisms
    - [x] File-to-page mapping operations
    - [x] Sync time tracking
    - [x] Deleted pages management
    - [x] Concurrent access safety
    - [x] State persistence across instances
    - [x] Permission error handling
  - [x] __COMPLETED__: FileMonitor tests (tests/test_file_watcher.py)
    - [x] MarkdownFileEventHandler for file system events
    - [x] Debouncing logic to prevent event spam
    - [x] Path validation (files must be under docs directory)
    - [x] Event handling for create, modify, delete operations
    - [x] Thread safety of debounce mechanism
    - [x] FileMonitor integration with sync engine
    - [x] Observer pattern implementation
    - [x] Start/stop lifecycle management
  - [x] __COMPLETED__: SyncEngine tests (tests/test_sync_engine.py)
    - [x] Singleton pattern implementation and thread safety
    - [x] Event processing (create, modify, delete operations)
    - [x] Queue processing with worker thread
    - [x] Debouncing logic to prevent event spam
    - [x] Image upload integration workflow
    - [x] Error handling and recovery mechanisms
    - [x] Hierarchy management with parent page detection
    - [x] Path validation and relative path handling
    - [x] Initial scan functionality for untracked files
    - [x] Thread safety and concurrent event processing
    - [x] Worker thread lifecycle management
  - [x] __COMPLETED__: UI Application tests (tests/test_ui_app.py)
    - [x] LogWidget functionality (session filtering, log refresh, mounting)
    - [x] MDToConfluenceApp initialization and configuration
    - [x] App navigation and key bindings
    - [x] File status table management
    - [x] Error handling in UI components
    - [x] Configuration loading and validation
    - [x] Async component testing with pytest-asyncio
    - [x] UI integration with sync engine
    - [x] CSS styling verification
  - [x] __COMPLETED__: Integration tests (tests/test_integration.py)
    - [x] Component integration between all major modules
    - [x] End-to-end workflow tests (file lifecycle, hierarchical sync)
    - [x] System-level integration scenarios
    - [x] Error recovery and resilience testing
    - [x] Performance testing with multiple files
    - [x] State persistence across application restarts
    - [x] Real file system operations with FileMonitor
    - [x] Confluence API mocking for integration scenarios
- [ ] Optimize performance
  - [ ] Profile application
  - [ ] Optimize bottlenecks
  - [ ] Memory usage analysis
  - [ ] Concurrent processing improvements
- [ ] Implement user feedback
  - [ ] Add user-friendly error reporting
  - [ ] Improve error messages
  - [ ] Add progress indicators
  - [ ] Add confirmation prompts for destructive operations

### Security and Reliability

- [ ] __IMPORTANT__: Security improvements
  - [ ] Token validation and secure storage
  - [ ] Input sanitization for markdown content
  - [ ] Path traversal protection
  - [ ] Secure API communication validation
- [ ] __IMPORTANT__: Reliability improvements
  - [ ] Connection retry logic
  - [ ] State backup and recovery
  - [ ] Graceful degradation on errors
  - [ ] Data consistency checks

### New Features (Additional)

- [ ] __ENHANCEMENT__: Advanced sync features
  - [ ] Selective sync (ignore patterns)
  - [ ] Dry-run mode for testing
  - [ ] Conflict resolution strategies
  - [ ] Batch operations for large file sets
  - [ ] Delta sync (only changed content)
- [ ] __ENHANCEMENT__: UI improvements
  - [ ] Configuration management screen
  - [ ] Progress tracking for long operations
  - [ ] File diff viewer
  - [ ] Manual sync triggers
  - [ ] Connection status indicator
- [ ] __ENHANCEMENT__: Monitoring and reporting
  - [ ] Sync statistics
  - [ ] Performance metrics
  - [ ] Health checks
  - [ ] Export/import sync state

## Packaging and Distribution

- [ ] Package for distribution
  - [ ] Create setup scripts
  - [ ] Configure package metadata
  - [ ] Add release scripts
  - [ ] Create distribution packages (wheel, source)
- [ ] Set up CI/CD
  - [ ] Configure GitHub Actions
  - [ ] Add automated testing pipeline
  - [ ] Set up automated releases
  - [ ] Add code quality checks
- [ ] Create installation methods
  - [ ] pip installable package
  - [ ] Docker container
  - [ ] Standalone executables
  - [ ] Installation documentation

## Current Priorities

### Immediate (High Priority)

1. __Write comprehensive tests__ - The application is functionally complete but lacks test coverage
2. __Add configuration validation__ - Ensure robust configuration handling
3. __Security review__ - Validate token handling and input sanitization
4. __User documentation__ - Create installation and usage guides

### Short-term (Medium Priority)

1. __Enhanced error reporting__ - User-friendly error messages and recovery
2. __Performance optimization__ - Profile and optimize bottlenecks
3. __Advanced sync features__ - Selective sync, dry-run mode
4. __UI enhancements__ - Configuration screens, progress indicators

### Long-term (Lower Priority)

1. __Packaging and distribution__ - Make the tool easily installable
2. __CI/CD pipeline__ - Automated testing and releases
3. __Monitoring features__ - Statistics and health checks
4. __Alternative installation methods__ - Docker, executables
