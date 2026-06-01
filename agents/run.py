"""Live scripted driver: fetch a real explain via the MongoDB MCP server, then run the
deterministic diagnosis on it.

Uses raw stdio JSON-RPC over a subprocess (not the `mcp` ClientSession, whose stdio
teardown hangs in this environment) and kills the server in a `finally` — so the path
can never hang. Manual / integration: needs npx + a Mongo connection string.
Run: uv run --with python-dotenv python agents/run.py

The parsing + diagnosis logic lives in `agents.tools` (extract_explain_json +
diagnosis_from_explain, both unit-tested offline); this module is only the MCP plumbing.
"""

import json
import os
import queue
import subprocess
import threading
import time

from agents.tools import diagnosis_from_explain, extract_explain_json
from controller.explain import get_connection_string

DB = "sample_supplies"
COLL = "sales_agent_demo"
QUERY_FILTER = {"storeLocation": "Denver", "customer.age": {"$gte": 30, "$lte": 50}}
QUERY_SORT = [("saleDate", -1)]
LIMIT = 20


def fetch_explain(connection_string: str, timeout: float = 90.0) -> dict:  # pragma: no cover - live MCP I/O
    env = {**os.environ, "MDB_MCP_CONNECTION_STRING": connection_string}
    proc = subprocess.Popen(
        ["npx", "-y", "mongodb-mcp-server", "--readOnly", "false"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
        env=env,
    )
    outq: queue.Queue[str] = queue.Queue()
    threading.Thread(target=lambda: [outq.put(line) for line in proc.stdout], daemon=True).start()

    next_id = 0

    def send(method: str, params: dict | None = None, notify: bool = False) -> int | None:
        nonlocal next_id
        msg: dict = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        if not notify:
            next_id += 1
            msg["id"] = next_id
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()
        return None if notify else next_id

    def wait_for(request_id: int, deadline: float) -> dict:
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
            if obj.get("id") == request_id:
                return obj
        raise TimeoutError(f"MCP: no response for request {request_id}")

    try:
        deadline = time.time() + timeout
        init_id = send(
            "initialize",
            {"protocolVersion": "2024-11-05", "capabilities": {},
             "clientInfo": {"name": "gcrah", "version": "0.1"}},
        )
        wait_for(init_id, deadline)
        send("notifications/initialized", notify=True)
        call_id = send(
            "tools/call",
            {"name": "explain", "arguments": {
                "database": DB, "collection": COLL,
                # hint the "obvious" index B so the explain shows the blocking-sort
                # trap the agent diagnoses (the seeded collection also has the good
                # index C, which the optimizer would otherwise pick unprompted)
                "method": [{"name": "find", "arguments": {
                    "filter": QUERY_FILTER, "sort": {"saleDate": -1}, "limit": LIMIT,
                    "hint": "esr_wrong_B"}}],
            }},
        )
        resp = wait_for(call_id, deadline)
        if "error" in resp:
            raise RuntimeError(f"MCP explain error: {resp['error']}")
        text = "".join(part.get("text", "") for part in resp["result"]["content"])
        return extract_explain_json(text)
    finally:
        proc.kill()


def run_live() -> dict:  # pragma: no cover - live MCP I/O
    connection_string = get_connection_string()
    if not connection_string:
        raise RuntimeError("no Mongo connection string in env")
    return diagnosis_from_explain(fetch_explain(connection_string), QUERY_FILTER, QUERY_SORT)


def main() -> None:  # pragma: no cover - live entrypoint
    from dotenv import load_dotenv

    load_dotenv()
    print(json.dumps(run_live(), indent=2))


if __name__ == "__main__":  # pragma: no cover
    main()
