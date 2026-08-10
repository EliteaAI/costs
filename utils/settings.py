"""Plugin settings accessors — the persisted active price source.

The active source drives both the daily refresh cron (when called with no
explicit source_id) and the admin selector. Defaults to the registry default
(litellm) when unset.
"""

from pylon.core.tools import log

from ..sources import registry

_SETTINGS_ID = 1


def get_active_source() -> str:
    from tools import db
    from ..models.costs_setting import CostsSetting

    with db.with_project_schema_session(None) as session:
        row = session.query(CostsSetting).filter(CostsSetting.id == _SETTINGS_ID).first()
        source_id = row.active_source_id if row else None
    if source_id and registry.get(source_id) is not None:
        return source_id
    return registry.DEFAULT_SOURCE_ID


def set_active_source(source_id: str) -> str:
    if registry.get(source_id) is None:
        raise ValueError("unknown source: %r" % source_id)

    from tools import db
    from ..models.costs_setting import CostsSetting

    with db.with_project_schema_session(None) as session:
        row = session.query(CostsSetting).filter(CostsSetting.id == _SETTINGS_ID).first()
        if row is None:
            row = CostsSetting(id=_SETTINGS_ID, active_source_id=source_id)
            session.add(row)
        else:
            row.active_source_id = source_id
        session.commit()
    log.info("costs.settings: active source set to %r", source_id)
    return source_id
