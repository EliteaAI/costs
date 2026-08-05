"""List endpoint for the model price catalog (administration mode).

URL: GET /api/v2/costs/prices/administration/<project_id>
"""

from flask import request

from tools import api_tools, auth, config as c, register_openapi

from ...utils import cache

OPENAPI_TAG = "costs/prices"


class AdminAPI(api_tools.APIModeHandler):
    @register_openapi(
        name="List Model Prices",
        description="Paginated catalog of model prices with search and mode filter.",
        tags=[OPENAPI_TAG],
        parameters=[
            {"name": "project_id", "in": "path", "schema": {"type": "integer"}},
            {"name": "search", "in": "query", "required": False, "schema": {"type": "string"},
             "description": "Substring match on model name."},
            {"name": "mode", "in": "query", "required": False, "schema": {"type": "string"},
             "description": "Filter by mode (chat, embedding, image_generation, ...)."},
            {"name": "custom_only", "in": "query", "required": False, "schema": {"type": "boolean"},
             "description": "Return only admin-overridden rows."},
            {"name": "limit", "in": "query", "required": False, "schema": {"type": "integer", "default": 50}},
            {"name": "offset", "in": "query", "required": False, "schema": {"type": "integer", "default": 0}},
        ],
    )
    @auth.decorators.check_api({
        "permissions": ["configuration.model_prices.prices.view"],
        "recommended_roles": {
            c.ADMINISTRATION_MODE: {"admin": True, "viewer": True, "editor": True},
        },
    })
    @api_tools.endpoint_metrics
    def get(self, project_id: int, **kwargs):
        search = (request.args.get("search") or "").strip().lower()
        mode = request.args.get("mode") or None
        custom_only = (request.args.get("custom_only", "false").lower() == "true")
        limit = int(request.args.get("limit", 50))
        offset = int(request.args.get("offset", 0))

        rows = list(cache.all_prices().values())
        if search:
            rows = [r for r in rows if search in r["model_name"].lower()]
        if mode:
            rows = [r for r in rows if r.get("mode") == mode]
        if custom_only:
            rows = [r for r in rows if r.get("is_custom")]

        rows.sort(key=lambda r: r["model_name"])
        total = len(rows)
        page = rows if limit in (0, "All") else rows[offset:offset + limit]
        return {"total": total, "rows": page}, 200


class API(api_tools.APIBase):
    url_params = [
        "<string:mode>/<int:project_id>",
    ]

    mode_handlers = {
        c.ADMINISTRATION_MODE: AdminAPI,
    }
