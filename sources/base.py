"""Source-neutral canonical entry + PriceSource protocol.

The plugin core only ever understands `CanonicalEntry`. A source adapter is
responsible for turning its own format (LiteLLM JSON, a CSV upload, a provider
API, ...) into a list of these. Core code never imports a concrete adapter.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, Protocol, runtime_checkable


# Cost fields carried on a canonical entry, kept as plain floats. These names
# match the effective price columns on the ModelPrice model.
COST_FIELDS = (
    "input_cost_per_token",
    "output_cost_per_token",
    "cache_read_input_token_cost",
    "cache_creation_input_token_cost",
)


@dataclass
class CanonicalEntry:
    model_name: str
    provider: Optional[str] = None
    mode: Optional[str] = None
    input_cost_per_token: Optional[float] = None
    output_cost_per_token: Optional[float] = None
    cache_read_input_token_cost: Optional[float] = None
    cache_creation_input_token_cost: Optional[float] = None
    max_input_tokens: Optional[int] = None
    max_output_tokens: Optional[int] = None
    aliases: list = field(default_factory=list)
    extra: dict = field(default_factory=dict)
    source: Optional[str] = None
    source_ref: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@runtime_checkable
class PriceSource(Protocol):
    """A named price source. `fetch()` returns canonical entries."""

    id: str

    def fetch(self) -> list:  # -> list[CanonicalEntry]
        ...
