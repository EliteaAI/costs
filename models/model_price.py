"""ModelPrice model — one row per canonical model in the shared schema.

Source-neutral: the schema knows nothing about any specific price source.
Adapters normalize their own format into a canonical entry that maps here.
`is_custom` marks an admin override; the daily refresh never overwrites the
effective price columns on custom rows (it only refreshes `base_snapshot`).
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Integer, String, DateTime, Numeric, Boolean, Index, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from tools import db, config as c


class ModelPrice(db.Base):
    __tablename__ = 'model_prices'
    __table_args__ = (
        Index('ix_model_prices_is_custom', 'is_custom'),
        Index('ix_model_prices_mode', 'mode'),
        Index('ix_model_prices_provider', 'provider'),
        {'schema': c.POSTGRES_SCHEMA},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Canonical platform model key (e.g. gpt-4o, anthropic.claude-...). Adapters
    # map their own keys into this; it is not tied to any source's format.
    model_name: Mapped[str] = mapped_column(String(256), nullable=False, unique=True, index=True)
    provider: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    mode: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    # Effective price columns (custom overrides the imported value).
    input_cost_per_token: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 12), nullable=True)
    output_cost_per_token: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 12), nullable=True)
    cache_read_input_token_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 12), nullable=True)
    cache_creation_input_token_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 12), nullable=True)

    max_input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_output_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Alternate names/keys a source used, to aid lookup.
    aliases: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    # Full normalized entry (capability flags, per-image/pixel/query costs).
    extra: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    is_custom: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Adapter id that last wrote this row: litellm / custom / upload / ...
    source: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    # Original key/id in that source, for round-trip/debug.
    source_ref: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    # Last imported values, for "reset to default".
    base_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def to_json(self):
        return {
            'id': self.id,
            'model_name': self.model_name,
            'provider': self.provider,
            'mode': self.mode,
            'input_cost_per_token': _num(self.input_cost_per_token),
            'output_cost_per_token': _num(self.output_cost_per_token),
            'cache_read_input_token_cost': _num(self.cache_read_input_token_cost),
            'cache_creation_input_token_cost': _num(self.cache_creation_input_token_cost),
            'max_input_tokens': self.max_input_tokens,
            'max_output_tokens': self.max_output_tokens,
            'aliases': self.aliases or [],
            'is_custom': self.is_custom,
            'source': self.source,
            'source_ref': self.source_ref,
        }


def _num(value: Optional[Decimal]):
    return float(value) if value is not None else None
