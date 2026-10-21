"""A hosted Claude model as the engine (Anthropic API): `python eng_anthropic.py haiku`.

Same item, same options and documents, same one instruction (common.question) as every other engine. The
model answers through one forced tool call with its three best option names in order, so top-1 and top-3
score like the others and a plain retry is the next name (the retry rule of the bench). All options go
as they are: no shortlist, the 90 tool documents fit in one prompt. The options block is cached, so
the 79 queries over the same 90 tools pay for it once.

Needs the `anthropic` package and ANTHROPIC_API_KEY. On Windows the key may live in the user's
environment only (setx, before the shell started); it is read from there too, never written anywhere."""
import os
import sys

import common

MODELS = {"haiku": "claude-haiku-5-5", "sonnet": "claude-sonnet-5-5", "opus": "claude-opus-5-5"}


def _key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key and sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                key = winreg.QueryValueEx(k, "ANTHROPIC_API_KEY")[0]
        except OSError:
            key = None
    if not key:
        raise SystemExit("ANTHROPIC_API_KEY is not set")
    return key


def make(model: str):
    import anthropic
    client = anthropic.Anthropic(api_key=_key(), max_retries=6)

    def decide(it):
        opts = it["options"]
        listing = "\n".join(f"- {it['docs'][o]}" for o in opts)
        tool = {"name": "choose", "description": "Give the best options, best first.",
                "input_schema": {"type": "object", "required": ["ranking"], "properties": {
                    "ranking": {"type": "array", "minItems": 1, "maxItems": 3,
                                "items": {"type": "string", "enum": list(opts)},
                                "description": "Up to three option names, best first."}}}}
        # Opus 5.5 refuses a forced tool_choice (400) and its thinking cannot be turned off: it gets tool_choice
        # auto and one more line asking for the call; its thinking needs room, so max_tokens is larger.
        forced = not model.startswith("claude-opus-5")
        ask = "" if forced else "\nAnswer only by calling the choose tool."
        r = client.messages.create(
            model=model, max_tokens=200 if forced else 4000, tools=[tool],
            tool_choice={"type": "tool", "name": "choose"} if forced else {"type": "auto"},
            system=[{"type": "text", "text": f"{common.question(it)}{ask}\nOptions (name: what it is):\n{listing}",
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": it["text"]}])
        ranking = next(b.input["ranking"] for b in r.content if b.type == "tool_use")
        u = r.usage
        return {"ranking": [x for x in ranking if x in opts], "confidence": 0.0,
                "tokens_in": u.input_tokens + (u.cache_read_input_tokens or 0) + (u.cache_creation_input_tokens or 0),
                "tokens_out": u.output_tokens, "cache_read": u.cache_read_input_tokens or 0,
                "cache_write": u.cache_creation_input_tokens or 0}
    return decide


if __name__ == "__main__":
    name = sys.argv[1]
    common.run(name, make(MODELS[name]))
