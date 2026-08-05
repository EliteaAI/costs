"""Daily catalog refresh RPC.

Resolves the configured source from the generic registry, fetches canonical
entries, and applies the upsert rule (custom rows keep their effective prices).
On any fetch error it falls back to the bundled offline seed, so a no-internet /
air-gapped deployment still refreshes from a known-good snapshot.
"""

from pylon.core.tools import web, log

from ..sources import registry
from ..utils import cache, catalog


class RPC:
    @web.rpc("costs_refresh_catalog", "refresh_catalog")
    def refresh_catalog(self, source_id: str = None, **kwargs) -> dict:
        source_id = source_id or registry.DEFAULT_SOURCE_ID
        source = registry.get(source_id)

        entries = []
        used = source_id
        if source is not None:
            try:
                entries = source.fetch()
            except Exception as e:  # pylint: disable=W0703
                log.warning("costs.refresh: source %r failed: %s", source_id, e)
                entries = []

        if not entries:
            fallback = registry.get(registry.FALLBACK_SOURCE_ID)
            if fallback is not None:
                entries = fallback.fetch()
                used = registry.FALLBACK_SOURCE_ID
                log.info("costs.refresh: fell back to %r", used)

        if not entries:
            log.error("costs.refresh: no entries from %r or fallback", source_id)
            return {"source": used, "counts": None, "cached": cache.count()}

        counts = catalog.upsert_entries(entries, used)
        cache.reload()
        result = {"source": used, "counts": counts, "cached": cache.count()}
        log.info("costs.refresh: done %s", result)
        return result
