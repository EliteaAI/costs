"""Daily catalog refresh RPC.

Resolves the configured source from the generic registry, fetches canonical
entries, and applies the upsert rule (custom rows keep their effective prices).
On any fetch error it falls back to the bundled offline seed, so a no-internet /
air-gapped deployment still refreshes from a known-good snapshot.
"""

from pylon.core.tools import web, log

from ..sources import registry
from ..utils import cache, catalog, settings


class RPC:
    @web.rpc("costs_refresh_catalog", "refresh_catalog")
    def refresh_catalog(self, source_id: str = None, **kwargs) -> dict:
        source_id = source_id or settings.get_active_source()
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

    @web.rpc("costs_reimport_catalog", "reimport_catalog")
    def reimport_catalog(self, source_id: str = None, **kwargs) -> dict:
        """Destructive re-import: fetch first, then wipe+replace the whole table.

        Aborts (no wipe) if the source is unknown or returns no entries, so a
        failed fetch can never empty the catalog.
        """
        source_id = source_id or settings.get_active_source()
        source = registry.get(source_id)
        if source is None:
            return {"error": "unknown_source", "source": source_id, "cached": cache.count()}

        try:
            entries = source.fetch()
        except Exception as e:  # pylint: disable=W0703
            log.warning("costs.reimport: source %r failed: %s", source_id, e)
            return {"error": "fetch_failed", "source": source_id, "cached": cache.count()}

        if not entries:
            log.error("costs.reimport: source %r returned no entries; aborting wipe", source_id)
            return {"error": "empty_fetch", "source": source_id, "cached": cache.count()}

        counts = catalog.replace_entries(entries, source_id)
        cache.reload()
        result = {"source": source_id, "counts": counts, "cached": cache.count()}
        log.info("costs.reimport: done %s", result)
        return result
