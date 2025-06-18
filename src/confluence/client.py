"""Confluence API client for interacting with Confluence Server/Data Center."""

import logging
import time
from typing import Any, Dict, Optional

from atlassian import Confluence
from requests.exceptions import HTTPError, RequestException

logger = logging.getLogger(__name__)


class ConfluenceClient:
    """Client for interacting with Confluence API."""

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
        """
        self.base_url = base_url.rstrip("/")
        self.space_key = space_key
        self.retry_max_attempts = retry_max_attempts
        self.retry_backoff_factor = retry_backoff_factor

        # Initialize the Confluence client
        self.client = Confluence(
            url=self.base_url,
            token=token,
            verify_ssl=True,
        )
        logger.info(f"Initialized Confluence client for space: {space_key}")

    def _retry_with_backoff(
        self: "ConfluenceClient", operation: callable, *args: Any, **kwargs: Any
    ) -> Any:
        """Execute an operation with exponential backoff retry logic.

        Args:
            operation: The function to execute
            *args: Positional arguments for the operation
            **kwargs: Keyword arguments for the operation

        Returns:
            The result of the operation

        Raises:
            Exception: If all retry attempts fail
        """
        for attempt in range(self.retry_max_attempts):
            try:
                return operation(*args, **kwargs)
            except HTTPError as e:
                if e.response.status_code == 429:  # Too Many Requests
                    wait_time = self.retry_backoff_factor * (2**attempt)
                    logger.warning(f"Rate limit hit, waiting {wait_time}s before retry...")
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

    def create_page(
        self: "ConfluenceClient",
        title: str,
        body: str,
        parent_id: Optional[str] = None,
        representation: str = "storage",
    ) -> Dict[str, Any]:
        """Create a new page in Confluence.

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

        return self._retry_with_backoff(self.client.create_page, **create_params)

    def update_page(
        self: "ConfluenceClient",
        page_id: str,
        title: str,
        body: str,
        representation: str = "storage",
    ) -> Dict[str, Any]:
        """Update an existing page in Confluence.

        Args:
            page_id: ID of the page to update
            title: New title of the page
            body: New content of the page
            representation: Content representation (default: storage)

        Returns:
            Dict containing the updated page information
        """
        logger.info(f"Updating page: {title} (ID: {page_id})")

        curr_page = self._retry_with_backoff(self.client.get_page_by_id, page_id)
        version = curr_page["version"]["number"]

        update_params = {
            "page_id": page_id,
            "title": title,
            "body": body,
            "type": "page",
            "version": version + 1,
            "representation": representation,
        }

        return self._retry_with_backoff(self.client.update_page, **update_params)

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
        return pages[0] if pages else None

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
