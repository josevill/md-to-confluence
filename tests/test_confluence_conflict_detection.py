"""Tests for ConfluenceClient conflict detection methods."""

from unittest.mock import patch

import pytest

from src.confluence.client import ConfluenceClient


class TestConfluenceClientConflictDetection:
    """Test conflict detection methods in ConfluenceClient."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock ConfluenceClient for testing."""
        with patch.object(ConfluenceClient, "_instance", None):
            client = ConfluenceClient.get_instance(
                base_url="https://test.atlassian.net", token="test-token", space_key="TEST"
            )
            yield client

    def test_get_space_page_titles_empty_space(self, mock_client):
        """Test getting page titles from an empty space."""
        with patch.object(mock_client, "list_all_space_pages", return_value=[]):
            titles = mock_client.get_space_page_titles()

            assert titles == {}

    def test_get_space_page_titles_with_pages(self, mock_client):
        """Test getting page titles from a space with pages."""
        mock_pages = [
            {"id": "12345", "title": "Page One"},
            {"id": "67890", "title": "Page Two"},
            {"id": "11111", "title": "Page Three"},
        ]

        with patch.object(mock_client, "list_all_space_pages", return_value=mock_pages):
            titles = mock_client.get_space_page_titles()

            expected = {"Page One": "12345", "Page Two": "67890", "Page Three": "11111"}
            assert titles == expected

    def test_get_space_page_titles_missing_fields(self, mock_client):
        """Test getting page titles when some pages have missing fields."""
        mock_pages = [
            {"id": "12345", "title": "Page One"},
            {"id": "67890"},  # Missing title
            {"title": "Page Three"},  # Missing id
            {"id": "11111", "title": "Page Four"},
        ]

        with patch.object(mock_client, "list_all_space_pages", return_value=mock_pages):
            titles = mock_client.get_space_page_titles()

            expected = {"Page One": "12345", "Page Four": "11111"}
            assert titles == expected

    def test_check_title_conflicts_no_conflicts(self, mock_client):
        """Test checking for title conflicts when none exist."""
        mock_existing_titles = {"Existing Page One": "12345", "Existing Page Two": "67890"}

        with patch.object(mock_client, "get_space_page_titles", return_value=mock_existing_titles):
            conflicts = mock_client.check_title_conflicts(["New Page", "Another New Page"])

            assert conflicts == {}

    def test_check_title_conflicts_with_conflicts(self, mock_client):
        """Test checking for title conflicts when they exist."""
        mock_existing_titles = {
            "Existing Page One": "12345",
            "Existing Page Two": "67890",
            "Another Page": "11111",
        }

        titles_to_check = ["New Page", "Existing Page One", "Different Page", "Another Page"]

        with patch.object(mock_client, "get_space_page_titles", return_value=mock_existing_titles):
            conflicts = mock_client.check_title_conflicts(titles_to_check)

            expected = {"Existing Page One": "12345", "Another Page": "11111"}
            assert conflicts == expected

    def test_check_title_conflicts_empty_list(self, mock_client):
        """Test checking for title conflicts with empty title list."""
        mock_existing_titles = {"Existing Page One": "12345", "Existing Page Two": "67890"}

        with patch.object(mock_client, "get_space_page_titles", return_value=mock_existing_titles):
            conflicts = mock_client.check_title_conflicts([])

            assert conflicts == {}

    def test_check_title_conflicts_case_sensitivity(self, mock_client):
        """Test that title conflict checking is case-sensitive."""
        mock_existing_titles = {"Page One": "12345", "page two": "67890"}

        titles_to_check = ["page one", "Page Two", "Page One"]

        with patch.object(mock_client, "get_space_page_titles", return_value=mock_existing_titles):
            conflicts = mock_client.check_title_conflicts(titles_to_check)

            # Only exact matches should be detected
            expected = {"Page One": "12345"}
            assert conflicts == expected

    def test_check_title_conflicts_duplicate_titles_in_input(self, mock_client):
        """Test checking for conflicts when input has duplicate titles."""
        mock_existing_titles = {"Existing Page": "12345"}

        titles_to_check = ["New Page", "Existing Page", "New Page", "Existing Page"]

        with patch.object(mock_client, "get_space_page_titles", return_value=mock_existing_titles):
            conflicts = mock_client.check_title_conflicts(titles_to_check)

            expected = {"Existing Page": "12345"}
            assert conflicts == expected

    @patch("src.confluence.client.logger")
    def test_get_space_page_titles_logging(self, mock_logger, mock_client):
        """Test that appropriate logging occurs during page title retrieval."""
        mock_pages = [{"id": "12345", "title": "Page One"}, {"id": "67890", "title": "Page Two"}]

        with patch.object(mock_client, "list_all_space_pages", return_value=mock_pages):
            mock_client.get_space_page_titles()

            # Check that info logs were called
            assert mock_logger.info.call_count >= 2
            mock_logger.info.assert_any_call("Retrieving all page titles in space: TEST")
            mock_logger.info.assert_any_call("Found 2 pages in space 'TEST'")

    @patch("src.confluence.client.logger")
    def test_check_title_conflicts_logging_no_conflicts(self, mock_logger, mock_client):
        """Test logging when no conflicts are found."""
        mock_existing_titles = {"Existing Page": "12345"}

        with patch.object(mock_client, "get_space_page_titles", return_value=mock_existing_titles):
            mock_client.check_title_conflicts(["New Page"])

            mock_logger.info.assert_any_call("Checking 1 titles for conflicts in space: TEST")
            mock_logger.info.assert_any_call("No title conflicts found for 1 titles")

    @patch("src.confluence.client.logger")
    def test_check_title_conflicts_logging_with_conflicts(self, mock_logger, mock_client):
        """Test logging when conflicts are found."""
        mock_existing_titles = {"Existing Page": "12345"}

        with patch.object(mock_client, "get_space_page_titles", return_value=mock_existing_titles):
            mock_client.check_title_conflicts(["Existing Page", "New Page"])

            mock_logger.info.assert_any_call("Checking 2 titles for conflicts in space: TEST")
            mock_logger.warning.assert_any_call(
                "Title conflict detected: 'Existing Page' already exists (ID: 12345)"
            )
            mock_logger.warning.assert_any_call("Found 1 title conflicts out of 2 titles checked")

    def test_get_space_page_titles_exception_handling(self, mock_client):
        """Test exception handling in get_space_page_titles."""
        with patch.object(mock_client, "list_all_space_pages", side_effect=Exception("API Error")):
            with pytest.raises(Exception, match="API Error"):
                mock_client.get_space_page_titles()

    def test_check_title_conflicts_exception_handling(self, mock_client):
        """Test exception handling in check_title_conflicts."""
        with patch.object(mock_client, "get_space_page_titles", side_effect=Exception("API Error")):
            with pytest.raises(Exception, match="API Error"):
                mock_client.check_title_conflicts(["Test Page"])


class TestConfluenceClientConflictDetectionIntegration:
    """Integration tests for ConfluenceClient conflict detection."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock ConfluenceClient for integration testing."""
        with patch.object(ConfluenceClient, "_instance", None):
            client = ConfluenceClient.get_instance(
                base_url="https://test.atlassian.net", token="test-token", space_key="TEST"
            )
            yield client

    def test_full_conflict_detection_workflow(self, mock_client):
        """Test the complete conflict detection workflow."""
        # Mock existing pages in the space
        mock_pages = [
            {"id": "12345", "title": "Getting Started"},
            {"id": "67890", "title": "User Guide"},
            {"id": "11111", "title": "API Reference"},
            {"id": "22222", "title": "Troubleshooting"},
        ]

        # Proposed new pages (some conflicting)
        proposed_titles = [
            "Getting Started",  # Conflict
            "Installation Guide",  # No conflict
            "User Guide",  # Conflict
            "Advanced Topics",  # No conflict
            "API Reference",  # Conflict
        ]

        with patch.object(mock_client, "list_all_space_pages", return_value=mock_pages):
            # Get all existing titles
            existing_titles = mock_client.get_space_page_titles()

            # Check for conflicts
            conflicts = mock_client.check_title_conflicts(proposed_titles)

            # Verify results
            assert len(existing_titles) == 4
            assert len(conflicts) == 3

            expected_conflicts = {
                "Getting Started": "12345",
                "User Guide": "67890",
                "API Reference": "11111",
            }
            assert conflicts == expected_conflicts

            # Verify non-conflicting titles
            non_conflicting = [title for title in proposed_titles if title not in conflicts]
            assert set(non_conflicting) == {"Installation Guide", "Advanced Topics"}

    def test_large_space_conflict_detection(self, mock_client):
        """Test conflict detection with a large number of pages."""
        # Generate a large number of mock pages
        mock_pages = [{"id": f"{i:05d}", "title": f"Page {i:03d}"} for i in range(1000)]

        # Proposed titles with some conflicts
        proposed_titles = [
            "Page 001",  # Conflict
            "Page 500",  # Conflict
            "Page 999",  # Conflict
            "New Page 1",  # No conflict
            "New Page 2",  # No conflict
        ]

        with patch.object(mock_client, "list_all_space_pages", return_value=mock_pages):
            conflicts = mock_client.check_title_conflicts(proposed_titles)

            assert len(conflicts) == 3
            assert "Page 001" in conflicts
            assert "Page 500" in conflicts
            assert "Page 999" in conflicts
            assert "New Page 1" not in conflicts
            assert "New Page 2" not in conflicts
