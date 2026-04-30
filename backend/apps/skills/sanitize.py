"""Input sanitization for skill content fields.

Strips dangerous HTML tags and scripts from user-supplied content before
persistence.  Skill ``content_md`` is stored as a TextField and rendered
as-is — if a user injects ``<script>`` or ``<img onerror>`` tags they
would execute in the context of any viewer, so we sanitize at write time.
"""

import re


def _strip_tags(text: str) -> str:
    """Remove all HTML tags from *text*.

    Runs in a loop until stable so that nested/broken markup like
    ``<scr<script>ipt>`` is fully removed.
    """
    while True:
        cleaned = re.sub(r"<[^>]*>", "", text)
        if cleaned == text:
            return cleaned
        text = cleaned


def sanitize_content_md(text: str) -> str:
    """Sanitize ``content_md`` text.

    Returns the text with all HTML tags removed.  If the caller passes a
    long string it is truncated to 20 000 characters (the same limit used
    for embedding indexing).
    """
    from apps.skills.constants import MAX_INDEXED_TEXT_CHARS

    clean = _strip_tags(text)
    # Truncate to the same limit used for discovery embeddings so the
    # field never grows beyond what we can index.
    return clean[:MAX_INDEXED_TEXT_CHARS]


def sanitize_frontmatter(text: str) -> str:
    """Sanitize frontmatter YAML text.

    Frontmatter is expected to be YAML — strip any HTML that might sneak
    in from AI-generated content.
    """
    return _strip_tags(text)[:50_000]


def sanitize_description(text: str) -> str:
    """Sanitize the skill description field."""
    return _strip_tags(text)[:2000]
