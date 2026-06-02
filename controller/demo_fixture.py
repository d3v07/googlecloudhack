"""The canonical demo scenario — the Denver-sales ESR-trap query — shared by the CLI
demo (agents/demo.py) and the POST /run live trigger (api/server.py). Lives in controller/
so the read-API container can import it without packaging the agents/ (ADK) layer."""

DB = "sample_supplies"
COLL = "sales_agent_demo"
QUERY_FILTER = {"storeLocation": "Denver", "customer.age": {"$gte": 30, "$lte": 50}}
QUERY_SORT = [("saleDate", -1)]
LIMIT = 20
