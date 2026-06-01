from enum import StrEnum
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from controller.phases import Phase


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DecisionAction(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    DEFER = "defer"


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, tuple | list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set | frozenset):
        return tuple(_freeze(item) for item in sorted(value, key=repr))
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


class EvidenceMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)

    docs_examined: int = Field(ge=0)
    docs_returned: int = Field(ge=0)
    millis: float = Field(ge=0)
    total_keys_examined: int = Field(ge=0)
    stages: tuple[str, ...] = ()

    @property
    def has_blocking_sort(self) -> bool:
        return "SORT" in self.stages


class Evidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    query: Mapping[str, Any] | str
    explain_plan: Mapping[str, Any]
    metrics: EvidenceMetrics

    @field_validator("query", "explain_plan", mode="after")
    @classmethod
    def freeze_payload(cls, value: Any) -> Any:
        return _freeze(value)

    @field_serializer("query", "explain_plan")
    def serialize_payload(self, value: Any) -> Any:
        return _thaw(value)


class Finding(BaseModel):
    model_config = ConfigDict(frozen=True)

    problem: str = Field(min_length=1)
    severity: Severity
    evidence_refs: tuple[str, ...] = Field(min_length=1)


class Recommendation(BaseModel):
    model_config = ConfigDict(frozen=True)

    # ordered (field, direction) pairs — field ORDER is the recommendation (ESR), so a
    # dict would lose it under sorted-key hashing/serialization. Pairs stay ordered.
    index_spec: tuple[tuple[str, int], ...] = Field(min_length=1)
    rationale: str = Field(min_length=1)


class Decision(BaseModel):
    model_config = ConfigDict(frozen=True)

    action: DecisionAction
    evidence_hash: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    phase: Phase


class Diagnosis(BaseModel):
    model_config = ConfigDict(frozen=True)

    finding: Finding
    recommendation: Recommendation
