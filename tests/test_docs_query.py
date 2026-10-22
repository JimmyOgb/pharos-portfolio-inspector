"""
Unit and integration tests for PharosDocsMCPClient (scripts/docs_query.py).
Tests MCP protocol framing, initialization, tool discovery, tool invocation,
error handling, CLI commands, and regression protection against the old GitBook ask endpoint.
"""

import io
import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock
import urllib.error

from scripts.docs_query import (
    PharosDocsMCPClient,
    PharosDocsClient,
    PharosMCPError,
    DEFAULT_DOCS_MCP_ENDPOINT,
    DEFAULT_PROTOCOL_VERSION,
    DEFAULT_GOAL,
    main,
)


def make_mcp_sse_response(payload: dict, status: int = 200) -> MagicMock:
    """Helper to mock an MCP Streamable HTTP response with SSE framing."""
    sse_text = f"event: message\ndata: {json.dumps(payload)}\n\n"
    mock_resp = MagicMock()
    mock_resp.status = status
    mock_resp.headers = {"Content-Type": "text/event-stream"}
    mock_resp.read.return_value = sse_text.encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    return mock_resp


class TestPharosDocsMCPClient(unittest.TestCase):
    """Offline unit tests for PharosDocsMCPClient using mock protocol fixtures."""

    def setUp(self):
        self.client = PharosDocsMCPClient(timeout=5)

    def test_empty_ask_raises_error(self):
        """Ensures empty or whitespace question raises ValueError."""
        with self.assertRaises(ValueError):
            self.client.query("")
        with self.assertRaises(ValueError):
            self.client.query("   ")
        with self.assertRaises(ValueError):
            self.client.ask_question("")

    def test_empty_search_or_page_raises_error(self):
        """Ensures empty search query or page URL raises ValueError."""
        with self.assertRaises(ValueError):
            self.client.search("")
        with self.assertRaises(ValueError):
            self.client.get_page("")
        with self.assertRaises(ValueError):
            self.client.call_tool("", {})

    @patch("urllib.request.urlopen")
    def test_mcp_initialize_mock(self, mock_urlopen):
        """Verifies JSON-RPC 2.0 initialize request and capability handshake."""
        init_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "protocolVersion": DEFAULT_PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": True}},
                "serverInfo": {
                    "name": "docs.pharos.xyz/~gitbook/mcp",
                    "title": "docs.pharos.xyz MCP Server",
                    "version": "0.27.2",
                },
            },
        }
        mock_urlopen.return_value = make_mcp_sse_response(init_payload)

        result = self.client.initialize()
        self.assertEqual(result["protocolVersion"], DEFAULT_PROTOCOL_VERSION)
        self.assertEqual(self.client.server_info["version"], "0.27.2")
        self.assertEqual(self.client.server_info["name"], "docs.pharos.xyz/~gitbook/mcp")

        # Verify first outgoing request was POST initialize to MCP endpoint
        self.assertGreaterEqual(len(mock_urlopen.call_args_list), 1)
        req = mock_urlopen.call_args_list[0][0][0]
        self.assertEqual(req.full_url, DEFAULT_DOCS_MCP_ENDPOINT)
        self.assertEqual(req.get_method(), "POST")
        sent_body = json.loads(req.data.decode("utf-8"))
        self.assertEqual(sent_body["method"], "initialize")
        self.assertEqual(sent_body["params"]["protocolVersion"], DEFAULT_PROTOCOL_VERSION)

    @patch("urllib.request.urlopen")
    def test_mcp_list_tools_mock(self, mock_urlopen):
        """Verifies tools/list tool discovery."""
        self.client.server_info = {"name": "docs.pharos.xyz/~gitbook/mcp"}
        tools_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "tools": [
                    {"name": "searchDocumentation", "description": "Search docs"},
                    {"name": "getPage", "description": "Get page markdown"},
                    {"name": "askQuestion", "description": "Ask question"},
                    {"name": "sendFeedback", "description": "Report doc issue"},
                ]
            },
        }
        mock_urlopen.return_value = make_mcp_sse_response(tools_payload)

        tools = self.client.list_tools()
        self.assertEqual(len(tools), 4)
        tool_names = [t["name"] for t in tools]
        self.assertIn("askQuestion", tool_names)
        self.assertIn("searchDocumentation", tool_names)
        self.assertIn("getPage", tool_names)
        self.assertIn("sendFeedback", tool_names)

    @patch("urllib.request.urlopen")
    def test_mcp_ask_question_mock(self, mock_urlopen):
        """Verifies tools/call for askQuestion tool with argument passing and source extraction."""
        self.client.server_info = {"name": "docs.pharos.xyz/~gitbook/mcp"}
        call_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "The Atlantic RPC URL is `https://atlantic.dplabs-internal.com`.\n\n"
                            "# Sources\n\n"
                            "- [Atlantic Testnet](https://docs.pharos.xyz/getting-started/network/atlantic-testnet)\n"
                            "- [ZAN RPC](https://docs.pharos.xyz/tooling-and-infrastructure/rpc/zan)\n"
                        ),
                    }
                ]
            },
        }
        mock_urlopen.return_value = make_mcp_sse_response(call_payload)

        res = self.client.ask_question("What is the Atlantic RPC URL?", goal="test goal")
        self.assertTrue(res["success"])
        self.assertEqual(res["tool"], "askQuestion")
        self.assertIn("https://atlantic.dplabs-internal.com", res["markdown_content"])
        self.assertEqual(len(res["sources"]), 2)
        self.assertEqual(res["sources"][0]["title"], "Atlantic Testnet")
        self.assertEqual(
            res["sources"][0]["url"],
            "https://docs.pharos.xyz/getting-started/network/atlantic-testnet",
        )

        # Verify sent arguments in tools/call
        req = mock_urlopen.call_args[0][0]
        sent_body = json.loads(req.data.decode("utf-8"))
        self.assertEqual(sent_body["method"], "tools/call")
        self.assertEqual(sent_body["params"]["name"], "askQuestion")
        self.assertEqual(sent_body["params"]["arguments"]["question"], "What is the Atlantic RPC URL?")
        self.assertEqual(sent_body["params"]["arguments"]["goal"], "test goal")

    @patch("urllib.request.urlopen")
    def test_mcp_search_mock(self, mock_urlopen):
        """Verifies tools/call for searchDocumentation tool."""
        self.client.server_info = {"name": "docs.pharos.xyz/~gitbook/mcp"}
        search_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": "Title: Atlantic Testnet\nLink: https://docs.pharos.xyz/getting-started/network/atlantic-testnet\nContent: RPC URL",
                    }
                ]
            },
        }
        mock_urlopen.return_value = make_mcp_sse_response(search_payload)

        res = self.client.search("Atlantic RPC")
        self.assertTrue(res["success"])
        self.assertEqual(res["tool"], "searchDocumentation")
        self.assertIn("Title: Atlantic Testnet", res["markdown_content"])

    @patch("urllib.request.urlopen")
    def test_mcp_get_page_mock(self, mock_urlopen):
        """Verifies tools/call for getPage tool."""
        self.client.server_info = {"name": "docs.pharos.xyz/~gitbook/mcp"}
        page_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": "# Atlantic Testnet\n\nFull page markdown documentation content.",
                    }
                ]
            },
        }
        mock_urlopen.return_value = make_mcp_sse_response(page_payload)

        res = self.client.get_page("https://docs.pharos.xyz/getting-started/network/atlantic-testnet")
        self.assertTrue(res["success"])
        self.assertEqual(res["tool"], "getPage")
        self.assertIn("# Atlantic Testnet", res["markdown_content"])

    @patch("urllib.request.urlopen")
    def test_mcp_server_error_mock(self, mock_urlopen):
        """Verifies handling of JSON-RPC protocol error from MCP server."""
        self.client.server_info = {"name": "docs.pharos.xyz/~gitbook/mcp"}
        err_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {
                "code": -32602,
                "message": "Tool unknown_tool not found",
            },
        }
        mock_urlopen.return_value = make_mcp_sse_response(err_payload)

        with self.assertRaises(PharosMCPError) as ctx:
            self.client.call_tool("unknown_tool", {})
        self.assertEqual(ctx.exception.code, -32602)
        self.assertIn("not found", str(ctx.exception))

    @patch("urllib.request.urlopen")
    def test_mcp_http_error_mock(self, mock_urlopen):
        """Verifies HTTP 500 / 404 error handling."""
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://docs.pharos.xyz/~gitbook/mcp",
            code=502,
            msg="Bad Gateway",
            hdrs={},
            fp=io.BytesIO(b"Bad Gateway upstream"),
        )

        res = self.client.query("Valid question")
        self.assertFalse(res["success"])
        self.assertIn("HTTP 502", res["error"])

    @patch("urllib.request.urlopen")
    def test_mcp_timeout_error_mock(self, mock_urlopen):
        """Verifies network timeout handling."""
        mock_urlopen.side_effect = TimeoutError("The read operation timed out")

        res = self.client.query("Timeout question")
        self.assertFalse(res["success"])
        self.assertIn("timed out", res["error"].lower())

    @patch("scripts.docs_query.PharosDocsMCPClient.query")
    def test_cli_json_output(self, mock_query):
        """Verifies CLI prints JSON when --json flag is supplied."""
        mock_query.return_value = {
            "success": True,
            "tool": "askQuestion",
            "question": "test question",
            "goal": "test goal",
            "endpoint": DEFAULT_DOCS_MCP_ENDPOINT,
            "server_info": {"name": "docs.pharos.xyz/~gitbook/mcp"},
            "elapsed_seconds": 0.12,
            "markdown_content": "# Mock Content",
            "sources": [{"title": "Doc", "url": "https://docs.pharos.xyz"}],
            "error": None,
        }

        test_args = ["docs_query.py", "test question", "--json"]
        with patch.object(sys, "argv", test_args):
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                main()
                output = mock_stdout.getvalue()
                parsed = json.loads(output)
                self.assertTrue(parsed["success"])
                self.assertEqual(parsed["tool"], "askQuestion")
                self.assertEqual(parsed["markdown_content"], "# Mock Content")

    @patch("scripts.docs_query.PharosDocsMCPClient.list_tools")
    @patch("scripts.docs_query.PharosDocsMCPClient.initialize")
    def test_cli_list_tools(self, mock_init, mock_list):
        """Verifies CLI --list-tools command output."""
        mock_init.return_value = {}
        mock_list.return_value = [
            {"name": "askQuestion", "description": "Ask question tool"},
            {"name": "searchDocumentation", "description": "Search docs tool"},
        ]

        test_args = ["docs_query.py", "--list-tools"]
        with patch.object(sys, "argv", test_args):
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                main()
                output = mock_stdout.getvalue()
                self.assertIn("askQuestion", output)
                self.assertIn("searchDocumentation", output)

    @patch("urllib.request.urlopen")
    def test_regression_old_gitbook_ask_not_used(self, mock_urlopen):
        """
        REGRESSION TEST: Ensures that the implementation NEVER makes requests to
        the rejected GitBook ask endpoint (https://docs.pharos.xyz/index.md?ask=...)
        and strictly communicates via POST JSON-RPC to the Docs MCP server.
        """
        self.client.server_info = {"name": "docs.pharos.xyz/~gitbook/mcp"}
        mock_urlopen.return_value = make_mcp_sse_response({
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "content": [{"type": "text", "text": "Genuine MCP Answer"}]
            }
        })

        res = self.client.query("What is Atlantic RPC?")
        self.assertTrue(res["success"])

        # Inspect all calls to urlopen
        for call_item in mock_urlopen.call_args_list:
            req = call_item[0][0]
            # 1. Target URL must be the MCP endpoint, NEVER index.md
            self.assertEqual(req.full_url, DEFAULT_DOCS_MCP_ENDPOINT)
            self.assertNotIn("index.md", req.full_url)
            self.assertNotIn("?ask=", req.full_url)
            # 2. Method must be POST (JSON-RPC), NEVER GET
            self.assertEqual(req.get_method(), "POST")
            # 3. Payload must be JSON-RPC MCP structure
            body = json.loads(req.data.decode("utf-8"))
            self.assertEqual(body.get("jsonrpc"), "2.0")
            self.assertEqual(body.get("method"), "tools/call")


class TestLivePharosDocsMCP(unittest.TestCase):
    """
    Live integration test against the official Pharos Developer Docs MCP server.
    Only executed when PHAROS_LIVE_TESTS=1 environment variable is present.
    """

    @unittest.skipUnless(os.environ.get("PHAROS_LIVE_TESTS") == "1", "Live network test disabled")
    def test_live_docs_mcp_handshake_and_query(self):
        client = PharosDocsMCPClient(timeout=30)
        init_res = client.initialize()
        self.assertEqual(init_res["protocolVersion"], DEFAULT_PROTOCOL_VERSION)
        self.assertIn("docs.pharos.xyz", client.server_info["name"])

        tools = client.list_tools()
        tool_names = [t["name"] for t in tools]
        self.assertIn("askQuestion", tool_names)
        self.assertIn("searchDocumentation", tool_names)

        # Real read-only query
        query_res = client.query("What is the Atlantic RPC URL?")
        self.assertTrue(query_res["success"])
        self.assertEqual(query_res["tool"], "askQuestion")
        self.assertIn("https://atlantic.dplabs-internal.com", query_res["markdown_content"])


if __name__ == "__main__":
    unittest.main()
