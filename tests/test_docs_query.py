"""
Unit and integration tests for PharosDocsClient (scripts/docs_query.py).
Tests URL construction, parameter encoding, error handling, mock HTTP responses, and CLI parsing.
"""

import io
import sys
import json
import unittest
from unittest.mock import patch, MagicMock
import urllib.error

from scripts.docs_query import PharosDocsClient, DEFAULT_DOCS_ENDPOINT, DEFAULT_GOAL, main


class TestPharosDocsClient(unittest.TestCase):
    """Offline unit tests for PharosDocsClient using mocks."""

    def setUp(self):
        self.client = PharosDocsClient(timeout=5)

    def test_build_query_url_default_goal(self):
        """Verifies canonical URL construction with default goal."""
        ask = "What is the Atlantic RPC URL?"
        url = self.client.build_query_url(ask)
        self.assertTrue(url.startswith(DEFAULT_DOCS_ENDPOINT))
        self.assertIn("ask=What+is+the+Atlantic+RPC+URL%3F", url)
        self.assertIn("goal=develop+and+verify+autonomous+AI+agents+on+Pharos", url)

    def test_build_query_url_custom_goal(self):
        """Verifies custom goal parameter encoding."""
        ask = "How to call eth_call"
        custom_goal = "query contract state via MCP"
        url = self.client.build_query_url(ask, goal=custom_goal)
        self.assertIn("ask=How+to+call+eth_call", url)
        self.assertIn("goal=query+contract+state+via+MCP", url)

    def test_empty_ask_raises_error(self):
        """Ensures empty or whitespace ask string raises ValueError."""
        with self.assertRaises(ValueError):
            self.client.query("")
        with self.assertRaises(ValueError):
            self.client.query("   ")

    @patch("urllib.request.urlopen")
    def test_query_success_mock(self, mock_urlopen):
        """Verifies successful query handling with mock Markdown response."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b"# Atlantic RPC\nhttps://atlantic.dplabs-internal.com"
        mock_urlopen.return_value.__enter__.return_value = mock_response

        res = self.client.query("What is the RPC URL?")
        self.assertTrue(res["success"])
        self.assertEqual(res["http_status"], 200)
        self.assertIn("https://atlantic.dplabs-internal.com", res["markdown_content"])
        self.assertIsNone(res["error"])

    @patch("urllib.request.urlopen")
    def test_query_http_error_mock(self, mock_urlopen):
        """Verifies HTTPError handling (e.g. 404 or 500)."""
        error_file = io.BytesIO(b"Page Not Found")
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://docs.pharos.xyz/test",
            code=404,
            msg="Not Found",
            hdrs={},
            fp=error_file
        )

        res = self.client.query("Invalid doc question")
        self.assertFalse(res["success"])
        self.assertEqual(res["http_status"], 404)
        self.assertIn("HTTP 404", res["error"])

    @patch("urllib.request.urlopen")
    def test_query_timeout_mock(self, mock_urlopen):
        """Verifies timeout exception handling."""
        mock_urlopen.side_effect = TimeoutError("The read operation timed out")

        res = self.client.query("Timeout question")
        self.assertFalse(res["success"])
        self.assertEqual(res["http_status"], 0)
        self.assertIn("timed out", res["error"].lower())

    @patch("scripts.docs_query.PharosDocsClient.query")
    def test_cli_json_output(self, mock_query):
        """Verifies CLI prints JSON when --json flag is supplied."""
        mock_query.return_value = {
            "success": True,
            "ask": "test question",
            "goal": "test goal",
            "endpoint": "https://docs.pharos.xyz/index.md",
            "http_status": 200,
            "elapsed_seconds": 0.12,
            "markdown_content": "# Mock Content",
            "error": None
        }

        test_args = ["docs_query.py", "test question", "--json"]
        with patch.object(sys, "argv", test_args):
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                main()
                output = mock_stdout.getvalue()
                parsed = json.loads(output)
                self.assertTrue(parsed["success"])
                self.assertEqual(parsed["markdown_content"], "# Mock Content")


if __name__ == "__main__":
    unittest.main()
