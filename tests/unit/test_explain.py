from controller.explain import capture_evidence, get_connection_string


class _FakeCursor:
    def __init__(self, explained):
        self._explained = explained

    def hint(self, _hint):
        return self

    def explain(self):
        return self._explained


class _FakeCollection:
    def __init__(self, explained):
        self._explained = explained
        self.last_find = None

    def find(self, query_filter, sort, limit):
        self.last_find = {"filter": query_filter, "sort": sort, "limit": limit}
        return _FakeCursor(self._explained)


_EXPLAIN_B = {
    "queryPlanner": {
        "winningPlan": {
            "stage": "FETCH",
            "inputStage": {"stage": "SORT", "inputStage": {"stage": "IXSCAN"}},
        }
    },
    "executionStats": {
        "nReturned": 20,
        "totalKeysExamined": 17209,
        "totalDocsExamined": 20,
        "executionTimeMillis": 41,
    },
}


def test_capture_evidence_extracts_blocking_sort_and_keys():
    collection = _FakeCollection(_EXPLAIN_B)

    evidence = capture_evidence(
        collection,
        {"storeLocation": "Denver", "customer.age": {"$gte": 30, "$lte": 50}},
        [("saleDate", -1)],
        20,
        hint="esr_wrong_B",
    )

    assert evidence.metrics.has_blocking_sort is True
    assert evidence.metrics.total_keys_examined == 17209
    assert evidence.metrics.stages == ("FETCH", "SORT", "IXSCAN")
    assert collection.last_find["limit"] == 20


def test_capture_evidence_handles_branching_input_stages():
    explained = {
        "queryPlanner": {
            "winningPlan": {
                "stage": "FETCH",
                "inputStages": [{"stage": "IXSCAN"}, {"stage": "IXSCAN"}],
            }
        },
        "executionStats": {"nReturned": 1, "totalKeysExamined": 2, "totalDocsExamined": 1},
    }

    evidence = capture_evidence(_FakeCollection(explained), {"a": 1}, [("b", 1)], 5)

    assert evidence.metrics.has_blocking_sort is False
    assert evidence.metrics.stages == ("FETCH", "IXSCAN", "IXSCAN")
    assert evidence.metrics.millis == 0.0


def test_get_connection_string_reads_known_env_vars(monkeypatch):
    monkeypatch.delenv("MDB_MCP_CONNECTION_STRING", raising=False)
    monkeypatch.delenv("MONGODB_TARGET_URI", raising=False)
    assert get_connection_string() is None

    monkeypatch.setenv("MONGODB_TARGET_URI", "mongodb+srv://example/")
    assert get_connection_string() == "mongodb+srv://example/"
