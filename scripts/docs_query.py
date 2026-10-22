#!/usr/bin/env python3
"""
Pharos Developer Docs MCP Client & Wrapper
Implements a Model Context Protocol (MCP) client wrapping the official Pharos Developer Docs MCP server.

Official Endpoint:
    POST https://docs.pharos.xyz/~gitbook/mcp

MCP Server Specification:
    Protocol Version: 2024-11-05
    Transport: Streamable HTTP / Server-Sent Events (SSE) JSON-RPC 2.0
    Server Name: docs.pharos.xyz/~gitbook/mcp
    Exposed Tools:
        1. searchDocumentation(query: str)
        2. getPage(url: str)
        3. askQuestion(question: str, goal?: str)
        4. sendFeedback(content: str, pageUrl: str, goal?: str)

Requirements:
    Zero external dependencies (Python 3.10+ standard library only: urllib, json, re, time, argparse).
    Zero cost ($0.00).
    No GitBook HTTP 'ask' endpoint fallback.
"""

import sys
import json
import time
import re
import argparse
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional, Tuple

DEFAULT_DOCS_MCP_ENDPOINT = "https://docs.pharos.xyz/~gitbook/mcp"
DEFAULT_PROTOCOL_VERSION = "2024-11-05"
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PharosDocsMCP/2.0 (+https://github.com/JimmyOgb/pharos-portfolio-inspector)"
DEFAULT_GOAL = "develop and verify autonomous AI agents on Pharos"
DEFAULT_TIMEOUT = 35


class PharosMCPError(Exception):
    """Raised when an MCP protocol, JSON-RPC, or server error occurs."""

    def __init__(self, code: int, message: str, data: Any = None):
        super().__init__(f"MCP Error [{code}]: {message}")
        self.code = code
        self.message = message
        self.data = data


class PharosDocsMCPClient:
    """Official client and wrapper for the Pharos Developer Docs MCP server."""

    def __init__(
        self,
        endpoint: str = DEFAULT_DOCS_MCP_ENDPOINT,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        self.endpoint = endpoint
        self.user_agent = user_agent
        self.timeout = timeout
        self.session_id: Optional[str] = None
        self.server_info: Optional[Dict[str, Any]] = None
        self.server_capabilities: Optional[Dict[str, Any]] = None
        self._request_id = 0

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    @staticmethod
    def _parse_mcp_response(raw_body: str) -> Dict[str, Any]:
        """
        Parses MCP server responses, safely handling both SSE message framing
        (event: message\\ndata: {...}) and plain JSON-RPC responses.
        """
        trimmed = raw_body.strip()
        if not trimmed:
            raise PharosMCPError(code=-32700, message="Empty response body from Docs MCP server.")

        data_payloads = []
        for line in trimmed.splitlines():
            line_str = line.strip()
            if line_str.startswith("data:"):
                payload = line_str[5:].strip()
                if payload:
                    data_payloads.append(payload)

        if data_payloads:
            # Use the final data payload event in the stream
            try:
                return json.loads(data_payloads[-1])
            except json.JSONDecodeError as e:
                raise PharosMCPError(code=-32700, message=f"Malformed SSE JSON payload: {e}")

        try:
            return json.loads(trimmed)
        except json.JSONDecodeError as e:
            raise PharosMCPError(code=-32700, message=f"Malformed JSON-RPC response: {e}")

    def _rpc_call(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        is_notification: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Executes a JSON-RPC 2.0 call against the Streamable HTTP MCP server.
        """
        call_id = None if is_notification else self._next_id()
        payload: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method
        }
        if call_id is not None:
            payload["id"] = call_id
        if params is not None:
            payload["params"] = params

        req_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": self.user_agent
        }
        if self.session_id:
            req_headers["mcp-session-id"] = self.session_id

        req_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint,
            data=req_bytes,
            headers=req_headers,
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                new_session = resp.headers.get("mcp-session-id")
                if new_session:
                    self.session_id = new_session

                raw_bytes = resp.read()
                if not raw_bytes or is_notification:
                    return None

                body_text = raw_bytes.decode("utf-8", errors="replace")
                data = self._parse_mcp_response(body_text)

                if "error" in data:
                    err = data["error"]
                    raise PharosMCPError(
                        code=err.get("code", -32000),
                        message=err.get("message", "Unknown MCP server error"),
                        data=err.get("data")
                    )

                return data
        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            raise PharosMCPError(
                code=e.code,
                message=f"HTTP {e.code}: {e.reason}. {err_body[:200]}"
            )
        except urllib.error.URLError as e:
            raise ConnectionError(f"Failed to connect to Docs MCP at {self.endpoint}: {e.reason}")
        except TimeoutError as e:
            raise TimeoutError(f"Docs MCP request timed out after {self.timeout}s: {e}")

    def initialize(self) -> Dict[str, Any]:
        """
        Initializes the MCP session with the server and exchanges capabilities.
        """
        params = {
            "protocolVersion": DEFAULT_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {
                "name": "pharos-portfolio-inspector",
                "version": "0.1.0"
            }
        }
        resp = self._rpc_call("initialize", params)
        if not resp or "result" not in resp:
            raise PharosMCPError(code=-32603, message=f"Malformed initialize response: {resp}")

        result = resp["result"]
        self.server_info = result.get("serverInfo", {})
        self.server_capabilities = result.get("capabilities", {})

        # Send notifications/initialized as required by MCP protocol specification
        try:
            self._rpc_call("notifications/initialized", {}, is_notification=True)
        except Exception:
            pass

        return result

    def list_tools(self) -> List[Dict[str, Any]]:
        """
        Discovers all available documentation tools from the server via tools/list.
        """
        if not self.server_info:
            self.initialize()

        resp = self._rpc_call("tools/list", {})
        if not resp or "result" not in resp:
            raise PharosMCPError(code=-32603, message=f"Malformed tools/list response: {resp}")

        return resp["result"].get("tools", [])

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Invokes an MCP tool on the server via tools/call.
        """
        if not tool_name or not tool_name.strip():
            raise ValueError("Tool name cannot be empty.")
        if not self.server_info:
            self.initialize()

        params = {
            "name": tool_name.strip(),
            "arguments": arguments
        }
        resp = self._rpc_call("tools/call", params)
        if not resp or "result" not in resp:
            raise PharosMCPError(code=-32603, message=f"Malformed tools/call response: {resp}")

        return resp["result"]

    @staticmethod
    def extract_sources(markdown_text: str) -> List[Dict[str, str]]:
        """
        Extracts structured source citations ([Title](URL)) from MCP markdown responses.
        Handles '# Sources' with or without trailing colon.
        """
        sources: List[Dict[str, str]] = []
        match = re.search(r"#+\s*Sources:?\s*(.*)", markdown_text, re.DOTALL | re.IGNORECASE)
        if match:
            sources_block = match.group(1)
            for m in re.finditer(r"-\s*\[(.*?)\]\((.*?)\)", sources_block):
                sources.append({
                    "title": m.group(1).strip(),
                    "url": m.group(2).strip()
                })
        return sources

    def ask_question(self, question: str, goal: Optional[str] = None) -> Dict[str, Any]:
        """
        Invokes the official `askQuestion` MCP tool.
        Returns synthesized markdown answer, timing, server info, and extracted source references.
        """
        if not question or not question.strip():
            raise ValueError("Question parameter cannot be empty.")

        args: Dict[str, Any] = {"question": question.strip()}
        effective_goal = goal.strip() if goal and goal.strip() else DEFAULT_GOAL
        args["goal"] = effective_goal

        start = time.time()
        tool_res = self.call_tool("askQuestion", args)
        elapsed = round(time.time() - start, 2)

        content_items = tool_res.get("content", [])
        text = "\n\n".join(item.get("text", "") for item in content_items if item.get("type") == "text")
        sources = self.extract_sources(text)

        return {
            "success": True,
            "tool": "askQuestion",
            "question": question.strip(),
            "goal": effective_goal,
            "endpoint": self.endpoint,
            "server_info": self.server_info,
            "elapsed_seconds": elapsed,
            "markdown_content": text,
            "sources": sources,
            "error": None,
            "raw": tool_res
        }

    def search(self, query: str) -> Dict[str, Any]:
        """
        Invokes the official `searchDocumentation` MCP tool.
        Returns matched documentation sections, titles, and direct links.
        """
        if not query or not query.strip():
            raise ValueError("Search query parameter cannot be empty.")

        start = time.time()
        tool_res = self.call_tool("searchDocumentation", {"query": query.strip()})
        elapsed = round(time.time() - start, 2)

        content_items = tool_res.get("content", [])
        text = "\n\n".join(item.get("text", "") for item in content_items if item.get("type") == "text")

        return {
            "success": True,
            "tool": "searchDocumentation",
            "query": query.strip(),
            "endpoint": self.endpoint,
            "server_info": self.server_info,
            "elapsed_seconds": elapsed,
            "markdown_content": text,
            "error": None,
            "raw": tool_res
        }

    def get_page(self, url: str) -> Dict[str, Any]:
        """
        Invokes the official `getPage` MCP tool to retrieve full page markdown.
        """
        if not url or not url.strip():
            raise ValueError("Page URL parameter cannot be empty.")

        start = time.time()
        tool_res = self.call_tool("getPage", {"url": url.strip()})
        elapsed = round(time.time() - start, 2)

        content_items = tool_res.get("content", [])
        text = "\n\n".join(item.get("text", "") for item in content_items if item.get("type") == "text")

        return {
            "success": True,
            "tool": "getPage",
            "url": url.strip(),
            "endpoint": self.endpoint,
            "server_info": self.server_info,
            "elapsed_seconds": elapsed,
            "markdown_content": text,
            "error": None,
            "raw": tool_res
        }

    def send_feedback(self, content: str, page_url: str, goal: Optional[str] = None) -> Dict[str, Any]:
        """
        Invokes the official `sendFeedback` MCP tool to report documentation issues.
        """
        if not content or not content.strip():
            raise ValueError("Feedback content cannot be empty.")
        if not page_url or not page_url.strip():
            raise ValueError("Page URL cannot be empty.")

        args: Dict[str, Any] = {
            "content": content.strip(),
            "pageUrl": page_url.strip()
        }
        if goal and goal.strip():
            args["goal"] = goal.strip()

        start = time.time()
        tool_res = self.call_tool("sendFeedback", args)
        elapsed = round(time.time() - start, 2)

        content_items = tool_res.get("content", [])
        text = "\n\n".join(item.get("text", "") for item in content_items if item.get("type") == "text")

        return {
            "success": True,
            "tool": "sendFeedback",
            "endpoint": self.endpoint,
            "server_info": self.server_info,
            "elapsed_seconds": elapsed,
            "markdown_content": text,
            "error": None,
            "raw": tool_res
        }

    def query(self, ask: str, goal: Optional[str] = None) -> Dict[str, Any]:
        """
        High-level compatibility method for Task 3 queries.
        Directly delegates to the Developer Docs MCP `askQuestion` tool.
        Never reverts to GitBook HTTP ask endpoints.
        """
        if not ask or not ask.strip():
            raise ValueError("Query parameter 'ask' cannot be empty.")

        effective_goal = goal.strip() if goal and goal.strip() else DEFAULT_GOAL
        try:
            return self.ask_question(ask, effective_goal)
        except Exception as e:
            return {
                "success": False,
                "tool": "askQuestion",
                "question": ask.strip(),
                "goal": effective_goal,
                "endpoint": self.endpoint,
                "server_info": self.server_info,
                "elapsed_seconds": 0.0,
                "markdown_content": "",
                "sources": [],
                "error": str(e),
                "raw": None
            }


# Backward-compatible alias for existing imports
PharosDocsClient = PharosDocsMCPClient
DEFAULT_DOCS_ENDPOINT = DEFAULT_DOCS_MCP_ENDPOINT


def main():
    parser = argparse.ArgumentParser(
        description="Query Pharos Developer Docs via the official Developer Docs MCP server."
    )
    parser.add_argument(
        "ask",
        type=str,
        nargs="?",
        default=None,
        help="Question to ask via Docs MCP askQuestion tool."
    )
    parser.add_argument(
        "--goal",
        type=str,
        default=None,
        help=f"High-level developer goal (default: '{DEFAULT_GOAL}')."
    )
    parser.add_argument(
        "--search",
        type=str,
        default=None,
        help="Search query across documentation using searchDocumentation tool."
    )
    parser.add_argument(
        "--page",
        type=str,
        default=None,
        help="Full URL of a page to fetch markdown content using getPage tool."
    )
    parser.add_argument(
        "--list-tools",
        action="store_true",
        help="Discover and display available tools on the Developer Docs MCP server."
    )
    parser.add_argument(
        "--endpoint",
        type=str,
        default=DEFAULT_DOCS_MCP_ENDPOINT,
        help=f"Docs MCP endpoint (default: '{DEFAULT_DOCS_MCP_ENDPOINT}')."
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"Request timeout in seconds (default: {DEFAULT_TIMEOUT})."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON instead of rendered Markdown."
    )

    args = parser.parse_args()

    client = PharosDocsMCPClient(endpoint=args.endpoint, timeout=args.timeout)

    # 1. List tools command
    if args.list_tools:
        try:
            client.initialize()
            tools = client.list_tools()
            if args.json:
                print(json.dumps({
                    "serverInfo": client.server_info,
                    "tools": tools
                }, indent=2))
            else:
                server_name = client.server_info.get("name", "Docs MCP") if client.server_info else "Docs MCP"
                print(f"=== Pharos Developer Docs MCP Tools ({server_name}) ===")
                for t in tools:
                    print(f"- {t['name']}: {t.get('description', '').strip()[:100]}...")
            return 0
        except Exception as e:
            print(f"[Docs MCP Error] {e}", file=sys.stderr)
            return 1

    # 2. Search command
    if args.search:
        try:
            res = client.search(args.search)
            if args.json:
                print(json.dumps(res, indent=2))
            else:
                print(f"=== Pharos Docs Search Results: '{args.search}' ({res['elapsed_seconds']}s) ===")
                print(res["markdown_content"])
            return 0
        except Exception as e:
            print(f"[Docs MCP Error] {e}", file=sys.stderr)
            return 1

    # 3. Get page command
    if args.page:
        try:
            res = client.get_page(args.page)
            if args.json:
                print(json.dumps(res, indent=2))
            else:
                print(f"=== Pharos Docs Page ({res['elapsed_seconds']}s) ===")
                print(res["markdown_content"])
            return 0
        except Exception as e:
            print(f"[Docs MCP Error] {e}", file=sys.stderr)
            return 1

    # 4. Ask Question (positional)
    if args.ask:
        res = client.query(args.ask, args.goal)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            if res["success"]:
                print(f"=== Pharos Developer Docs MCP Answer ({res['elapsed_seconds']}s) ===")
                print(res["markdown_content"])
                if res.get("sources"):
                    print("\n=== Sources ===")
                    for s in res["sources"]:
                        print(f"- {s['title']}: {s['url']}")
            else:
                print(f"[Docs MCP Error] {res['error']}", file=sys.stderr)
                return 1
        return 0

    # If no action provided
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
