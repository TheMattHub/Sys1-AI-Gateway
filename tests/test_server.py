"""End-to-end: spawn the MCP server over stdio and speak JSON-RPC to it."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def rpc(id_, method, params=None):
    msg = {"jsonrpc": "2.0", "method": method, "params": params or {}}
    if id_ is not None:
        msg["id"] = id_
    return json.dumps(msg)


class StdioServerTests(unittest.TestCase):
    def test_instructions_say_when_not_to_use(self):
        from system1_gateway.server import INSTRUCTIONS
        for word in ("writing", "maths", "dates"):
            self.assertIn(word, INSTRUCTIONS)

    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.toml"
            config.write_text('[gateway]\nprovider = "mock"\n', encoding="utf-8")
            lines = [
                rpc(1, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                      "clientInfo": {"name": "test", "version": "0"}}),
                rpc(None, "notifications/initialized"),
                rpc(2, "tools/list"),
                rpc(3, "tools/call", {"name": "system1_decide",
                                      "arguments": {"question": "Tabs or spaces?", "options": ["spaces", "tabs"]}}),
                rpc(4, "tools/call", {"name": "system1_health"}),
                rpc(5, "tools/call", {"name": "system1_decide", "arguments": {"question": ""}}),
                rpc(6, "no/such/method"),
                rpc(7, "ping"),
                "this is not json",
            ]
            # cwd outside the repo + PYTHONPATH: the server must not depend on the caller's directory.
            proc = subprocess.run([sys.executable, "-m", "system1_gateway"], input="\n".join(lines) + "\n",
                                  capture_output=True, text=True, encoding="utf-8", timeout=30, cwd=tmp,
                                  env={**os.environ, "PYTHONPATH": str(REPO), "SYSTEM1_CONFIG": str(config),
                                       "SYSTEM1_INSTALL_DIR": str(Path(config).parent)})  # not the real pause file
        self.assertEqual(proc.returncode, 0, proc.stderr)
        responses = [json.loads(line) for line in proc.stdout.splitlines()]  # stdout is pure JSON-RPC
        by_id = {r["id"]: r for r in responses}
        self.assertEqual(len(responses), 8)  # 7 requests + 1 parse error; the notification gets no reply

        self.assertEqual(by_id[1]["result"]["protocolVersion"], "2025-06-18")
        self.assertEqual({t["name"] for t in by_id[2]["result"]["tools"]},
                         {"system1_decide", "system1_health", "system1_capabilities"})
        decided = by_id[3]["result"]
        self.assertFalse(decided["isError"])
        self.assertEqual(decided["structuredContent"]["decision"], "spaces")
        self.assertEqual(json.loads(decided["content"][0]["text"]), decided["structuredContent"])
        self.assertEqual(by_id[4]["result"]["structuredContent"]["status"], "ok")
        self.assertTrue(by_id[5]["result"]["isError"])
        self.assertEqual(by_id[6]["error"]["code"], -32601)
        self.assertEqual(by_id[7]["result"], {})
        self.assertEqual(by_id[None]["error"]["code"], -32700)


if __name__ == "__main__":
    unittest.main()
