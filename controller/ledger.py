import hashlib
import json
from base64 import b64encode
from collections.abc import Iterable, Mapping
from typing import Any

from pydantic import BaseModel

_VOLATILE_KEYS = {
    "_ts",
    "created_at",
    "generated_at",
    "timestamp",
    "updated_at",
}


def evidence_hash(evidence: Any) -> str:
    canonical = _canonical_collection(evidence) if _is_collection(evidence) else _canonical(evidence)
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _is_collection(value: Any) -> bool:
    return isinstance(value, Iterable) and not isinstance(value, BaseModel | Mapping | str | bytes)


def _canonical_collection(values: Iterable[Any]) -> list[Any]:
    items = [_canonical(item) for item in values]
    return sorted(items, key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")))


def _canonical(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _canonical(value.model_dump(mode="python"))
    if isinstance(value, Mapping):
        return {
            str(key): _canonical(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key) not in _VOLATILE_KEYS
        }
    if isinstance(value, bytes):
        return {"__bytes__": b64encode(value).decode("ascii")}
    if isinstance(value, str):
        return value
    if isinstance(value, set | frozenset):
        return _canonical_collection(value)
    if isinstance(value, Iterable):
        return [_canonical(item) for item in value]
    return value
