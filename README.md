# MD-to-Confluence

A Python application that automatically syncs Markdown files to Confluence pages with real-time monitoring and a Terminal User Interface (TUI).

## Features

- **Real-time sync** - Monitors markdown files and automatically updates Confluence pages
- **File hierarchy mapping** - Maintains folder structure as page hierarchy in Confluence
- **Image handling** - Uploads local images as Confluence attachments
- **Terminal UI** - Live monitoring with file status and log viewing
- **Robust error handling** - Retry logic, rate limiting, and graceful failure recovery
- **Secure token management** - Integration with 1Password CLI for secure token storage

## Installation

### Prerequisites

- Python 3.10 or higher
- [1Password CLI](https://1password.com/downloads/command-line/) (for secure token storage)
- Access to a Confluence instance with API permissions

### Install Dependencies

- Clone the repository:

```bash
git clone <repository-url>
cd md-to-confluence
```

- Install using uv (recommended) or pip:

```bash
# Using uv (faster)
uv install

# Or using pip
pip install -e .
```

### Set Up 1Password CLI

- Install the 1Password CLI from https://1password.com/downloads/command-line/
- Sign in to your 1Password account:

```bash
op signin
```

- Create a new item in 1Password to store your Confluence Personal Access Token:

```bash
op item create --title="ConfluencePAT" --category="api credential" notesPlain="your-confluence-token-here"
```

### Generate Confluence Personal Access Token

1. Go to your Confluence settings
2. Navigate to Personal Access Tokens
3. Create a new token with appropriate permissions
4. Store the token in 1Password as described above

## Configuration

### Create Configuration File

Create a `config.json` file in the project root:

```json
{
  "confluence": {
    "base_url": "https://your-domain.atlassian.net",
    "space_key": "YOUR_SPACE_KEY",
    "token_1password_item": "ConfluencePAT",
    "retry_max_attempts": 3,
    "retry_backoff_factor": 1.0
  },
  "sync": {
    "docs_dir": "docs",
    "initial_scan": true,
    "debounce_delay": 2.0
  },
  "ui": {
    "refresh_interval": 1.0,
    "log_lines": 100
  }
}
```

### Configuration Options

#### Confluence Section

- `base_url` - Your Confluence instance URL
- `space_key` - The Confluence space key where pages will be created
- `token_1password_item` - Name of the 1Password item containing your PAT
- `retry_max_attempts` - Number of retry attempts for failed API calls
- `retry_backoff_factor` - Backoff multiplier for retry delays

#### Sync Section

- `docs_dir` - Directory to monitor for markdown files
- `initial_scan` - Whether to scan existing files on startup
- `debounce_delay` - Delay in seconds before processing file changes

#### UI Section

- `refresh_interval` - UI refresh rate in seconds
- `log_lines` - Number of log lines to display in the UI

## Usage

### Command Line Interface

Run the application with the TUI:

```bash
python main.py
```

### TUI Controls

- `q` or `Ctrl+C` - Quit the application
- `c` - Clear log display
- `Tab` - Navigate between UI sections

### File Organization

The application maps your local file structure to Confluence page hierarchy:

```markdown
docs/
├── index.md              → Root page in space
├── getting-started.md    → Child page
└── guides/
    ├── user-guide.md     → Parent page in "guides" section
    └── admin-guide.md    → Child page under "guides"
```

### Markdown Features

Supported markdown features:

- Headers (become page sections)
- Lists (bulleted and numbered)
- Tables
- Code blocks (converted to Confluence macros)
- Images (uploaded as attachments)
- Links (internal and external)
- Bold/italic text
- Blockquotes
- Horizontal rules

### Image Handling

Local images are automatically:

1. Detected in markdown content
2. Uploaded as Confluence attachments
3. Replaced with proper Confluence image macros
4. Cached to avoid re-uploading unchanged images

Supported formats: PNG, JPG, JPEG, GIF, SVG, WEBP

## Troubleshooting

### Common Issues

**"Configuration file not found"**

- Ensure `config.json` exists in the project root
- Check file permissions

**"1Password CLI not found"**

- Install 1Password CLI: https://1password.com/downloads/command-line/
- Ensure `op` command is in your PATH

**"Failed to authenticate with Confluence"**

- Verify your Personal Access Token is correct
- Check that the token has appropriate permissions
- Ensure the base_url and space_key are correct

**"Permission denied" errors**

- Check file system permissions for the docs directory
- Ensure write access to the logs directory

### Debug Mode

Enable debug logging by setting the log level in `config.py`:

```python
setup_logging(level=logging.DEBUG)
```

### Log Files

Application logs are stored in `logs/md_to_confluence.log` with automatic rotation.

## Development

### Running Tests

```bash
# Run all tests
python -m pytest

# Run specific test file
python -m pytest tests/test_confluence_client.py

# Run with coverage
python -m pytest --cov=src
```

### Code Quality

The project uses:

- Black for code formatting
- Flake8 for linting (100 character line limit)
- Pre-commit hooks for quality checks

```bash
# Format code
black src/ tests/

# Run linter
flake8 src/ tests/

# Install pre-commit hooks
pre-commit install
```

## Architecture

The application consists of several key components:

- **Configuration** (`src/config.py`) - Configuration management and validation
- **Confluence Client** (`src/confluence/client.py`) - API interactions with rate limiting
- **Markdown Converter** (`src/confluence/converter.py`) - Markdown to Confluence format conversion
- **File Monitor** (`src/monitor/file_watcher.py`) - Real-time file system monitoring
- **Sync Engine** (`src/sync/engine.py`) - Orchestrates the sync process
- **State Management** (`src/sync/state.py`) - Tracks file-to-page mappings
- **TUI** (`src/ui/app.py`) - Terminal user interface

## Security

- Personal Access Tokens are stored securely in 1Password
- Input validation prevents injection attacks
- File path sanitization prevents directory traversal
- Secure HTTPS communication with Confluence API

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Support

For issues and questions:

1. Check the troubleshooting section above
2. Review existing issues in the repository
3. Create a new issue with detailed information about your problem
