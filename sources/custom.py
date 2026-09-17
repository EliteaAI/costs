"""Custom source — no upstream catalog, always empty.

Selecting this source means the admin manages the whole price table by hand.
`fetch()` intentionally returns no entries; callers must treat that as the
correct outcome for this source, not a failure (see `rpc/refresh.py`).
"""

SOURCE_ID = "custom"


class CustomSource:
    id = SOURCE_ID

    def fetch(self) -> list:
        return []
