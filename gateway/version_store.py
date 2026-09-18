"""Explicit, recoverable version governance for approved generated Skills.

The registry never changes a Skill's files when selecting an active version.
Cleanup moves only generated drafts to a local trash folder, so it is reversible.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from repository import ROOT, SKILLS_ROOT, _skill_path


REGISTRY = SKILLS_ROOT / ".trainer-version-history.json"
TRASH = SKILLS_ROOT / ".trainer-trash"


def _load() -> dict[str, Any]:
    if not REGISTRY.exists():
        return {"families": {}}
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def _save(data: dict[str, Any]) -> None:
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    temporary = REGISTRY.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, REGISTRY)


def _family(data: dict[str, Any], skill_id: str) -> tuple[str, dict[str, Any]]:
    for base_id, family in data["families"].items():
        if any(version["id"] == skill_id for version in family.get("versions", [])):
            return base_id, family
    return skill_id, {"activeId": skill_id, "versions": [{"id": skill_id, "parentId": None, "state": "active", "createdAt": "baseline"}]}


def register_approved_version(parent_id: str | None, skill_id: str) -> None:
    """Record a newly approved optimization; activation remains a user decision."""
    data = _load()
    base_id, family = _family(data, parent_id or skill_id)
    if base_id not in data['families'] and parent_id:
        try:
            _skill_path(parent_id)
        except FileNotFoundError:
            # Rejected inbox candidates were never installed teaching versions.
            # Preserve provenance without making their absent ID active.
            family['activeId'] = skill_id
            family['versions'][0]['state'] = 'not-installed'
    versions = family["versions"]
    if not any(version["id"] == skill_id for version in versions):
        versions.append({"id": skill_id, "parentId": parent_id, "state": "active" if family['activeId'] == skill_id else "available", "createdAt": datetime.now(timezone.utc).isoformat()})
    data["families"][base_id] = family
    _save(data)


def history(skill_id: str) -> dict[str, Any]:
    data = _load()
    base_id, family = _family(data, skill_id)
    versions = []
    for version in family['versions']:
        item = dict(version)
        if item.get('state') != 'trashed':
            try:
                _skill_path(item['id'])
            except FileNotFoundError:
                item['state'] = 'not-installed'
        versions.append(item)
    return {"familyId": base_id, "activeId": family["activeId"], "versions": versions}

def link_legacy(skill_id, parent_id):
    """An explicit user-selected parent is the only authority for legacy lineage."""
    if skill_id == parent_id:
        raise ValueError('不能关联自己。')
    _skill_path(skill_id); _skill_path(parent_id)
    data = _load()
    child_base, child = _family(data, skill_id)
    parent_base, parent = _family(data, parent_id)
    if child_base == parent_base:
        return history(skill_id)
    if len(child['versions']) > 1:
        raise ValueError('此 Skill 已有版本家族，不能自动合并。')
    if REGISTRY.exists():
        backup = REGISTRY.with_name(REGISTRY.name + '.before-link-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f'))
        shutil.copy2(REGISTRY, backup)
    data['families'].pop(child_base, None)
    parent['versions'].append({'id': skill_id, 'parentId': parent_id, 'state': 'available', 'createdAt': datetime.now(timezone.utc).isoformat()})
    data['families'][parent_base] = parent
    _save(data)
    return history(skill_id)


def resolve_teaching_id(skill_id: str) -> str:
    """Honor activation when available; never redirect a saved candidate to a missing parent."""
    active_id = history(skill_id)['activeId']
    try:
        _skill_path(active_id)
        return active_id
    except FileNotFoundError:
        _skill_path(skill_id)
        return skill_id


def activate(skill_id: str, target_id: str) -> dict[str, Any]:
    data = _load()
    base_id, family = _family(data, skill_id)
    target = next((item for item in family["versions"] if item["id"] == target_id and item.get("state") != "trashed"), None)
    if target is None:
        raise ValueError("That version is not available in this Skill family.")
    try:
        _skill_path(target_id)
    except FileNotFoundError as error:
        raise ValueError("That version is no longer available locally.") from error
    family["activeId"] = target_id
    for item in family["versions"]:
        if item.get("state") != "trashed":
            item["state"] = "active" if item["id"] == target_id else "available"
    data["families"][base_id] = family
    _save(data)
    return history(target_id)


def trash(skill_id: str, target_id: str) -> dict[str, Any]:
    """Recoverably clean a non-active generated version; core/verified assets are protected."""
    data = _load()
    base_id, family = _family(data, skill_id)
    if target_id == family["activeId"]:
        raise ValueError("请先将另一版本设为当前教学版本，再清理当前版本。")
    target = next((item for item in family["versions"] if item["id"] == target_id), None)
    if target is None or target_id == base_id:
        raise ValueError("基础版本不能清理；可将它设为当前版本以回退。")
    source = _skill_path(target_id)
    try:
        source.relative_to(SKILLS_ROOT / "generated")
    except ValueError as error:
        raise ValueError("仅 AI 生成的版本可以清理，内置和已验证资产受保护。") from error
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = TRASH / stamp / target_id.replace(".", "/")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))
    target["state"] = "trashed"
    target["trashedPath"] = str(destination.relative_to(ROOT))
    data["families"][base_id] = family
    _save(data)
    return history(skill_id)


def restore(skill_id: str, target_id: str) -> dict[str, Any]:
    data = _load()
    base_id, family = _family(data, skill_id)
    target = next((item for item in family['versions'] if item['id'] == target_id and item.get('state') == 'trashed'), None)
    if target is None:
        raise ValueError('此版本不在回收区。')
    source = (ROOT / target['trashedPath']).resolve()
    if not source.is_relative_to(TRASH.resolve()) or not source.is_dir():
        raise ValueError('回收内容不存在。')
    from repository import SAFE_SKILL_ID
    if not SAFE_SKILL_ID.fullmatch(target_id):
        raise ValueError('Invalid Skill id.')
    destination = SKILLS_ROOT / 'generated' / target_id.replace('.', '/')
    if destination.exists():
        raise ValueError('已有同名版本，不能覆盖恢复。')
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))
    target['state'] = 'available'
    target.pop('trashedPath', None)
    data['families'][base_id] = family
    _save(data)
    return history(skill_id)
