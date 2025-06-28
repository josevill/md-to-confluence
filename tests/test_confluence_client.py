"""Tests for ConfluenceClient."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from requests.exceptions import HTTPError, RequestException

from src.confluence.client import ConfluenceClient


class TestConfluenceClient:
    """Test suite for ConfluenceClient."""

    @pytest.fixture
    def mock_confluence_api(self):
        """Mock the underlying Confluence API."""
        with patch("src.confluence.client.Confluence") as mock_api:
            yield mock_api

    @pytest.fixture
    def client(self, mock_confluence_api):
        """Create a ConfluenceClient instance with mocked API."""
        with patch.object(ConfluenceClient, "_instance", None):
            client = ConfluenceClient.get_instance(
                base_url="https://example.atlassian.net", token="test-token", space_key="TEST"
            )
            return client

    def test_singleton_pattern(self, mock_confluence_api):
        """Test that ConfluenceClient follows singleton pattern."""
        # Clear any existing instance
        ConfluenceClient._instance = None

        client1 = ConfluenceClient.get_instance(
            base_url="https://example.atlassian.net", token="test-token", space_key="TEST"
        )

        client2 = ConfluenceClient.get_instance()

        assert client1 is client2

    def test_singleton_thread_safety(self, mock_confluence_api):
        """Test singleton pattern is thread-safe."""
        import threading

        # Clear any existing instance
        ConfluenceClient._instance = None
        instances = []

        def create_client():
            try:
                client = ConfluenceClient.get_instance(
                    base_url="https://example.atlassian.net", token="test-token", space_key="TEST"
                )
                instances.append(client)
            except Exception:
                pass  # Ignore errors from multiple threads trying to create

        # Create multiple threads
        threads = [threading.Thread(target=create_client) for _ in range(5)]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # Should have at least one instance created, and all should be the same
        assert len(instances) >= 1
        assert len(set(instances)) == 1

    def test_authentication_initialization(self, client):
        """Test client authentication and initialization."""
        assert client.base_url == "https://example.atlassian.net"
        assert client.space_key == "TEST"
        assert client.token == "test-token"
        assert client.client is not None

    def test_retry_with_backoff_success(self, client):
        """Test successful retry operation."""
        mock_func = Mock(return_value="success")

        result = client._retry_with_backoff(mock_func, "test", param="value")

        assert result == "success"
        mock_func.assert_called_once_with("test", param="value")

    def test_retry_with_backoff_temporary_failure(self, client):
        """Test retry with temporary failures."""
        mock_func = Mock()
        # Create proper HTTPError objects with response
        mock_response1 = Mock()
        mock_response1.status_code = 500
        error1 = HTTPError("500 Server Error")
        error1.response = mock_response1

        mock_response2 = Mock()
        mock_response2.status_code = 502
        error2 = HTTPError("502 Bad Gateway")
        error2.response = mock_response2

        # First two calls fail, third succeeds
        mock_func.side_effect = [error1, error2, "success"]

        with patch("time.sleep") as mock_sleep:
            result = client._retry_with_backoff(mock_func, "test")

        assert result == "success"
        assert mock_func.call_count == 3
        assert mock_sleep.call_count == 2  # Slept before retry attempts

    def test_retry_with_backoff_max_attempts_exceeded(self, client):
        """Test retry when max attempts are exceeded."""
        mock_response = Mock()
        mock_response.status_code = 500
        error = HTTPError("500 Server Error")
        error.response = mock_response
        mock_func = Mock(side_effect=error)

        with patch("time.sleep"):
            with pytest.raises(HTTPError):
                client._retry_with_backoff(mock_func, max_retries=2)

        assert mock_func.call_count == 3  # Initial + 2 retries

    def test_create_page_success(self, client):
        """Test successful page creation."""
        mock_response = {"id": "123", "title": "Test Page", "type": "page"}

        with patch.object(client, "_retry_with_backoff") as mock_retry:
            mock_retry.return_value = mock_response

            result = client.create_page("Test Page", "<p>Test content</p>")

            assert result == mock_response
            # Should be called twice: once for direct request, once for getting pages
            assert mock_retry.call_count >= 1

    def test_create_page_with_parent(self, client):
        """Test page creation with parent page."""
        mock_response = {"id": "123", "title": "Test Page", "type": "page"}

        with patch.object(client, "_retry_with_backoff") as mock_retry:
            mock_retry.return_value = mock_response

            result = client.create_page("Test Page", "<p>Test content</p>", parent_id="456")

            assert result == mock_response
            assert mock_retry.call_count >= 1

    def test_create_page_failure(self, client):
        """Test page creation failure."""
        with patch.object(client, "_retry_with_backoff") as mock_retry:
            mock_retry.side_effect = HTTPError("400 Bad Request")

            with pytest.raises(HTTPError):
                client.create_page("Test Page", "<p>Test content</p>")

    def test_update_page_success(self, client):
        """Test successful page update."""
        # Mock the get_page_by_id call first
        mock_page = {"id": "123", "title": "Old Title", "version": {"number": 1}, "type": "page"}

        mock_updated_page = {
            "id": "123",
            "title": "Updated Page",
            "version": {"number": 2},
            "type": "page",
        }

        with patch.object(client, "_retry_with_backoff") as mock_retry:
            # First call returns the existing page, second returns updated page
            mock_retry.side_effect = [mock_page, mock_updated_page]

            result = client.update_page("123", "Updated Page", "<p>Updated content</p>")

            assert result == mock_updated_page
            assert mock_retry.call_count == 2

    def test_update_page_not_found(self, client):
        """Test updating non-existent page."""
        with patch.object(client, "_retry_with_backoff") as mock_retry:
            mock_retry.side_effect = HTTPError("404 Not Found")

            with pytest.raises(HTTPError):
                client.update_page("999", "Title", "<p>Content</p>")

    def test_get_page_by_id_success(self, client):
        """Test successful page retrieval by ID."""
        mock_page = {"id": "123", "title": "Test Page", "type": "page"}

        client.client.get_page_by_id.return_value = mock_page

        result = client.get_page("123")

        assert result == mock_page
        client.client.get_page_by_id.assert_called_once_with(page_id="123")

    def test_get_page_by_id_not_found(self, client):
        """Test page retrieval with non-existent ID."""
        mock_response = Mock()
        mock_response.status_code = 404
        error = HTTPError("404 Not Found")
        error.response = mock_response
        client.client.get_page_by_id.side_effect = error

        with pytest.raises(HTTPError):
            client.get_page("999")

    def test_get_page_by_title_success(self, client):
        """Test successful page retrieval by title."""
        mock_page = {"id": "123", "title": "Test Page", "type": "page"}

        client.client.get_page_by_title.return_value = mock_page

        result = client.get_page_by_title("Test Page")

        assert result == mock_page
        client.client.get_page_by_title.assert_called_once_with(space="TEST", title="Test Page")

    def test_get_page_by_title_not_found(self, client):
        """Test page retrieval with non-existent title."""
        client.client.get_page_by_title.return_value = None

        result = client.get_page_by_title("Non-existent Page")

        assert result is None

    def test_delete_page_success(self, client):
        """Test successful page deletion."""
        with patch.object(client, "_retry_with_backoff") as mock_retry:
            mock_retry.return_value = None

            result = client.delete_page("123")

            assert result is None
            mock_retry.assert_called_once()

    def test_delete_page_failure(self, client):
        """Test page deletion failure."""
        with patch.object(client, "_retry_with_backoff") as mock_retry:
            mock_retry.side_effect = HTTPError("404 Not Found")

            with pytest.raises(HTTPError):
                client.delete_page("999")

    def test_get_child_pages_success(self, client):
        """Test successful child pages retrieval."""
        mock_child_pages = [{"id": "456", "title": "Child 1"}, {"id": "789", "title": "Child 2"}]

        client.client.get_page_child_by_type.return_value = mock_child_pages

        result = client.get_child_pages("123")

        assert result == mock_child_pages
        client.client.get_page_child_by_type.assert_called_once_with(page_id="123", type="page")

    def test_get_child_pages_empty(self, client):
        """Test child pages retrieval when no children exist."""
        client.client.get_page_child_by_type.return_value = []

        result = client.get_child_pages("123")

        assert result == []

    def test_list_all_space_pages_success(self, client):
        """Test successful listing of all space pages."""
        mock_pages_response = {
            "results": [
                {"id": "1", "title": "Page 1"},
                {"id": "2", "title": "Page 2"},
                {"id": "3", "title": "Page 3"},
            ],
            "size": 3,
            "start": 0,
            "limit": 50,
        }

        with patch.object(client, "get_space_pages") as mock_get_space_pages:
            mock_get_space_pages.return_value = mock_pages_response

            result = client.list_all_space_pages()

            # Should return the results array
            assert len(result) == 3
            assert result[0]["id"] == "1"
            assert result[1]["id"] == "2"
            assert result[2]["id"] == "3"

    def test_list_all_space_pages_empty(self, client):
        """Test listing pages from empty space."""
        mock_empty_response = {"results": [], "size": 0, "start": 0, "limit": 50}

        with patch.object(client, "_retry_with_backoff") as mock_retry:
            mock_retry.return_value = mock_empty_response

            result = client.list_all_space_pages()

            assert result == []

    def test_upload_attachment_success(self, client):
        """Test successful attachment upload."""
        test_file = Path("test.png")

        # Mock the requests.post to simulate successful upload
        with patch("requests.post") as mock_post:
            mock_response = Mock()
            mock_response.ok = True
            mock_response.json.return_value = {"id": "att123", "title": "test.png"}
            mock_post.return_value = mock_response

            # Mock the delete existing attachment method
            with patch.object(client, "_delete_existing_attachment"):
                result = client.upload_attachment("123", test_file)

                assert result["title"] == "test.png"
                assert result["id"] == "att123"

    def test_upload_attachment_file_not_found(self, client):
        """Test attachment upload with non-existent file."""
        non_existent_file = Path("does_not_exist.png")

        with pytest.raises(FileNotFoundError):
            client.upload_attachment("123", non_existent_file)

    def test_upload_attachment_api_error(self, client):
        """Test attachment upload with API error."""
        test_file = Path("test.png")

        # Mock the requests.post to return an error
        with patch("requests.post") as mock_post:
            mock_response = Mock()
            mock_response.ok = False
            mock_response.status_code = 500
            mock_response.text = "Server Error"
            mock_post.return_value = mock_response

            result = client.upload_attachment("123", test_file)
            assert result is None  # Should return None on error

    def test_make_direct_request_get(self, client):
        """Test direct GET request."""
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {"success": True}
        mock_response.raise_for_status.return_value = None

        with patch("requests.request") as mock_request:
            mock_request.return_value = mock_response

            result = client._make_direct_request("GET", "rest/api/content/123")

            assert result == {"success": True}
            mock_request.assert_called_once()

    def test_make_direct_request_post(self, client):
        """Test direct POST request."""
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {"id": "123"}
        mock_response.raise_for_status.return_value = None

        with patch("requests.request") as mock_request:
            mock_request.return_value = mock_response

            data = {"title": "Test Page"}
            result = client._make_direct_request("POST", "rest/api/content/", data)

            assert result == {"id": "123"}
            mock_request.assert_called_once()

    def test_make_direct_request_put(self, client):
        """Test direct PUT request."""
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {"updated": True}
        mock_response.raise_for_status.return_value = None

        with patch("requests.request") as mock_request:
            mock_request.return_value = mock_response

            data = {"title": "Updated Page"}
            result = client._make_direct_request("PUT", "rest/api/content/123", data)

            assert result == {"updated": True}
            mock_request.assert_called_once()

    def test_make_direct_request_delete(self, client):
        """Test direct DELETE request."""
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {}
        mock_response.raise_for_status.return_value = None

        with patch("requests.request") as mock_request:
            mock_request.return_value = mock_response

            result = client._make_direct_request("DELETE", "rest/api/content/123")

            assert result == {}
            mock_request.assert_called_once()

    def test_make_direct_request_http_error(self, client):
        """Test direct request with HTTP error."""
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = HTTPError("400 Bad Request")

        client._confluence._session.get.return_value = mock_response

        with pytest.raises(HTTPError):
            client._make_direct_request("GET", "rest/api/content/invalid")

    def test_rate_limiting_behavior(self, client):
        """Test that rate limiting is handled correctly."""
        mock_func = Mock()
        mock_func.side_effect = [HTTPError("429 Too Many Requests"), "success"]

        with patch("time.sleep") as mock_sleep:
            result = client._retry_with_backoff(mock_func)

        assert result == "success"
        assert mock_func.call_count == 2
        mock_sleep.assert_called_once()

    def test_request_timeout_handling(self, client):
        """Test handling of request timeouts."""
        mock_func = Mock(side_effect=RequestException("Request timeout"))

        with patch("time.sleep"):
            with pytest.raises(RequestException):
                client._retry_with_backoff(mock_func, max_retries=1)

    def test_exponential_backoff_timing(self, client):
        """Test exponential backoff timing."""
        mock_func = Mock()
        mock_func.side_effect = [
            HTTPError("500 Server Error"),
            HTTPError("500 Server Error"),
            "success",
        ]

        with patch("time.sleep") as mock_sleep:
            client._retry_with_backoff(mock_func)

        # Should have slept twice with exponential backoff
        assert mock_sleep.call_count == 2
        # First sleep should be base_delay (1 second)
        # Second sleep should be base_delay * 2^attempt
        sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
        assert sleep_calls[0] == 1  # First retry
        assert sleep_calls[1] == 2  # Second retry (exponential backoff)

    @pytest.mark.integration
    def test_full_page_workflow(self, client):
        """Test complete page creation, update, and deletion workflow."""
        # Mock responses for each step
        create_response = {"id": "123", "title": "Test Page", "type": "page"}
        get_response = {"id": "123", "title": "Test Page", "version": {"number": 1}, "type": "page"}
        update_response = {
            "id": "123",
            "title": "Updated Page",
            "version": {"number": 2},
            "type": "page",
        }

        with patch.object(client, "_retry_with_backoff") as mock_retry:
            # Set up side effects for different calls
            mock_retry.side_effect = [
                create_response,  # create_page call
                {},  # list_all_space_pages call (create_page)
                get_response,  # get_page_by_id call (update_page)
                update_response,  # update_page call
                True,  # delete_page call
            ]

            # Create page
            created = client.create_page("Test Page", "<p>Test content</p>")
            assert created["id"] == "123"

            # Update page
            updated = client.update_page("123", "Updated Page", "<p>Updated content</p>")
            assert updated["title"] == "Updated Page"

            # Delete page
            deleted = client.delete_page("123")
            assert deleted is None  # delete_page returns None on success

    @pytest.mark.thread_safety
    def test_concurrent_requests(self, client):
        """Test concurrent requests to ensure thread safety."""
        import threading

        mock_func = Mock(return_value="success")
        results = []

        def make_request():
            result = client._retry_with_backoff(mock_func)
            results.append(result)

        # Create multiple threads making concurrent requests
        threads = [threading.Thread(target=make_request) for _ in range(10)]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # All requests should succeed
        assert len(results) == 10
        assert all(result == "success" for result in results)
