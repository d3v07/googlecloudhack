import json, time, urllib.request as u, urllib.error

BASE = "http://127.0.0.1:8000"
TOK = "local-e2e-token"
CRED = {"dev": ("dev.trivedi", "a5rGdW8qTGoGCF23"),
        "aakash": ("aakash.singh", "ozIE6iyi4uA5glvP"),
        "dbre": ("dbre", "Jd74qM--Gg8PBI_Z")}


def req(path, body=None, bearer=None, xapi=False, timeout=200):
    h = {"accept": "application/json"}
    data = None
    if body is not None:
        h["content-type"] = "application/json"
        data = json.dumps(body).encode()
    if bearer:
        h["authorization"] = f"Bearer {bearer}"
    if xapi:
        h["x-api-token"] = TOK
    return json.load(u.urlopen(u.Request(BASE + path, data=data, headers=h,
                                         method="POST" if data else "GET"), timeout=timeout))


def login(who):
    return req("/auth/login", {"username": CRED[who][0], "password": CRED[who][1]})["token"]


dev = login("dev")
aakash = login("aakash")
dbre = login("dbre")

# distinct captures
r1 = req("/workload/query", {"preset": "phone_seniors"}, bearer=dev)
print("Dev      ran phone_seniors  -> sev",
      r1["captured"]["signal"]["severity"], "docs", r1["captured"]["metrics"]["docs_examined"])
r2 = req("/workload/query", {"preset": "seattle_recent"}, bearer=aakash)
print("Aakash   ran seattle_recent -> sev",
      r2["captured"]["signal"]["severity"], "docs", r2["captured"]["metrics"]["docs_examined"])

# find Dev's Phone capture in the DBRE queue
rows = req("/workload/slow-queries", bearer=dbre)
phone = next((r for r in rows if r["query"]["filter"].get("purchaseMethod") == "Phone"), None)
assert phone, "phone capture not in queue"
cid = phone["captured_id"]
print(f"diagnosing Dev's Phone capture {cid} via 3 Gemini engines (~50s)...")
t0 = time.time()
pack = req("/run", {"captured_query_id": cid}, bearer=dbre, xapi=True)
rid = pack["run_id"]
ae = sum(1 for e in pack.get("agent_trace", []) if e.get("actor") == "agent_engine")
print(f"  /run {time.time()-t0:.0f}s -> {rid} status={pack['status']} agent_engine_events={ae}")

# verify real Voyage memory is OK for this pack
mem = req(f"/packs/{rid}/memory", bearer=dbre)
srcs = sorted({g["source"] for g in mem.get("guidance", [])})
print(f"memory: status={mem['status']} configured={mem['configured']} "
      f"hits={len(mem.get('guidance', []))} sources={srcs}")

json.dump({"run_id": rid, "phone_captured_id": cid, "memory_status": mem["status"],
           "memory_sources": srcs},
          open("/Users/dev/Documents/GCRAH/demo/video/prestage.json", "w"), indent=2)
print("wrote prestage.json")
