"""Single model price endpoints (administration mode).

- GET    /api/v2/costs/price/administration/<project_id>/<model_name>  — effective price
- POST   /api/v2/costs/price/administration/<project_id>                — set custom override
- PUT    /api/v2/costs/price/administration/<project_id>/<model_name>   — update custom values
- DELETE /api/v2/costs/price/administration/<project_id>/<model_name>   — reset to default

Every write reloads the in-memory cache so reads stay authoritative.
"""

from flask import request
from pydantic import ValidationError

from tools import api_tools, auth, config as c, register_openapi

from ...models.pd.price import CustomPriceCreate, CustomPriceUpdate
from ...utils import cache, catalog

OPENAPI_TAG = "costs/prices"

_VIEW_ROLES = {c.ADMINISTRATION_MODE: {"admin": True, "viewer": True, "editor": True}}
_WRITE_ROLES = {c.ADMINISTRATION_MODE: {"admin": True, "viewer": False, "editor": True}}


class AdminAPI(api_tools.APIModeHandler):
    @register_openapi(
        name="Get Model Price",
        description="Resolve the effective price for a single model (with prefix-strip lookup).",
        tags=[OPENAPI_TAG],
        parameters=[
            {"name": "project_id", "in": "path", "schema": {"type": "integer"}},
            {"name": "model_name", "in": "path", "schema": {"type": "string"}},
        ],
    )
    @auth.decorators.check_api({
        "permissions": ["configuration.model_prices.prices.view"],
        "recommended_roles": _VIEW_ROLES,
    })
    @api_tools.endpoint_metrics
    def get(self, project_id: int, model_name: str, **kwargs):
        price = cache.get_price(model_name)
        if not price:
            return {"error": "not_found", "model_name": model_name}, 404
        return price, 200

    @register_openapi(
        name="Set Custom Model Price",
        description="Create or overwrite a custom price for a model (marks is_custom).",
        tags=[OPENAPI_TAG],
        parameters=[
            {"name": "project_id", "in": "path", "schema": {"type": "integer"}},
        ],
        response_model=CustomPriceCreate,
    )
    @auth.decorators.check_api({
        "permissions": ["configuration.model_prices.prices.create"],
        "recommended_roles": _WRITE_ROLES,
    })
    @api_tools.endpoint_metrics
    def post(self, project_id: int, **kwargs):
        try:
            payload = CustomPriceCreate.parse_obj(request.json or {})
        except ValidationError as e:
            return {"error": "validation_error", "details": e.errors()}, 400
        data = payload.dict()
        model_name = data.pop("model_name")
        result = catalog.set_custom_price(model_name, data)
        cache.reload()
        return result, 201

    @register_openapi(
        name="Update Custom Model Price",
        description="Update custom price values for a model.",
        tags=[OPENAPI_TAG],
        parameters=[
            {"name": "project_id", "in": "path", "schema": {"type": "integer"}},
            {"name": "model_name", "in": "path", "schema": {"type": "string"}},
        ],
        response_model=CustomPriceUpdate,
    )
    @auth.decorators.check_api({
        "permissions": ["configuration.model_prices.prices.edit"],
        "recommended_roles": _WRITE_ROLES,
    })
    @api_tools.endpoint_metrics
    def put(self, project_id: int, model_name: str, **kwargs):
        try:
            payload = CustomPriceUpdate.parse_obj(request.json or {})
        except ValidationError as e:
            return {"error": "validation_error", "details": e.errors()}, 400
        result = catalog.set_custom_price(model_name, payload.dict(exclude_none=True))
        cache.reload()
        return result, 200

    @register_openapi(
        name="Reset Model Price",
        description="Reset a custom override back to the imported default (or delete a custom-only row).",
        tags=[OPENAPI_TAG],
        parameters=[
            {"name": "project_id", "in": "path", "schema": {"type": "integer"}},
            {"name": "model_name", "in": "path", "schema": {"type": "string"}},
        ],
    )
    @auth.decorators.check_api({
        "permissions": ["configuration.model_prices.prices.delete"],
        "recommended_roles": _WRITE_ROLES,
    })
    @api_tools.endpoint_metrics
    def delete(self, project_id: int, model_name: str, **kwargs):
        result = catalog.reset_custom_price(model_name)
        if result is None:
            return {"error": "not_found", "model_name": model_name}, 404
        cache.reload()
        return result, 200


class API(api_tools.APIBase):
    url_params = [
        "<string:mode>/<int:project_id>",
        "<string:mode>/<int:project_id>/<path:model_name>",
    ]

    mode_handlers = {
        c.ADMINISTRATION_MODE: AdminAPI,
    }
