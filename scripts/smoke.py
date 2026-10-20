"""Check an installed System-1 gateway over stdio, launched exactly as Claude Code launches it.

    python scripts/smoke.py                                    # handshake + health
    python scripts/smoke.py --question "Rerun or block?" --options rerun block
    python scripts/smoke.py --python /path/to/venv/python      # check a different install

Exit 0 when the handshake works, health is "ok" and the decision (if asked) is not an error.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def default_python() -> Path:
    venv = Path(os.environ.get("SYSTEM1_INSTALL_DIR") or Path.home() / ".system1-gateway") / "venv"
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def rpc(id_, method, params=None) -> str:
    msg = {"jsonrpc": "2.0", "method": method, "params": params or {}}
    if id_ is not None:
        msg["id"] = id_
    return json.dumps(msg)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--python", default=str(default_python()), help="gateway interpreter (default: installed venv)")
    parser.add_argument("--question", help="also run one sample system1_decide")
    parser.add_argument("--options", nargs="+", help="options for the sample decision")
    args = parser.parse_args()

    if not Path(args.python).is_file():
        print(f"NOT INSTALLED: {args.python} does not exist. Run install.ps1 / install.sh.")
        return 2

    lines = [
        rpc(1, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                              "clientInfo": {"name": "system1-smoke", "version": "1"}}),
        rpc(None, "notifications/initialized"),
        rpc(2, "tools/list"),
        rpc(3, "tools/call", {"name": "system1_health", "arguments": {}}),
    ]
    if args.question:
        decide_args = {"question": args.question, "request_id": "smoke"}
        if args.options:
            decide_args["options"] = args.options
        lines.append(rpc(4, "tools/call", {"name": "system1_decide", "arguments": decide_args}))

    # Same flags and a neutral cwd, as Claude Code would run it from some unrelated project.
    proc = subprocess.run([args.python, "-I", "-m", "system1_gateway"], input="\n".join(lines) + "\n",
                          capture_output=True, text=True, encoding="utf-8", timeout=120, cwd=tempfile.gettempdir())
    try:
        by_id = {r.get("id"): r for r in map(json.loads, proc.stdout.splitlines())}
        server = by_id[1]["result"]["serverInfo"]
        tools = [t["name"] for t in by_id[2]["result"]["tools"]]
        health = by_id[3]["result"]["structuredContent"]
    except (ValueError, KeyError, TypeError) as e:
        print(f"HANDSHAKE FAILED ({type(e).__name__}: {e}); exit code {proc.returncode}")
        print("stdout:\n" + proc.stdout + "\nstderr:\n" + proc.stderr)
        return 1

    print(f"server:  {server['name']} {server['version']}")
    print(f"tools:   {', '.join(tools)}")
    print("health:  " + json.dumps(health, indent=2))
    ok = health["status"] == "ok"
    if args.question:
        decision = by_id[4]["result"]["structuredContent"]
        print("decide:  " + json.dumps(decision, indent=2))
        ok = ok and decision["status"] != "error"
    print("log:\n" + proc.stderr.rstrip())
    print("RESULT:  " + ("OK" if ok else "PROBLEM (see health/decide above)"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
