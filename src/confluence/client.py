"""Confluence API client for interacting with Confluence Server/Data Center."""

import logging
import threading
import time
from typing import Any, Dict, Optional

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
        # create_params = {
        #     "type": "page",
        #     "title": title,
        #     "space": {"key": self.space_key},
        #     "body": {
        #         "storage": {
        #             "value": body,
        #             "representation": representation,
        #         }
        #     },
        # }

        # if parent_id:
        #     create_params["ancestors"] = [{"id": parent_id}]

        result = self._retry_with_backoff(
            self.client.create_page,
            space=self.space_key,
            title=title,
            body=body,
            parent_id=parent_id,
            representation=representation,
        )

        # After successful page creation, get and log all pages in the space
        try:
            all_pages = self.list_all_space_pages()
            page_titles = [page.get("title", "Unknown") for page in all_pages]
            logger.info(
                f"Pages in space '{self.space_key!r}' after creating '{title!r}': {page_titles}"
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
        """Get all pages within the Confluence space (handles pagination automatically).

        This method retrieves all pages from the space by handling pagination automatically,
        making it easier to check the complete state of pages in the space.

        Returns:
            List containing all pages in the space
        """
        logger.info(f"Retrieving all pages from space: {self.space_key}")
        all_pages = []
        start = 0
        limit = 50

        while True:
            response = self.get_space_pages(limit=limit, start=start)

            if not response:
                break

            all_pages.extend(response)

            if len(response) < limit:
                break

            start += limit

        logger.info(f"Retrieved {len(all_pages)} total pages from space: {self.space_key}")
        return all_pages
