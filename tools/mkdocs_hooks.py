"""mkdocs hooks for the docs site (dev only; the gateway never imports this).

- A link from a page to a repository file outside docs/ (a script, a skill, the bench) becomes a link to
  that file on GitHub, so the same relative link works in the GitHub view and on the site.
- After the build: a Markdown copy of every page next to its HTML (linked with rel="alternate"),
  llms.txt (every page in menu order with its first sentence) and llms-full.txt (the whole site as one file).
- schema/request.json and schema/response.json, written from system1_gateway/schema.py, so they never drift.
"""
import json
import posixpath
import re
import sys
from pathlib import Path

REPO_URL = "https://github.com/TheMattHub/Sys1-AI-Gateway/blob/main/"
_LINK = re.compile(r"(\]\()([^)\s#]+)(#[^)\s]*)?(\))")
_pages: dict = {}  # src_uri -> Markdown as written
_nav = None


def _to_github(match, src_uri: str) -> str:
    target = match.group(2)
    if "://" in target or target.startswith(("mailto:", "/")):
        return match.group(0)
    resolved = posixpath.normpath(posixpath.join("docs", posixpath.dirname(src_uri), target))
    if resolved.startswith("docs/"):
        return match.group(0)
    return f"{match.group(1)}{REPO_URL}{resolved}{match.group(3) or ''}{match.group(4)}"


def on_nav(nav, config, files):
    global _nav
    _nav = nav
    return nav


def on_page_markdown(markdown, page, config, files):
    text = _LINK.sub(lambda m: _to_github(m, page.file.src_uri), markdown)
    _pages[page.file.src_uri] = text
    return text


def on_post_page(output, page, config):
    tag = f'<link rel="alternate" type="text/markdown" href="{Path(page.file.src_uri).name}">'
    return output.replace("</head>", tag + "</head>", 1)


def _first_sentence(text: str) -> str:
    for block in text.split("\n\n"):
        block = block.strip()
        if block and not block.startswith(("#", "!", "[!", "|", "```", "<", "-", ">")):
            block = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", " ".join(block.split()))
            return re.split(r"(?<=[.?])\s+(?=[A-Z])", block, maxsplit=1)[0]
    return ""


def on_post_build(config):
    site = Path(config["site_dir"])
    base = config["site_url"].rstrip("/") + "/"
    for src_uri, text in _pages.items():
        (site / src_uri).write_text(text, encoding="utf-8", newline="\n")
    index = [f"# {config['site_name']}", "", f"> {config['site_description']}.", "",
             "Every page has a Markdown copy at its address with .md in place of .html. "
             "The whole site as one file: llms-full.txt.", ""]
    full = [f"# {config['site_name']}: full documentation", "", f"> {config['site_description']}.", ""]
    for item in _nav.items:
        pages = item.children if item.is_section else [item]
        index += [f"## {item.title}", ""]
        for page in pages:
            text = _pages.get(page.file.src_uri, "")
            url = base + page.file.src_uri[:-3] + ".html"
            index.append(f"- [{page.title}]({url}): {_first_sentence(text)}")
            full += ["---", "", f"Page: {page.title}", f"URL: {url}", "", text]
        index.append("")
    (site / "llms.txt").write_text("\n".join(index), encoding="utf-8", newline="\n")
    (site / "llms-full.txt").write_text("\n".join(full), encoding="utf-8", newline="\n")
    sys.path.insert(0, str(Path(config.config_file_path).parent))
    from system1_gateway import schema
    (site / "schema").mkdir(exist_ok=True)
    for name, value in (("request", schema.REQUEST_JSON_SCHEMA), ("response", schema.RESPONSE_JSON_SCHEMA)):
        (site / "schema" / f"{name}.json").write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
