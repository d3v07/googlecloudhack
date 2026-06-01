import os


def get_mongo_connection_string() -> str:
    secret_name = os.getenv("MONGO_SECRET_NAME")
    if secret_name:  # pragma: no cover - live GCP
        from google.cloud import secretmanager  # noqa: PLC0415

        project = os.environ["GOOGLE_CLOUD_PROJECT"]
        client = secretmanager.SecretManagerServiceClient()
        path = f"projects/{project}/secrets/{secret_name}/versions/latest"
        response = client.access_secret_version(name=path)
        return response.payload.data.decode("utf-8")

    conn = os.getenv("MDB_MCP_CONNECTION_STRING")
    if conn:
        return conn

    raise RuntimeError(
        "MongoDB connection string unavailable: set MONGO_SECRET_NAME (GCP) "
        "or MDB_MCP_CONNECTION_STRING (local)"
    )
