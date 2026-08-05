"""Manual-upload source (stub).

Wired in M3: an admin uploads a canonical/CSV/JSON payload which is staged and
returned here as canonical entries. For now it holds an in-memory staged batch.
"""

from .base import CanonicalEntry

SOURCE_ID = "upload"

_staged: list = []


def stage(entries: list) -> None:
    global _staged
    _staged = list(entries)


class UploadSource:
    id = SOURCE_ID

    def fetch(self) -> list:
        return [
            e if isinstance(e, CanonicalEntry) else CanonicalEntry(**e)
            for e in _staged
        ]
