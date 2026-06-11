"""Drop the gcrah_rec_* index created by the live approve, so the demo trap is repeatable.
Leaves the workload baseline indexes ({storeLocation:1}, {purchaseMethod:1}) untouched.
Run: uv run --env-file .env python demo/video/reset.py
"""

import os

from pymongo import MongoClient

DB, COLL = "sample_supplies", "sales_agent_demo"

conn = os.environ.get("MDB_MCP_CONNECTION_STRING") or os.environ.get("MONGODB_TARGET_URI")
assert conn, "no MDB connection string in env"
client = MongoClient(conn)
try:
    coll = client[DB][COLL]
    before = [ix["name"] for ix in coll.list_indexes()]
    dropped = []
    for name in before:
        if name.startswith("gcrah_rec_"):
            coll.drop_index(name)
            dropped.append(name)
    after = [ix["name"] for ix in coll.list_indexes()]
    print(f"namespace : {DB}.{COLL}")
    print(f"dropped   : {dropped or 'none'}")
    print(f"remaining : {after}")
finally:
    client.close()
