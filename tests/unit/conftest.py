import pytest


@pytest.fixture(autouse=True)
def _no_ambient_mongo(monkeypatch):
    """Unit tests pin their own stores/engines. Keep an ambient MONGO_SECRET_NAME or
    MDB_MCP_CONNECTION_STRING in the dev shell (e.g. a sourced .env) from flipping create_app
    into live Mongo mode mid-suite. Tests that exercise live mode set the env themselves after."""
    monkeypatch.delenv("MONGO_SECRET_NAME", raising=False)
    monkeypatch.delenv("MDB_MCP_CONNECTION_STRING", raising=False)
