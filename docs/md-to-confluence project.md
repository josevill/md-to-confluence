# Design Doc: Confluence Markdown Sync (md-to-confluence)

## Overview

CMSync will be a terminal application designed to synchronize a local directory of Markdown files with a Confluence space. The primary goal is to enable a "docs-as-code" workflow, allowing users to write and manage documentation in their preferred local editor and have it automatically published to Confluence, preserving the local folder structure as a page hierarchy.

The application will feature a Text User Interface (TUI) built with Textual for configuration, real-time status monitoring, and user interaction. File system changes will be detected by Watchdog, and all interactions with Confluence will be handled via its REST API using a Python wrapper like atlassian-python-api.

## Core Requirements

### Functional Requirements

**File Monitoring**: The application must monitor a user-specified local directory and all its subdirectories for changes to Markdown (.md) files. This includes file creation, modification, and deletion.

**Content Conversion**: Markdown files must be converted to Confluence's XHTML Storage Format before being uploaded. This includes handling standard Markdown syntax, code blocks, and images.

Confluence Page Management:

    Create: A new local Markdown file will create a corresponding new page in Confluence.

    Update: Modifying and saving a local Markdown file will update the content of the corresponding Confluence page.

    Delete: Deleting a local Markdown file will trigger the deletion of the corresponding Confluence page. This action must be configurable and require user confirmation.

    Hierarchy Sync: The local directory structure must be replicated in Confluence. A local sub-directory will correspond to a parent page in Confluence, and files within that directory will become its child pages.

Authentication: The application must authenticate with the Confluence API using a Personal Access Token (PAT), which will be retrieved securely.

Text User Interface (TUI):
Display a list of all monitored Markdown files.
Show the status of each file (e.g., Synced, Modified, Uploading, Error).

Provide a view for application logs and status messages.

Allow the user to configure essential settings:

Local directory path to monitor.
Confluence instance URL.
Confluence Space Key.
ID of the root Confluence page under which the hierarchy will be created.
Provide controls to start and stop the synchronization service.

### Non-Functional Requirements

Security: The Confluence PAT must be handled securely, loaded at runtime, and never hardcoded in source files or logs. Your get_confluence_pat_1password utility is a perfect fit for this.

Performance: The TUI must remain responsive at all times. API calls and file processing must be handled in background workers to avoid blocking the user interface.

Reliability: The application must gracefully handle common issues such as network errors, invalid API responses, and API rate limiting.

Usability: The TUI should be intuitive, providing clear feedback to the user about ongoing processes and errors.

Maintainability: The codebase will be organized into logical, decoupled components (UI, file monitoring, API client, sync logic) to facilitate future development and maintenance.

## Architecture and Design

The application will be composed of several distinct components that work together, orchestrated by a central SyncEngine.

### Core Components

#### TUI (Textual App): The user-facing component

**Responsibilities**: Render all UI elements (widgets like DataTable, Header, Footer, Log), capture user input for configuration, and display the real-time status of files and the sync process.

**Implementation**: It will be the main entry point of the application, built by subclassing textual.app.App. It will use background workers (@work) for any long-running tasks to keep the UI from freezing.

#### File Monitor (Watchdog): The file system event listener

**Responsibilities**: Monitor the target directory recursively for file events (on_created, on_modified, on_deleted). It will run in a dedicated background thread and place detected events onto a thread-safe queue for the SyncEngine to process.

**Implementation**: An Observer thread will be scheduled with a custom FileSystemEventHandler subclass.

#### Confluence Client (atlassian-python-api): A wrapper for API interactions

**Responsibilities**: Handle all communication with the Confluence REST API. This includes authentication with the PAT, creating, reading, updating, and deleting pages and attachments.

**Implementation**: A dedicated class that encapsulates an instance of atlassian.Confluence. It will be configured with the URL and PAT. Based on your script, the PAT will be passed using the token parameter, which is suitable for Confluence Data Center/Server instances. If targeting Confluence Cloud, the library typically expects the API token to be passed as the password parameter along with a username (email). The client should be designed to accommodate this if needed.

#### Markdown Processor: The content conversion utility

**Responsibilities**: Convert Markdown text into the Confluence XHTML Storage Format. This is a critical step, as Confluence does not render raw Markdown via the API; it requires a specific XHTML structure.

**Implementation**: We will leverage a specialized library like markdown-to-confluence  or md2cf , which are designed to handle this conversion, including syntax for code blocks, tables, and other elements.

#### Sync Engine: The central coordinator

**Responsibilities**:

- Orchestrate the entire sync process
- Process events from the FileMonitor's queue.
- Maintain a state mapping between local file paths and their corresponding Confluence page IDs.
- Determine the correct parent-child page relationships based on the file system structure.
- Instruct the MarkdownProcessor and ConfluenceClient to perform their tasks.
- Update the application's shared state, which the TUI will reflect.

### State Management: The Sync Map

A crucial design element is a persistent local cache (e.g., a sync_map.json file or a small SQLite database) that maps local file paths to Confluence page IDs.

    { "path/to/local/doc.md": "1234567" }

This map is essential for performance and correctness:

**Updates**: To update a page, we need its ID. Searching by title is slow and unreliable. The map provides an instant lookup.
Deletes: To delete a page, we need its ID.

**Renames/Moves**: A file move can be detected as a delete and a create. The map helps identify this as a rename, allowing the tool to potentially move the page in Confluence rather than re-creating it.

**Offline Changes**: When the app starts, it will scan the local directory and use this map to determine which files are new, which have been deleted, and which need checking for modifications since the last run.

## Key Considerations and Technical Deep Dive

### Confluence API and Content

**Authentication with PAT**: Your current script uses token=CONFLUENCE_PAT. This is the correct approach for Data Center/Server instances. The design will proceed with this, but we must be aware that for Cloud, the library often requires username and password (where the PAT is the password). The ConfluenceClient should make this configurable.

**Markdown to XHTML**: This is the most complex part of the content handling. Simple Markdown-to-HTML libraries are insufficient. We must use a tool that specifically targets the Confluence Storage Format to ensure elements like code blocks (<ac:structured-macro ac:name="code">...) render correctly. The library markdown-to-confluence appears to be a strong candidate.

**Page Hierarchy**: To create a page as a child of another, the create_page API call requires the parent_id.

The SyncEngine's logic will be:

    For a file docs/project-a/feature.md, determine its parent directory (docs/project-a).
    Look up the page ID for the parent directory in the sync_map.

    If the parent page doesn't exist, create it first, then create the child page.

    The root directory will be parented to the user-configured root page ID.

**API Rate Limiting**: For Cloud instances, this is a major consideration. The application must handle 429 Too Many Requests responses by implementing an exponential backoff-and-retry strategy. The atlassian-python-api library's RestClient has parameters like backoff_and_retry and retry_with_header that should be utilized.

### File Monitoring and Sync Logic

**Initial Scan**: On startup, the application must perform a full scan of the monitored directory to build an initial state and compare it against the sync_map to find changes made while the app was closed.

**Event Debouncing**: Text editors often fire multiple modification events when saving a file. The SyncEngine should implement a debouncing mechanism (e.g., waiting a short period after an event before processing it) to prevent redundant uploads for a single user action.

**Deletion Safety**: Deleting a Confluence page is irreversible. The feature should be disabled by default. When enabled, the TUI must present a clear confirmation dialog before proceeding with the deletion.

### TUI Implementation

**Asynchronous Operations**: All interactions with the SyncEngine (which will make network calls) must be done asynchronously from the TUI's perspective using Textual's @work decorator. This ensures the UI remains fluid and responsive.

**Reactive UI**: The list of files and their statuses should be stored in a reactive variable on the main App class. A watch method will monitor this variable for changes and automatically update the DataTable widget, simplifying UI updates.

## Phased Implementation Plan

### Phase 1: Core Command-Line Logic (No TUI)

- Develop the ConfluenceClient class, perfecting PAT authentication and page creation/updating. ⚙️
- Integrate the chosen Markdown-to-XHTML library and test conversions. ⚙️
- Build the SyncEngine with the sync_map logic for syncing a single file. ⚙️
- Create a simple command-line script to test syncing an entire directory once. ⚙️

### Phase 2: File Monitoring Integration

- Implement the FileMonitor using Watchdog. ⚙️
- Integrate it with the SyncEngine using a queue to process file events in real-time. ⚙️

### Phase 3: TUI Development

- Build the main Textual application layout. ⚙️
- Create a DataTable to display file statuses, driven by the SyncEngine's state. ⚙️
- Implement the configuration screen to manage settings. ⚙️
- Connect UI controls (e.g., "Start/Stop" buttons) to the SyncEngine. ⚙️

### Phase 4: Refinement and Hardening

- Implement robust error handling and display clear error messages in the TUI log. ⚙️
- Add and test the rate-limiting backoff strategy. ⚙️
- Implement the safe-delete functionality with user confirmation. ⚙️
- Write documentation and package the application for distribution. ⚙️
