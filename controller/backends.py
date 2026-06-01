"""Backend Protocol + implementations for the orchestrator.

PymongoBackend: live pymongo driver, wraps sync I/O with asyncio.to_thread.
FakeBackend: deterministic in-memory backend for unit tests.
"""

import asyncio
from collections.abc import Sequence
from typing import Any, Protocol

from controller.explain import capture_evidence
from controller.schemas import Evidence


class Backend(Protocol):
    async def explain(
        self,
        query_filter: dict[str, Any],
        query_sort: Sequence[tuple[str, int]],
        limit: int,
        hint: str | list | None = None,
    ) -> Evidence: ...

    async def apply_index(self, keys: list[tuple[str, int]], name: str) -> None: ...

    async def drop_index(self, name: str) -> None: ...

    def close(self) -> None: ...


class PymongoBackend:
    def __init__(self, connection_string: str, db: str, collection: str) -> None:
        from pymongo import MongoClient

        self._client = MongoClient(connection_string)
        self._coll = self._client[db][collection]

    async def explain(  # pragma: no cover - live I/O
        self,
        query_filter: dict[str, Any],
        query_sort: Sequence[tuple[str, int]],
        limit: int,
        hint: str | list | None = None,
    ) -> Evidence:
        return await asyncio.to_thread(
            capture_evidence, self._coll, query_filter, query_sort, limit, hint
        )

    async def apply_index(self, keys: list[tuple[str, int]], name: str) -> None:  # pragma: no cover - live I/O
        from pymongo.errors import OperationFailure

        def _create() -> None:
            try:
                self._coll.create_index(keys, name=name)
            except OperationFailure as exc:
                # code 86 = IndexKeySpecsConflict — identical key pattern under different name;
                # an equivalent index already exists so the verify step can proceed
                if exc.code != 86:
                    raise

        await asyncio.to_thread(_create)

    async def drop_index(self, name: str) -> None:  # pragma: no cover - live I/O
        from pymongo.errors import OperationFailure

        def _drop() -> None:
            try:
                self._coll.drop_index(name)
            except OperationFailure:
                pass  # index never created (conflict was absorbed) or already gone

        await asyncio.to_thread(_drop)

    def close(self) -> None:
        self._client.close()


class FakeBackend:
    """Deterministic in-memory backend for unit tests.

    Consumes explain_results in order (call 0 → result 0, call 1 → result 1,
    falling back to the last element so single-item lists work for trivial cases).
    """

    def __init__(self, explain_results: list[Evidence]) -> None:
        self._results = explain_results
        self._call_count = 0
        self.applied_indexes: list[tuple[list[tuple[str, int]], str]] = []
        self.dropped_indexes: list[str] = []

    async def explain(
        self,
        query_filter: dict[str, Any],
        query_sort: Sequence[tuple[str, int]],
        limit: int,
        hint: str | list | None = None,
    ) -> Evidence:
        idx = min(self._call_count, len(self._results) - 1)
        self._call_count += 1
        return self._results[idx]

    async def apply_index(self, keys: list[tuple[str, int]], name: str) -> None:
        self.applied_indexes.append((keys, name))

    async def drop_index(self, name: str) -> None:
        self.dropped_indexes.append(name)

    def close(self) -> None:
        pass
