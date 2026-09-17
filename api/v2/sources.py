"""Price source selection + destructive re-import (administration mode).

- GET  /api/v2/costs/sources/administration/<project_id>   — list sources + active
- POST /api/v2/costs/sources/administration/<project_id>    — set source & re-import

The POST is destructive: it sets the active source, then wipes ALL model prices
(including custom overrides) and reloads them from the chosen source. The reimport
RPC fetches first and aborts before any wipe if the source returns nothing.
"""

from flask import request

from tools import api_tools, auth, config as c, register_openapi

from ...sources import registry
from ...utils import settings

OPENAPI_TAG = "costs/prices"

_VIEW_ROLES = {c.ADMINISTRATION_MODE: {"admin": True, "viewer": True, "editor": True}}
_WRITE_ROLES = {c.ADMINISTRATION_MODE: {"admin": True, "viewer": False, "editor": True}}

# Sources selectable from the admin UI (kept intentionally narrow).
_SELECTABLE_SOURCES = ("litellm", "azure_foundry", "bedrock", "custom")


class AdminAPI(api_tools.APIModeHandler):
    @register_openapi(
        name="List Price Sources",
        description="List selectable price sources and the currently active one.",
        tags=[OPENAPI_TAG],
        parameters=[
            {"name": "project_id", "in": "path", "schema": {"type": "integer"}},
        ],
    )
    @auth.decorators.check_api({
        "permissions": ["configuration.model_prices.prices.view"],
        "recommended_roles": _VIEW_ROLES,
    })
    @api_tools.endpoint_metrics
    def get(self, project_id: int, **kwargs):
        available = [s for s in _SELECTABLE_SOURCES if registry.get(s) is not None]
        return {"sources": available, "active": settings.get_active_source()}, 200

    @register_openapi(
        name="Re-import Model Prices",
        description="Set the active source and destructively re-import the whole price table.",
        tags=[OPENAPI_TAG],
        parameters=[
            {"name": "project_id", "in": "path", "schema": {"type": "integer"}},
        ],
    )
    @auth.decorators.check_api({
        "permissions": ["configuration.model_prices.prices.reimport"],
        "recommended_roles": _WRITE_ROLES,
    })
    @api_tools.endpoint_metrics
    def post(self, project_id: int, **kwargs):
        body = request.json or {}
        source_id = body.get("source_id")
        if source_id not in _SELECTABLE_SOURCES or registry.get(source_id) is None:
            return {"error": "invalid_source", "source_id": source_id}, 400

        settings.set_active_source(source_id)
        result = self.module.context.rpc_manager.call.costs_reimport_catalog(source_id=source_id)
        if result.get("error"):
            return result, 502
        return result, 200


class API(api_tools.APIBase):
    url_params = [
        "<string:mode>/<int:project_id>",
    ]

    mode_handlers = {
        c.ADMINISTRATION_MODE: AdminAPI,
    }
