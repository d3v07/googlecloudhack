#!/usr/bin/env python3
"""Smoke-test MongoDB MCP server tools over stdio JSON-RPC against `target`.

Drives the real MCP protocol: initialize -> tools/list -> tools/call for each
required tool. Reads use sample_supplies.sales (read-only); write tools
(create-index/drop-index) use a scratch namespace so demo data is untouched.
"""

import json, os, subprocess, sys, threading, queue, time

URI = os.environ["MCP_URI"]
SCRATCH_DB = "mcp_smoketest"
SCRATCH_COLL = "scratch"

# Launch the published server over stdio.
proc = subprocess.Popen(
    ["npx", "-y", "mongodb-mcp-server@latest", "--connectionString", URI, "--readOnly", "false"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    bufsize=1,
)

outq = queue.Queue()


def reader():
    for line in proc.stdout:
        outq.put(line)


threading.Thread(target=reader, daemon=True).start()


def drain_stderr():
    for line in proc.stderr:
        pass  # swallow server logs


threading.Thread(target=drain_stderr, daemon=True).start()

_id = 0


def send(method, params=None, is_notification=False):
    global _id
    msg = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        msg["params"] = params
    if not is_notification:
        _id += 1
        msg["id"] = _id
    proc.stdin.write(json.dumps(msg) + "\n")
    proc.stdin.flush()
    return None if is_notification else _id


def wait_for(target_id, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            line = outq.get(timeout=deadline - time.time())
        except queue.Empty:
            break
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("id") == target_id:
            return obj
    return {"error": {"message": "TIMEOUT waiting for id %s" % target_id}}


def call_tool(name, args):
    rid = send("tools/call", {"name": name, "arguments": args})
    return wait_for(rid)


def summarize(resp):
    if "error" in resp:
        return "ERROR: " + json.dumps(resp["error"])[:300]
    res = resp.get("result", {})
    if res.get("isError"):
        txt = " ".join(c.get("text", "") for c in res.get("content", []))
        return "TOOL-ERROR: " + txt[:300]
    sc = res.get("structuredContent")
    if sc is not None:
        return "ok structuredContent keys=" + ",".join(list(sc.keys()))[:200]
    txt = " ".join(c.get("text", "") for c in res.get("content", []))
    return "ok: " + txt[:200].replace("\n", " ")


results = {}

# 1. initialize
rid = send(
    "initialize",
    {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "frex22-smoke", "version": "0.1"},
    },
)
init = wait_for(rid)
if "error" in init:
    print("INIT FAILED:", init)
    proc.kill()
    sys.exit(1)
send("notifications/initialized", {}, is_notification=True)

# 2. tools/list
rid = send("tools/list", {})
tl = wait_for(rid)
tools = [t["name"] for t in tl.get("result", {}).get("tools", [])]
required = [
    "explain",
    "mongodb-logs",
    "create-index",
    "drop-index",
    "collection-indexes",
    "aggregate",
    "find",
    "count",
    "collection-schema",
    "atlas-get-performance-advisor",
]
print("=== TOOLS/LIST: %d tools exposed ===" % len(tools))
for r in required:
    print("  present" if r in tools else "  MISSING", "-", r)

print("\n=== SMOKE TESTS (against target) ===")

# Read-only tools on sample_supplies.sales
results["find"] = summarize(
    call_tool("find", {"database": "sample_supplies", "collection": "sales", "limit": 1})
)
results["count"] = summarize(
    call_tool("count", {"database": "sample_supplies", "collection": "sales"})
)
results["aggregate"] = summarize(
    call_tool(
        "aggregate",
        {"database": "sample_supplies", "collection": "sales", "pipeline": [{"$count": "n"}]},
    )
)
results["collection-schema"] = summarize(
    call_tool(
        "collection-schema",
        {"database": "sample_supplies", "collection": "sales", "sampleSize": 20},
    )
)
results["collection-indexes"] = summarize(
    call_tool("collection-indexes", {"database": "sample_supplies", "collection": "sales"})
)
results["explain"] = summarize(
    call_tool(
        "explain",
        {
            "database": "sample_supplies",
            "collection": "sales",
            "method": [{"name": "find", "arguments": {"filter": {"storeLocation": "Denver"}}}],
            "verbosity": "executionStats",
        },
    )
)
results["mongodb-logs"] = summarize(call_tool("mongodb-logs", {"type": "global", "limit": 5}))

# Write tools on scratch namespace (insert a seed doc first so collection exists)
call_tool(
    "insert-many",
    {"database": SCRATCH_DB, "collection": SCRATCH_COLL, "documents": [{"x": 1}, {"x": 2}]},
)
results["create-index"] = summarize(
    call_tool(
        "create-index",
        {
            "database": SCRATCH_DB,
            "collection": SCRATCH_COLL,
            "name": "smoke_x",
            "definition": [{"type": "classic", "keys": {"x": 1}}],
        },
    )
)
# drop-index has a confirmation gate; call may return a confirmation request
drop_resp = call_tool(
    "drop-index",
    {"database": SCRATCH_DB, "collection": SCRATCH_COLL, "indexName": "smoke_x", "type": "classic"},
)
results["drop-index"] = summarize(drop_resp)

# Atlas Performance Advisor (expected deferred on M0 / no service account)
pa = call_tool(
    "atlas-get-performance-advisor",
    {
        "projectId": os.environ.get("ATLAS_PROJECT", ""),
        "clusterName": "target",
        "operations": ["suggestedIndexes"],
    },
)
results["atlas-get-performance-advisor"] = summarize(pa)

for k in [
    "explain",
    "find",
    "count",
    "aggregate",
    "collection-schema",
    "collection-indexes",
    "mongodb-logs",
    "create-index",
    "drop-index",
    "atlas-get-performance-advisor",
]:
    print("  %-28s %s" % (k, results.get(k, "(not run)")))

# cleanup scratch
call_tool("drop-collection", {"database": SCRATCH_DB, "collection": SCRATCH_COLL})

proc.terminate()
print("\nDONE")
