#!/usr/bin/env python3
"""
MCP Bridge: stdio transport <-> Streamable HTTP transport

Connects Claude Code (stdio MCP) to Tencent Docs MCP API (HTTP).
Reads JSON-RPC requests from stdin, forwards to remote HTTP endpoint,
and writes responses back to stdout.
"""

import sys
import json
import os

import requests

# Configuration from environment or .mcp.json
MCP_URL = os.environ.get(
    "TENCENTDOCS_MCP_URL",
    "https://docs.qq.com/openapi/mcp",
)
AUTH_TOKEN = os.environ.get(
    "TENCENTDOCS_AUTH_TOKEN",
    "3fc6ae349620458b98e1440ff0f7d076",
)

HEADERS = {
    "Content-Type": "application/json",
    "Authorization": AUTH_TOKEN,
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def log_stderr(msg: str) -> None:
    """Log to stderr so it doesn't interfere with MCP protocol on stdout."""
    print(f"[mcp-bridge] {msg}", file=sys.stderr, flush=True)


def main() -> None:
    log_stderr(f"Starting MCP bridge to {MCP_URL}")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        request_id = None
        try:
            request = json.loads(line)
            request_id = request.get("id")
            method = request.get("method", "unknown")

            log_stderr(f"-> {method}")

            response = SESSION.post(
                MCP_URL,
                json=request,
                timeout=60,
            )
            response.raise_for_status()
            result = response.json()

            if "result" in result:
                log_stderr(f"<- {method}: OK")
            elif "error" in result:
                log_stderr(f"<- {method}: ERROR - {result['error'].get('message', 'unknown')}")

            sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
            sys.stdout.flush()

        except json.JSONDecodeError as e:
            log_stderr(f"JSON parse error: {e}")
            error_response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32700, "message": f"Parse error: {e}"},
            }
            sys.stdout.write(json.dumps(error_response) + "\n")
            sys.stdout.flush()
        except requests.RequestException as e:
            log_stderr(f"HTTP error: {e}")
            error_response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32603, "message": f"Transport error: {e}"},
            }
            sys.stdout.write(json.dumps(error_response) + "\n")
            sys.stdout.flush()

    log_stderr("Bridge shutting down")


if __name__ == "__main__":
    main()
