"""Build identity defaults for source-tree development.

Packaging replaces this module in an isolated source copy. Runtime code must
never infer a packaged artifact's identity from an unrelated working tree.
"""

BUILD_CREATED = "UNKNOWN"
BUILD_REVISION = "UNKNOWN"
BUILD_SOURCE = "UNKNOWN"
