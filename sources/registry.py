"""Generic, source-neutral registry of price sources.

Core code only talks to this registry — it never imports a concrete adapter.
Adapters self-register at import time. The active source is chosen by config
(default: `litellm`), so a no-LiteLLM deployment swaps the default with no core change.
"""

from pylon.core.tools import log

_sources = {}

DEFAULT_SOURCE_ID = "litellm"
FALLBACK_SOURCE_ID = "bundled"


def register(source) -> None:
    _sources[source.id] = source
    log.info("costs.sources: registered %r", source.id)


def get(source_id: str):
    return _sources.get(source_id)


def all() -> dict:
    return dict(_sources)


def register_defaults() -> None:
    """Register the built-in adapters. Each is optional and self-contained."""
    from .litellm import LiteLLMSource
    from .bundled import BundledSource
    from .upload import UploadSource
    from .azure_foundry import AzureFoundrySource
    from .bedrock import BedrockSource

    register(LiteLLMSource())
    register(BundledSource())
    register(UploadSource())
    register(AzureFoundrySource())
    register(BedrockSource())
