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
