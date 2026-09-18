"""Durable local inbox for generated Skills awaiting human approval."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from repository import ROOT, save_provisional_draft


PENDING_ROOT = ROOT / "pending-approvals"


def _pending_path(pending_id: str) -> Path:
    """Constrain inbox operations to UUID-named records inside PENDING_ROOT."""
    try:
        normalized = str(uuid.UUID(pending_id))
    except (ValueError, AttributeError) as error:
        raise ValueError("Invalid pending candidate id.") from error
    return PENDING_ROOT / f"{normalized}.json"


def stage(result: dict[str, Any], source: str, lineage: str | None = None) -> dict[str, Any]:
    from jobs import checkpoint, current_id
    checkpoint()
    PENDING_ROOT.mkdir(parents=True, exist_ok=True)
    pending_id = current_id() or str(uuid.uuid4())
    record = {"pendingId": pending_id, "source": source, "lineage": lineage, "createdAt": datetime.now(timezone.utc).isoformat(), "result": result}
    target = PENDING_ROOT / f"{pending_id}.json"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, target)
    return {"pendingId": pending_id, "source": source, "createdAt": record["createdAt"]}


def list_pending() -> list[dict[str, Any]]:
    if not PENDING_ROOT.exists():
        return []
    items: list[dict[str, Any]] = []
    for path in PENDING_ROOT.glob("*.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
        result = record.get("result", {})
        draft = result.get("draft", {})
        items.append({"pendingId": record["pendingId"], "source": record.get("source", "unknown"), "createdAt": record.get("createdAt", ""), "title": draft.get("title", "Untitled candidate"), "skillId": draft.get("id", ""), "valid": bool(result.get("validation", {}).get("valid"))})
    return sorted(items, key=lambda item: item["createdAt"], reverse=True)


def read_pending(pending_id: str) -> dict[str, Any]:
    path = _pending_path(pending_id)
    if not path.exists():
        raise FileNotFoundError("Pending candidate not found.")
    return json.loads(path.read_text(encoding="utf-8"))


def approve(pending_id: str) -> dict[str, Any]:
    record = read_pending(pending_id)
    result = record["result"]
    if not result.get("validation", {}).get("valid"):
        raise ValueError("This candidate did not pass validation.")
    saved = save_provisional_draft(result["draft"])
    from repository import _skill_path
    directory = _skill_path(saved['id'])
    for name, content in result.get('projectDocuments', {}).items():
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts or not name.startswith('project/') or relative.suffix != '.md':
            raise ValueError('Invalid project teaching document path.')
        destination = directory / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding='utf-8')
    # Import here to keep the durable inbox usable even during standalone tests.
    from version_store import register_approved_version
    register_approved_version(record.get("lineage"), saved["id"])
    _pending_path(pending_id).unlink(missing_ok=True)
    return saved


def discard(pending_id: str) -> None:
    """Delete a candidate only after an explicit human discard action."""
    path = _pending_path(pending_id)
    if not path.exists():
        raise FileNotFoundError("Pending candidate not found.")
    path.unlink()
