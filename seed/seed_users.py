"""Seed the three demo accounts into dbre_state.users with scrypt-hashed passwords.

For each account that does not yet exist, a strong random password is generated, the user is
inserted with only its hash, and the plaintext is printed ONCE to stdout for the operator to
record. Existing accounts keep their password (idempotent) — display name and role are kept in
sync. Plaintext passwords are never persisted or logged anywhere but this one-time stdout line.

Usage:
  export MDB_MCP_CONNECTION_STRING=...     # or MONGO_SECRET_NAME (+ GOOGLE_CLOUD_PROJECT) on GCP
  uv run python seed/seed_users.py
"""

import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pymongo import MongoClient  # noqa: E402

from api.secrets import get_mongo_connection_string  # noqa: E402
from controller.auth import hash_password  # noqa: E402

ACCOUNTS = [
    {"username": "dev.trivedi", "display_name": "Dev Trivedi", "role": "user"},
    {"username": "aakash.singh", "display_name": "Aakash Singh", "role": "user"},
    {"username": "dbre", "display_name": "DBRE Operator", "role": "dbre"},
]


def _generate_password() -> str:
    return secrets.token_urlsafe(12)


def main() -> int:
    users = MongoClient(get_mongo_connection_string())["dbre_state"]["users"]
    users.create_index("username", unique=True)

    rows: list[tuple[str, str, str, str | None]] = []
    for account in ACCOUNTS:
        password = _generate_password()
        result = users.update_one(
            {"username": account["username"]},
            {
                "$set": {"display_name": account["display_name"], "role": account["role"]},
                "$setOnInsert": {"password_hash": hash_password(password)},
            },
            upsert=True,
        )
        created = result.upserted_id is not None
        rows.append(
            (
                account["display_name"],
                account["username"],
                account["role"],
                password if created else None,
            )
        )

    print("\nDemo accounts (record the passwords now — shown only on first creation):\n")
    for display, username, role, password in rows:
        shown = password if password is not None else "(unchanged — already seeded)"
        print(f"  {display:<16} username={username:<14} role={role:<5} password={shown}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
