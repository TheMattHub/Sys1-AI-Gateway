"""MCP server over stdio: newline-delimited JSON-RPC 2.0, stdlib only.

stdout carries protocol messages only; all logging goes to stderr (and optionally a file).
"""

import json
import logging
import sys
from pathlib import Path

from . import __version__
from .gateway import Gateway
from .schema import REQUEST_JSON_SCHEMA

log = logging.getLogger("system1_gateway")

PROTOCOL_VERSIONS = ("2024-11-05", "2025-03-26", "2025-06-18")

INSTRUCTIONS = (
    "System-1 gateway: fast, intuitive decisions for low-stakes judgement calls. "
    "Call system1_decide with a question (and options when there is a fixed set). "
    "If status is 'abstained' or 'error', reason it through yourself instead. "
    "Not for writing, chat, multi-step reasoning, counting, maths or dates: do those yourself and ask it only "
    "the judgement call."
)

_NO_ARGS = {"type": "object", "properties": {}, "additionalProperties": False}

TOOLS = [
    {"name": "system1_decide",
     "description": "Ask the configured System-1 provider for a fast decision. Returns status "
                    "decided | abstained | error, with decision, confidence (0-1), rationale and request_id.",
     "inputSchema": REQUEST_JSON_SCHEMA},
    {"name": "system1_health",
     "description": "Check gateway and provider health (ok | degraded | down).",
     "inputSchema": _NO_ARGS},
    {"name": "system1_capabilities",
     "description": "Describe the gateway: version, schema versions, provider chain, thresholds and JSON schemas.",
     "inputSchema": _NO_ARGS},
]


class RpcError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def _tool_result(payload: dict, is_error: bool = False) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
            "structuredContent": payload, "isError": is_error}


class Server:
    def __init__(self, gateway: Gateway):
        self.gateway = gateway

    def handle(self, msg):
        """Return the JSON-RPC response for msg, or None when no response is due."""
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
            return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}
        if "method" not in msg:
            return None  # a response to a server->client request; we never send any
        is_notification = "id" not in msg
        try:
            params = msg.get("params") or {}
            if not isinstance(msg["method"], str) or not isinstance(params, dict):
                raise RpcError(-32600, "Invalid Request")
            result = self._dispatch(msg["method"], params)
        except RpcError as e:
            error = {"code": e.code, "message": str(e)}
        except Exception as e:
            log.exception("internal error handling %r", msg.get("method"))
            error = {"code": -32603, "message": f"Internal error: {type(e).__name__}"}
        else:
            return None if is_notification else {"jsonrpc": "2.0", "id": msg["id"], "result": result}
        return None if is_notification else {"jsonrpc": "2.0", "id": msg["id"], "error": error}

    def _dispatch(self, method: str, params: dict):
        if method.startswith("notifications/"):
            return None
        if method == "initialize":
            requested = params.get("protocolVersion")
            return {
                "protocolVersion": requested if requested in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[-1],
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "system1-gateway", "version": __version__},
                "instructions": INSTRUCTIONS,
            }
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": TOOLS}
        if method == "tools/call":
            name, args = params.get("name"), params.get("arguments") or {}
            if name == "system1_decide":
                payload = self.gateway.decide(args)
                return _tool_result(payload, is_error=payload["status"] == "error")
            if name == "system1_health":
                return _tool_result(self.gateway.health())
            if name == "system1_capabilities":
                return _tool_result(self.gateway.capabilities())
            raise RpcError(-32602, f"Unknown tool: {name!r}")
        raise RpcError(-32601, f"Method not found: {method}")


def _setup_logging(config):
    handlers = [logging.StreamHandler(sys.stderr)]
    file_error = None
    if config.log_file:
        try:
            handlers.append(logging.FileHandler(Path(config.log_file).expanduser(), encoding="utf-8"))
        except OSError as e:
            file_error = e
    logging.basicConfig(level=config.log_level, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if file_error:
        log.warning("cannot open log_file %r: %s", config.log_file, file_error)


def main():
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    gateway = Gateway()
    _setup_logging(gateway.config)
    for problem in gateway.config_errors:
        log.error("config error: %s", problem)
    log.info("system1-gateway %s started: provider=%s fallback=%s config=%s", __version__,
             gateway.config.provider, gateway.config.fallback, gateway.config.source or "(defaults)")

    server = Server(gateway)
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        else:
            response = server.handle(msg)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()
