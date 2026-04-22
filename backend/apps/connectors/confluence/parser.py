"""
Converts Atlassian Confluence storage format (XHTML with ac: macros) to clean Markdown.
"""

from bs4 import BeautifulSoup, NavigableString, Tag


def parse_storage_to_markdown(storage_xml: str) -> str:
    soup = BeautifulSoup(storage_xml, "lxml")

    # Remove noise tags entirely (content + tag)
    for tag in soup.find_all(["script", "style", "ac:parameter"]):
        tag.decompose()

    return _node_to_md(soup).strip()


def _node_to_md(node) -> str:
    if isinstance(node, NavigableString):
        return str(node)

    parts = []
    for child in node.children:
        parts.append(_node_to_md(child))
    inner = "".join(parts)

    if not isinstance(node, Tag):
        return inner

    name = node.name.lower() if node.name else ""

    # Headings
    if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
        level = int(name[1])
        return f"\n{'#' * level} {inner.strip()}\n"

    # Block elements
    if name == "p":
        stripped = inner.strip()
        return f"\n{stripped}\n" if stripped else ""

    if name in ("ul", "ol"):
        return "\n" + inner + "\n"

    if name == "li":
        # Determine if parent is ol
        parent = node.parent
        if parent and getattr(parent, "name", "") == "ol":
            siblings = [c for c in parent.children if isinstance(c, Tag) and c.name == "li"]
            idx = siblings.index(node) + 1
            prefix = f"{idx}. "
        else:
            prefix = "- "
        return f"{prefix}{inner.strip()}\n"

    # Inline formatting
    if name in ("strong", "b"):
        return f"**{inner}**"

    if name in ("em", "i"):
        return f"_{inner}_"

    if name == "code":
        return f"`{inner}`"

    if name == "pre":
        return f"\n```\n{inner.strip()}\n```\n"

    if name == "a":
        href = node.get("href", "")
        text = inner.strip() or href
        return f"[{text}]({href})"

    if name == "br":
        return "\n"

    if name == "hr":
        return "\n---\n"

    # Tables
    if name == "table":
        return _table_to_md(node)

    # Atlassian macros
    if name == "ac:structured-macro":
        body = node.find("ac:rich-text-body")
        if body:
            return _node_to_md(body)
        return ""

    if name == "ac:image":
        # inner already contains the ri:attachment rendering
        return inner if inner.strip() else "[image]"

    if name == "ri:attachment":
        filename = node.get("ri:filename", "image")
        return f"[image: {filename}]"

    if name == "ac:link":
        page = node.find("ri:page")
        alias = node.find("ac:plain-text-link-body")
        alias_text = alias.get_text() if alias else None
        page_title = page.get("ri:content-title", "") if page else ""
        title = alias_text or page_title
        return f"[{title}]" if title else inner

    # Structural wrappers — pass through
    if name in ("div", "span", "body", "html", "ac:rich-text-body", "[document]"):
        return inner

    # Unknown tags — keep text, drop tag
    return inner


def _table_to_md(table: Tag) -> str:
    rows = table.find_all("tr")
    if not rows:
        return ""

    def cell_text(cell: Tag) -> str:
        return _node_to_md(cell).strip().replace("\n", " ").replace("|", "\\|")

    result_rows = []
    for i, row in enumerate(rows):
        cells = row.find_all(["th", "td"])
        row_md = "| " + " | ".join(cell_text(c) for c in cells) + " |"
        result_rows.append(row_md)
        if i == 0:
            sep = "| " + " | ".join("---" for _ in cells) + " |"
            result_rows.append(sep)

    return "\n" + "\n".join(result_rows) + "\n"
