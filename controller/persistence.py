"""Persist EvidencePacks. Local-file store needs no driver; the Mongo store is
driver-thin (takes a collection), so both stay CI-safe and fake-collection testable.
"""

import json
from pathlib import Path
from typing import Any

from controller.schemas import EvidencePack


def write_pack(pack: EvidencePack, directory: Path) -> Path:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{pack.run_id}.json"
    path.write_text(json.dumps(pack.model_dump(mode="json"), indent=2, sort_keys=True) + "\n")
    return path


def read_pack(path: Path) -> EvidencePack:
    return EvidencePack.model_validate_json(Path(path).read_text())


def save_pack(collection: Any, pack: EvidencePack) -> None:
    collection.replace_one({"run_id": pack.run_id}, pack.model_dump(mode="json"), upsert=True)


def load_pack(collection: Any, run_id: str) -> EvidencePack | None:
    doc = collection.find_one({"run_id": run_id}, projection={"_id": False})
    return EvidencePack.model_validate(doc) if doc else None
