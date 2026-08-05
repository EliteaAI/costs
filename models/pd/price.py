"""Request models for custom-price CRUD.

Validation guards: non-negative costs, known `mode`. Prices are per-token USD
amounts (very small floats), so we allow 0 but reject negatives.
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

_KNOWN_MODES = {
    "chat", "completion", "embedding", "image_generation",
    "audio_transcription", "audio_speech", "moderation", "rerank",
}


class CustomPriceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_name: str = Field(..., min_length=1, max_length=256)
    provider: Optional[str] = Field(None, max_length=128)
    mode: Optional[str] = Field(None, max_length=32)
    input_cost_per_token: Optional[float] = None
    output_cost_per_token: Optional[float] = None
    cache_read_input_token_cost: Optional[float] = None
    cache_creation_input_token_cost: Optional[float] = None
    max_input_tokens: Optional[int] = Field(None, ge=0)
    max_output_tokens: Optional[int] = Field(None, ge=0)

    @field_validator(
        "input_cost_per_token", "output_cost_per_token",
        "cache_read_input_token_cost", "cache_creation_input_token_cost",
    )
    @classmethod
    def _non_negative(cls, v):
        if v is not None and v < 0:
            raise ValueError("cost must be non-negative")
        return v

    @field_validator("mode")
    @classmethod
    def _known_mode(cls, v):
        if v and v not in _KNOWN_MODES:
            raise ValueError(f"unknown mode: {v}")
        return v


class CustomPriceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Optional[str] = Field(None, max_length=128)
    mode: Optional[str] = Field(None, max_length=32)
    input_cost_per_token: Optional[float] = None
    output_cost_per_token: Optional[float] = None
    cache_read_input_token_cost: Optional[float] = None
    cache_creation_input_token_cost: Optional[float] = None
    max_input_tokens: Optional[int] = Field(None, ge=0)
    max_output_tokens: Optional[int] = Field(None, ge=0)

    @field_validator(
        "input_cost_per_token", "output_cost_per_token",
        "cache_read_input_token_cost", "cache_creation_input_token_cost",
    )
    @classmethod
    def _non_negative(cls, v):
        if v is not None and v < 0:
            raise ValueError("cost must be non-negative")
        return v

    @field_validator("mode")
    @classmethod
    def _known_mode(cls, v):
        if v and v not in _KNOWN_MODES:
            raise ValueError(f"unknown mode: {v}")
        return v
