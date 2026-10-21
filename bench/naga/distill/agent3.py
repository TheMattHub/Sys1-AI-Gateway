"""AGENT3: find_tool queries as the agent writes them (round 5).

`python distill/agent3.py gen` (Python312, PYTHONPATH=ArenaPy, read-only): for every TEST3, TEST2 and HELD_OUT_2
request (never TRAIN2: the students trained on it), Claude Opus 5.5 gets naga's real MCP server instructions as the
system prompt, find_tool as its only tool (real description and schema from nagasim), the request as the user
message and tool_choice auto (Opus 5.5 refuses a forced one). The query argument of its first find_tool call is
the AGENT3 row, the seed's gold kept. No call = logged and dropped. Raw answers: distill/agent3_raw.jsonl, appended
(resumable). `python distill/agent3.py build` writes distill/agent3.jsonl (id, source, writer, query, gold).
`python distill/agent3.py derive` (PYTHONPATH=the naga clone, as round 4) writes distill/derived4 for
BENCH_ROUND=agent3 (results in distill/results4)."""
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "agent3_raw.jsonl"
MODEL = "claude-opus-5-5"


def seeds():
    q = json.loads((HERE / "derived3" / "tool_queries.json").read_text(encoding="utf-8"))
    who = {"TEST3": None, "TEST2": "Claude Sonnet 5.5", "HELD_OUT_2": "round-2 set"}
    return [{"seed": f"{s}-{i}", "source": s, "writer": r.get("writer") or who[s], "text": r["query"], "gold": r["gold"]}
            for s in ("TEST3", "TEST2", "HELD_OUT_2") for i, r in enumerate(q[s])]


def gen():
    sys.path.insert(0, str(HERE.parent))
    import anthropic
    import eng_anthropic
    from nagasim import mcp_server
    from nagasim.agent_tools.core import TOOLS
    ft = TOOLS["find_tool"]
    tool = {"name": "find_tool", "description": ft.description, "input_schema": ft.input_schema}
    client = anthropic.Anthropic(api_key=eng_anthropic._key(), max_retries=6)
    done = {json.loads(x)["seed"] for x in RAW.read_text(encoding="utf-8").splitlines()} if RAW.exists() else set()
    with RAW.open("a", encoding="utf-8") as f:
        for s in seeds():
            if s["seed"] in done:
                continue
            r = client.messages.create(model=MODEL, max_tokens=4000, system=mcp_server.INSTRUCTIONS, tools=[tool],
                                       tool_choice={"type": "auto"}, messages=[{"role": "user", "content": s["text"]}])
            call = next((b for b in r.content if b.type == "tool_use" and b.name == "find_tool"), None)
            u = r.usage
            f.write(json.dumps({**s, "query": call.input.get("query") if call else None, "limit": call.input.get("limit") if call else None,
                                "stop_reason": r.stop_reason,
                                "text": "".join(b.text for b in r.content if b.type == "text")[:500] if not call else None,
                                "tokens_in": u.input_tokens + (u.cache_read_input_tokens or 0) + (u.cache_creation_input_tokens or 0),
                                "cache_read": u.cache_read_input_tokens or 0, "cache_write": u.cache_creation_input_tokens or 0,
                                "tokens_out": u.output_tokens}) + "\n")
            f.flush()
    print("raw rows", len(RAW.read_text(encoding="utf-8").splitlines()), "of", len(seeds()), flush=True)


def build():
    raw = [json.loads(x) for x in RAW.read_text(encoding="utf-8").splitlines()]
    order = {s["seed"]: i for i, s in enumerate(seeds())}
    raw.sort(key=lambda r: order[r["seed"]])
    keep = [r for r in raw if r["query"]]
    (HERE / "agent3.jsonl").write_text("".join(json.dumps(
        {"id": f"AGENT3-{i}", "seed": r["seed"], "source": r["source"], "writer": r["writer"], "query": r["query"],
         "gold": r["gold"]}) + "\n" for i, r in enumerate(keep)), encoding="utf-8")
    print(json.dumps({"seeds": len(raw), "kept": len(keep), "dropped_no_call": [r["seed"] for r in raw if not r["query"]]}))


def derive():
    from nagasim import toolsearch
    from nagasim.agent_tools.discover import catalogue_index
    idx = catalogue_index()
    rows = [json.loads(x) for x in (HERE / "agent3.jsonl").read_text(encoding="utf-8").splitlines()]
    out = []
    for r in rows:
        ranked = [c["name"] for c in toolsearch.search(idx, r["query"], limit=90)]
        out.append({"query": r["query"], "gold": r["gold"], "source": r["source"], "writer": r["writer"],
                    "candidates": ranked[:10], "ranked_all": ranked})
    der = HERE / "derived4"
    der.mkdir(exist_ok=True)
    shutil.copy(HERE / "derived" / "tools.json", der / "tools.json")
    (der / "tool_queries.json").write_text(json.dumps({"AGENT3": out}, indent=1), encoding="utf-8")
    print("AGENT3 gold in find_tool's top 10:", sum(any(g in o["candidates"] for g in o["gold"]) for o in out), "of", len(out))


if __name__ == "__main__":
    {"gen": gen, "build": build, "derive": derive}[sys.argv[1]]()
