#   Copyright 2026 EPAM Systems
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

""" Costs plugin — model price catalog with custom overrides """

from queue import Empty

from pylon.core.tools import log, module

from tools import auth, openapi_registry

from .init_db import init_db
from .sources import registry
from .utils import cache, catalog


class Module(module.ModuleModel):
    """ Costs plugin module """

    def __init__(self, context, descriptor):
        self.context = context
        self.descriptor = descriptor

    def init(self):
        log.info("Initializing costs plugin")
        self.descriptor.init_all()
        init_db()
        self._register_permissions()

    def ready(self):
        registry.register_defaults()
        self._seed_if_empty()
        self._register_openapi()
        self._register_cron()

    def deinit(self):
        log.info("De-initializing costs plugin")

    # -- internals -----------------------------------------------------------

    @staticmethod
    def _register_permissions():
        for action in ("view", "create", "edit", "delete"):
            auth.register_permissions({
                "permissions": [f"configuration.model_prices.prices.{action}"],
                "recommended_roles": {
                    "administration": {"super_admin": True, "admin": True, "viewer": action == "view", "editor": True},
                    "default": {"super_admin": True, "admin": True, "viewer": action == "view", "editor": True},
                    "developer": {"super_admin": True, "admin": True, "viewer": action == "view", "editor": True},
                },
            })

    def _seed_if_empty(self):
        """First-run seed from the bundled canonical dump if the table is empty."""
        try:
            if cache.count() > 0:
                return
            fallback = registry.get(registry.FALLBACK_SOURCE_ID)
            entries = fallback.fetch() if fallback else []
            if not entries:
                log.warning("costs: no bundled seed entries; catalog left empty")
                return
            catalog.upsert_entries(entries, registry.FALLBACK_SOURCE_ID)
            cache.reload()
        except Exception as e:  # pylint: disable=W0703
            log.exception("costs: catalog seed failed: %s", e)

    def _register_openapi(self):
        try:
            from .api import v2 as api_v2  # pylint: disable=C0415
            openapi_registry.register_plugin(
                plugin_name="costs",
                version=self.descriptor.metadata.get("version", "0.1"),
                description="Model price catalog with custom per-deployment overrides",
                api_module=api_v2,
            )
        except Exception as e:  # pylint: disable=W0703
            log.warning("Failed to register OpenAPI for costs plugin: %s", e)

    def _register_cron(self):
        try:
            self.context.rpc_manager.timeout(5).scheduling_create_if_not_exists({
                "rpc_func": "costs_refresh_catalog",
                "rpc_kwargs": {},
                "name": "costs_refresh_model_prices",
                "cron": "0 8 * * *",
                "active": True,
            })
        except Empty:
            log.warning("costs: no scheduling plugin found; daily refresh not registered")
        except Exception as e:  # pylint: disable=W0703
            log.warning("costs: failed to register daily refresh cron: %s", e)
