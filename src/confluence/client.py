"""Confluence API client for interacting with Confluence Server/Data Center."""

import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from atlassian import Confluence
from requests.exceptions import HTTPError, RequestException

logger = logging.getLogger(__name__)


class ConfluenceClient:
    """Client for interacting with Confluence API."""

    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(
        cls: type["ConfluenceClient"],
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        space_key: Optional[str] = None,
        retry_max_attempts: int = 3,
        retry_backoff_factor: float = 1.0,
    ) -> "ConfluenceClient":
        """Get the singleton instance of ConfluenceClient.

        Args:
            base_url: Base URL of the Confluence instance
            token: Personal Access Token for authentication
            space_key: Key of the Confluence space to work with
            retry_max_attempts: Maximum retry attempts for failed requests
            retry_backoff_factor: Backoff factor for retry delays

        Returns:
            The singleton instance of ConfluenceClient

        Raises:
            ValueError: If required parameters are missing on first initialization
        """
        with cls._lock:
            if cls._instance is None:
                if not all([base_url, token, space_key]):
                    raise ValueError(
                        "base_url, token, and space_key are required for first initialization"
                    )
                cls._instance = cls(
                    base_url=base_url,
                    token=token,
                    space_key=space_key,
                    retry_max_attempts=retry_max_attempts,
                    retry_backoff_factor=retry_backoff_factor,
                )
            return cls._instance

    def __init__(
        self,
        base_url: str,
        token: str,
        space_key: str,
        retry_max_attempts: int = 3,
        retry_backoff_factor: float = 1.0,
    ) -> None:
        """Initialize the Confluence client.

        Args:
            base_url: Base URL of the Confluence instance
            token: Personal Access Token for authentication
            space_key: Key of the Confluence space to work with
            retry_max_attempts: Maximum retry attempts for failed requests
            retry_backoff_factor: Backoff factor for retry delays

        Raises:
            Exception: If trying to create a new instance directly
        """
        if ConfluenceClient._instance is not None:
            raise Exception("ConfluenceClient is a singleton. Use get_instance()")

        self.base_url = base_url.rstrip("/")
        self.space_key = space_key
        self.token = token
        self.retry_max_attempts = retry_max_attempts
        self.retry_backoff_factor = retry_backoff_factor

        # Initialize the Confluence client for read operations only
        self.client = Confluence(
            url=self.base_url,
            token=token,
            verify_ssl=True,
        )

        # Alias for backwards compatibility with tests
        self._confluence = self.client

        # Set up headers for direct HTTP requests
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        logger.info(f"Initialized Confluence client for space: {space_key}")

    def _retry_with_backoff(
        self: "ConfluenceClient", operation: callable, *args: Any, **kwargs: Any
    ) -> Any:
        """Retry an operation with exponential backoff.

        Args:
            operation: The function to retry
            *args: Positional arguments for the operation
            **kwargs: Keyword arguments for the operation

        Returns:
            Result of the operation

        Raises:
            Exception: If all retries are exhausted
        """
        for attempt in range(self.retry_max_attempts):
            try:
                return operation(*args, **kwargs)
            except HTTPError as e:
                # Ensure response attribute exists before accessing status_code
                if (
                    hasattr(e, "response")
                    and e.response is not None
                    and e.response.status_code == 429
                ):  # Too Many Requests
                    wait_time = self.retry_backoff_factor * (2**attempt)
                    logger.warning(f"Rate limit hit, waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                    continue
                # For non-rate-limiting HTTPErrors, only retry if we have attempts left
                if attempt < self.retry_max_attempts - 1:
                    wait_time = self.retry_backoff_factor * (2**attempt)
                    logger.warning(f"HTTP error occurred, waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                    continue
                raise
            except RequestException:
                if attempt < self.retry_max_attempts - 1:
                    wait_time = self.retry_backoff_factor * (2**attempt)
                    logger.warning(f"Request failed, waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                    continue
                raise

        raise Exception(f"Failed after {self.retry_max_attempts} retries")

    def _make_direct_request(
        self, method: str, endpoint: str, data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Make a direct HTTP request to Confluence API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint (relative to base_url)
            data: Optional JSON data for the request

        Returns:
            JSON response from the API

        Raises:
            HTTPError: If the request fails
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        logger.debug(f"Making {method} request to {url}")

        response = requests.request(
            method=method, url=url, headers=self.headers, json=data, verify=True
        )

        if not response.ok:
            logger.error(f"Request failed: {response.status_code} - {response.text}")
            response.raise_for_status()

        return response.json()

    def create_page(
        self: "ConfluenceClient",
        title: str,
        body: str,
        parent_id: Optional[str] = None,
        representation: str = "storage",
    ) -> Dict[str, Any]:
        """Create a new page in Confluence using direct HTTP request.

        Args:
            title: Title of the page
            body: Content of the page in storage format
            parent_id: ID of the parent page (optional)
            representation: Content representation (default: storage)

        Returns:
            Dict containing the created page information
        """
        logger.info(f"Creating page: {title}")

        create_params = {
            "type": "page",
            "title": title,
            "space": {"key": self.space_key},
            "body": {
                "storage": {
                    "value": body,
                    "representation": representation,
                }
            },
        }

        if parent_id:
            create_params["ancestors"] = [{"id": parent_id}]

        result = self._retry_with_backoff(
            self._make_direct_request, "POST", "rest/api/content/", create_params
        )

        # After successful page creation, get and log all pages in the space
        try:
            all_pages = self.list_all_space_pages()
            page_titles = [page.get("title", "Unknown") for page in all_pages]
            logger.info(
                f"Pages in space {self.space_key!r} after creating {title!r}: {page_titles}"
            )
        except Exception as e:
            logger.warning(f"Failed to retrieve pages list after creating '{title!r}': {e}")

        return result

    def update_page(
        self: "ConfluenceClient",
        page_id: str,
        title: str,
        body: str,
        representation: str = "storage",
    ) -> Dict[str, Any]:
        """Update an existing page in Confluence using direct HTTP request.

        Args:
            page_id: ID of the page to update
            title: New title of the page
            body: New content of the page
            representation: Content representation (default: storage)

        Returns:
            Dict containing the updated page information
        """
        logger.info(f"Updating page: {title} (ID: {page_id})")

        # Get current page info to get the version number
        curr_page = self._retry_with_backoff(self.client.get_page_by_id, page_id)
        version = curr_page["version"]["number"]

        update_params = {
            "id": page_id,
            "type": "page",
            "title": title,
            "space": {"key": self.space_key},
            "body": {
                "storage": {
                    "value": body,
                    "representation": representation,
                }
            },
            "version": {"number": version + 1},
        }

        return self._retry_with_backoff(
            self._make_direct_request, "PUT", f"rest/api/content/{page_id}", update_params
        )

    def delete_page(self: "ConfluenceClient", page_id: str) -> None:
        """Delete a page from Confluence.

        Args:
            page_id: ID of the page to delete
        """
        logger.info(f"Deleting page with ID: {page_id}")
        self._retry_with_backoff(self.client.remove_page, page_id=page_id)

    def get_page(self: "ConfluenceClient", page_id: str) -> Dict[str, Any]:
        """Get a page from Confluence by its ID.

        Args:
            page_id: ID of the page to retrieve

        Returns:
            Dict containing the page information
        """
        logger.info(f"Retrieving page with ID: {page_id}")
        return self._retry_with_backoff(self.client.get_page_by_id, page_id=page_id)

    def get_page_by_title(self: "ConfluenceClient", title: str) -> Optional[Dict[str, Any]]:
        """Get a page from Confluence by its title.

        Args:
            title: Title of the page to retrieve

        Returns:
            Dict containing the page information or None if not found
        """
        logger.info(f"Retrieving page by title: {title}")
        pages = self._retry_with_backoff(
            self.client.get_page_by_title,
            space=self.space_key,
            title=title,
        )
        # Handle both list and dict return formats
        if isinstance(pages, list):
            return pages[0] if pages else None
        elif isinstance(pages, dict) and "results" in pages:
            results = pages["results"]
            return results[0] if results else None
        else:
            return pages if pages else None

    def get_child_pages(self: "ConfluenceClient", parent_id: str) -> list[Dict[str, Any]]:
        """Get all child pages of a given parent page.

        Args:
            parent_id: ID of the parent page

        Returns:
            List of child pages
        """
        logger.info(f"Retrieving child pages for parent ID: {parent_id}")
        return self._retry_with_backoff(
            self.client.get_page_child_by_type, page_id=parent_id, type="page"
        )

    def get_space_pages(
        self: "ConfluenceClient", limit: int = 50, start: int = 0, expand: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get all pages within the Confluence space.

        This method is used to check if pages have been uploaded/updated appropriately
        within the session's Confluence Space.

        Args:
            limit: Maximum number of pages to retrieve per request (default: 50)
            start: Starting index for pagination (default: 0)
            expand: Additional properties to expand in the response (optional)

        Returns:
            Dict containing the pages information and pagination details
        """
        logger.info(f"Retrieving pages from space: {self.space_key}")
        return self._retry_with_backoff(
            self.client.get_all_pages_from_space,
            space=self.space_key,
            start=start,
            limit=limit,
            expand=expand,
        )

    def list_all_space_pages(self: "ConfluenceClient") -> list[Dict[str, Any]]:
        """Get all pages in the Confluence space.

        Returns:
            List of all pages in the space
        """
        logger.info(f"Retrieving all pages in space: {self.space_key}")
        all_pages = []
        start = 0
        limit = 50

        while True:
            response = self._retry_with_backoff(self.get_space_pages, limit=limit, start=start)

            # Extract results from response
            if isinstance(response, dict) and "results" in response:
                pages = response["results"]
            elif isinstance(response, list):
                pages = response
            else:
                pages = []

            all_pages.extend(pages)

            # Check if there are more pages
            if isinstance(response, dict):
                # If response has pagination info, use it
                if len(pages) < limit or response.get("size", 0) < limit:
                    break
                start += limit
            else:
                # If response is a list, we're done
                break

        logger.info(f"Retrieved {len(all_pages)} total pages from space '{self.space_key!r}'")
        return all_pages

    def upload_attachment(self, page_id: str, file_path: Path) -> Optional[Dict[str, Any]]:
        """Upload an attachment to a Confluence page.

        Args:
            page_id: ID of the page to attach the file to
            file_path: Path to the file to upload

        Returns:
            Dict containing the uploaded attachment information

        Raises:
            FileNotFoundError: If the file does not exist
        """
        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            raise FileNotFoundError(f"File not found: {file_path}")

        filename = file_path.name
        logger.info(f"Uploading attachment {filename} to page {page_id}")

        try:
            # Delete existing attachment with the same name to avoid duplicates
            self._delete_existing_attachment(page_id, filename)

            # Upload the new attachment
            url = f"{self.base_url}/rest/api/content/{page_id}/child/attachment"
            headers = {"Authorization": f"Bearer {self.token}"}

            with open(file_path, "rb") as f:
                files = {"file": (filename, f, "application/octet-stream")}
                response = requests.post(url, headers=headers, files=files, verify=True)

            if response.ok:
                logger.info(f"Successfully uploaded attachment: {filename}")
                result = response.json()
                # Return the expected format for compatibility
                if isinstance(result, dict):
                    # Extract filename and other metadata for return
                    return {"title": filename, "id": result.get("id", ""), **result}
                return {"title": filename}
            else:
                logger.error(
                    f"Failed to upload attachment {filename}: "
                    f"{response.status_code} - {response.text}"
                )
                return None

        except Exception as e:
            logger.error(f"Failed to upload attachment {filename}: {e}")
            return None

    def _delete_existing_attachment(self, page_id: str, filename: str) -> None:
        """Delete existing attachment if it exists.

        Args:
            page_id: ID of the page
            filename: Name of the attachment to delete
        """
        try:
            # Get existing attachments
            url = f"{self.base_url}/rest/api/content/{page_id}/child/attachment"
            response = requests.get(url, headers=self.headers, verify=True)

            if response.ok:
                attachments = response.json().get("results", [])
                for attachment in attachments:
                    if attachment.get("title") == filename:
                        attachment_id = attachment.get("id")
                        delete_url = f"{self.base_url}/rest/api/content/{attachment_id}"
                        delete_response = requests.delete(
                            delete_url, headers=self.headers, verify=True
                        )
                        if delete_response.ok:
                            logger.debug(f"Deleted existing attachment: {filename}")
                        break

        except Exception as e:
            logger.warning(f"Could not delete existing attachment {filename}: {e}")

    def get_space_page_titles(self: "ConfluenceClient") -> Dict[str, str]:
        """Get all page titles in the space mapped to their IDs.

        Returns:
            Dict mapping page titles to page IDs
        """
        logger.info(f"Retrieving all page titles in space: {self.space_key}")
        all_pages = self.list_all_space_pages()

        title_to_id = {}
        for page in all_pages:
            title = page.get("title", "")
            page_id = page.get("id", "")
            if title and page_id:
                title_to_id[title] = page_id

        logger.info(f"Found {len(title_to_id)} pages in space '{self.space_key!r}'")
        return title_to_id

    def check_title_conflicts(self: "ConfluenceClient", titles: list[str]) -> Dict[str, str]:
        """Check for title conflicts with existing pages in the space.

        Args:
            titles: List of page titles to check for conflicts

        Returns:
            Dict mapping conflicting titles to their existing page IDs
        """
        logger.info(f"Checking {len(titles)} titles for conflicts in space: {self.space_key}")

        existing_titles = self.get_space_page_titles()
        conflicts = {}

        for title in titles:
            if title in existing_titles:
                conflicts[title] = existing_titles[title]
                logger.warning(
                    f"Title conflict detected: '{title!r}' already exists (ID: {existing_titles[title]})"
                )

        if conflicts:
            logger.warning(
                f"Found {len(conflicts)} title conflicts out of {len(titles)} titles checked"
            )
        else:
            logger.info(f"No title conflicts found for {len(titles)} titles")

        return conflicts
