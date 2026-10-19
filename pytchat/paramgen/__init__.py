"""Chat continuation tokens.

`resolver` is the only module here now. The two that used to sit beside it
(`liveparam`, `arcparam`) *generated* tokens by re-encoding a protobuf that
YouTube no longer accepts: measured on a live stream, a generated token returned
zero chat items while the page's own token returned dozens, on the same video,
in the same second. They are deleted rather than kept as a fallback, because a
fallback that silently yields an empty chat is worse than an error.
"""

from . import resolver  # noqa: F401

__all__ = ["resolver"]
