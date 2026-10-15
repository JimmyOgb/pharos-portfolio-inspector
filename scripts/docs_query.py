#!/usr/bin/env python3
"""
Pharos Developer Docs MCP Query Helper
Implements the official GitBook dynamic agentic query interface documented in:
https://docs.pharos.xyz/llms-full.txt

Interface:
    GET https://docs.pharos.xyz/index.md?ask=<question>&goal=<user_goal>

Requirements:
    Zero external dependencies (Python 3.10+ standard library only: urllib, json, argparse).
    Zero cost ($0.00).
"""

import sys
import json
import time
import argparse
import urllib.request
import urllib.parse
from typing import Dict, Any, Optional

DEFAULT_DOCS_ENDPOINT = "https://docs.pharos.xyz/index.md"
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PharosDocsClient/1.0"
DEFAULT_GOAL = "develop and verify autonomous AI agents on Pharos"


class PharosDocsClient:
    """Client for querying official Pharos Developer Docs agentic API."""

    def __init__(
        self,
        endpoint: str = DEFAULT_DOCS_ENDPOINT,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout: int = 25
    ):
        self.endpoint = endpoint
        self.user_agent = user_agent
        self.timeout = timeout

    def build_query_url(self, ask: str, goal: Optional[str] = None) -> str:
        """Constructs the canonical GitBook query URL with ask and goal parameters."""
        effective_goal = goal if goal else DEFAULT_GOAL
        params = urllib.parse.urlencode({
            "ask": ask.strip(),
            "goal": effective_goal.strip()
        })
        base = self.endpoint.split("?")[0]
        return f"{base}?{params}"

    def query(self, ask: str, goal: Optional[str] = None) -> Dict[str, Any]:
        """
        Executes a dynamic documentation query and returns structured results.

        Returns:
            dict containing:
                - success: bool
                - ask: str
                - goal: str
                - endpoint: str
                - http_status: int
                - elapsed_seconds: float
                - markdown_content: str (parsed response)
                - error: Optional[str]
        """
        if not ask or not ask.strip():
            raise ValueError("Query parameter 'ask' cannot be empty.")

        effective_goal = goal if goal else DEFAULT_GOAL
        query_url = self.build_query_url(ask, effective_goal)
        start_time = time.time()

        req = urllib.request.Request(
            query_url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "text/markdown, text/plain, application/json"
            },
            method="GET"
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw_bytes = resp.read()
                elapsed = round(time.time() - start_time, 2)
                markdown_text = raw_bytes.decode("utf-8", errors="replace")

                return {
                    "success": True,
                    "ask": ask,
                    "goal": effective_goal,
                    "endpoint": query_url,
                    "http_status": resp.status,
                    "elapsed_seconds": elapsed,
                    "markdown_content": markdown_text,
                    "error": None
                }
        except urllib.error.HTTPError as e:
            elapsed = round(time.time() - start_time, 2)
            error_body = ""
            try:
                error_body = e.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            return {
                "success": False,
                "ask": ask,
                "goal": effective_goal,
                "endpoint": query_url,
                "http_status": e.code,
                "elapsed_seconds": elapsed,
                "markdown_content": "",
                "error": f"HTTP {e.code}: {e.reason}. {error_body[:200]}"
            }
        except Exception as e:
            elapsed = round(time.time() - start_time, 2)
            return {
                "success": False,
                "ask": ask,
                "goal": effective_goal,
                "endpoint": query_url,
                "http_status": 0,
                "elapsed_seconds": elapsed,
                "markdown_content": "",
                "error": str(e)
            }


def main():
    parser = argparse.ArgumentParser(
        description="Query Pharos Developer Docs via official GitBook agentic API."
    )
    parser.add_argument(
        "ask",
        type=str,
        nargs="?",
        default=None,
        help="Question to query the documentation with."
    )
    parser.add_argument(
        "--goal",
        type=str,
        default=None,
        help=f"High-level developer goal (default: '{DEFAULT_GOAL}')."
    )
    parser.add_argument(
        "--endpoint",
        type=str,
        default=DEFAULT_DOCS_ENDPOINT,
        help=f"Base documentation endpoint (default: '{DEFAULT_DOCS_ENDPOINT}')."
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=25,
        help="Network request timeout in seconds (default: 25)."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON instead of rendered Markdown."
    )

    args = parser.parse_args()

    if not args.ask:
        parser.print_help()
        sys.exit(1)

    client = PharosDocsClient(endpoint=args.endpoint, timeout=args.timeout)
    result = client.query(args.ask, args.goal)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if result["success"]:
            print(f"=== Pharos Developer Docs Answer ({result['elapsed_seconds']}s) ===")
            print(result["markdown_content"])
        else:
            print(f"[Docs Query Error] {result['error']}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
