"""Shared constants for the skills app.

Centralises magic numbers so they can be referenced consistently across
modules and tested in one place.
"""

# Maximum bytes for inline output returned in the API response.
# Larger outputs are stored in GCS and the URI is returned instead.
MAX_OUTPUT_BYTES_INLINE = 32_768

# Maximum number of characters to include in the indexed text for
# semantic discovery embedding. Text beyond this limit is truncated.
MAX_INDEXED_TEXT_CHARS = 20_000

# ── AI-assisted skill writing limits ──────────────────────────────────────

# Maximum number of AI-assisted skill generations allowed per org per day.
# This limit is enforced to protect Vertex AI credits and prevent abuse.
AI_SKILL_GENERATION_LIMIT_PER_DAY = 10

# Rate limit for AI-assisted file edits (stream_ai_edit): requests per org per hour.
AI_FILE_EDIT_LIMIT_PER_HOUR = 30
