"""File-backed Skill repository with explicit provisional-save semantics."""

from __future__ import annotations

import os
import json
import re
from pathlib import Path
from typing import Any


from storage import DATA, ASSETS
ROOT = DATA
SKILLS_ROOT = ROOT / "skills"
SAFE_SKILL_ID = re.compile(r"^[a-z][a-z0-9.-]+$")


def _front_matter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end < 0:
        return {}
    values: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" in line and not line.startswith((" ", "-")):
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip().strip('"')
    return values


def _title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def _languages(directory: Path, text: str) -> list[str]:
    """Read declared teaching languages from Skill metadata, not path names."""
    candidates = [text]
    curriculum = directory / "curriculum.yaml"
    if curriculum.exists():
        candidates.append(curriculum.read_text(encoding="utf-8"))
    for candidate in candidates:
        match = re.search(r"^\s*languages:\s*\[([^\]]+)\]", candidate, re.MULTILINE)
        if match:
            return [value.strip().strip('"\'') for value in match.group(1).split(",") if value.strip()]
    return []


def _skill_path(skill_id: str) -> Path:
    if not SAFE_SKILL_ID.fullmatch(skill_id):
        raise ValueError("Invalid Skill id.")
    for path in SKILLS_ROOT.rglob("SKILL.md"):
        if any(part.startswith('.') for part in path.relative_to(SKILLS_ROOT).parts):
            continue
        metadata = _front_matter(path.read_text(encoding="utf-8"))
        if metadata.get("id") == skill_id:
            return path.parent
    raise FileNotFoundError("Skill not found.")


def _category(directory: Path, metadata: dict[str, str], text: str, trust: str) -> str:
    if trust == 'core':
        return 'core'
    sidecar = directory / '.trainer-category.json'
    if sidecar.exists():
        try:
            value = json.loads(sidecar.read_text(encoding='utf-8')).get('category')
            if value in {'course', 'project-practice'}:
                return value
        except (ValueError, OSError):
            pass
    if metadata.get('category') in {'course', 'project-practice'}:
        return metadata['category']
    # Compatibility for legacy assets without persisted generation mode.
    if re.search(r'项目实战|从零(?:写|构建|实现|开发)|从零.{0,12}小作品', text):
        return 'project-practice'
    return 'course'


def list_skills() -> list[dict[str, str]]:
    skills: list[dict[str, str]] = []
    for path in SKILLS_ROOT.rglob("SKILL.md"):
        if any(part.startswith('.') for part in path.relative_to(SKILLS_ROOT).parts):
            continue
        text = path.read_text(encoding="utf-8")
        metadata = _front_matter(text)
        skill_id = metadata.get("id")
        if not skill_id:
            continue
        relative = path.parent.relative_to(SKILLS_ROOT)
        trust = "core" if relative.parts[0] == "core" else metadata.get("status", "unknown")
        skills.append({
            "id": skill_id,
            "title": metadata.get("title", _title(text, skill_id)),
            "status": trust,
            "path": str(relative),
            "version": metadata.get("version", "0.1.0"),
            "languages": _languages(path.parent, text),
            "category": _category(path.parent, metadata, text, trust),
        })
    return sorted(skills, key=lambda item: ({'project-practice': 0, 'course': 1, 'core': 2}[item['category']], item['title'], item['id']))


def read_skill(skill_id: str) -> dict[str, Any]:
    directory = _skill_path(skill_id)
    documents: dict[str, str] = {}
    for path in directory.rglob("*"):
        if path.is_file() and path.suffix in {".md", ".yaml", ".yml"}:
            documents[str(path.relative_to(directory))] = path.read_text(encoding="utf-8")
    if skill_id.startswith('core.'):
        for name in ('PROJECT_TEACHING_RULES.md', 'PROJECT_PRACTICE_SPEC.md', 'SKILL_SPEC.md'):
            policy = ASSETS / 'docs' / name
            if policy.is_file():
                documents['当前生效规则/' + name] = policy.read_text(encoding='utf-8')
    recorded_rules = None
    try:
        recorded_rules = json.loads((directory / 'RULE_PROVENANCE.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        pass
    return {"id": skill_id, "documents": documents, "ruleProvenance": recorded_rules}


def save_provisional_draft(draft: dict[str, str]) -> dict[str, str]:
    """Persist only a validated draft under skills/generated; never overwrite verified assets."""
    skill_id = draft.get("id", "")
    if not SAFE_SKILL_ID.fullmatch(skill_id):
        raise ValueError("Invalid Skill id.")
    directory = SKILLS_ROOT / "generated" / skill_id.replace(".", "/")
    if directory.exists():
        # Approval is idempotent: a retry after a successful save must not look
        # like a failed approval or overwrite the existing candidate.
        existing = directory / "SKILL.md"
        if existing.exists() and existing.read_text(encoding="utf-8") == draft["skillMarkdown"]:
            return {
                "id": skill_id,
                "path": str(directory.relative_to(ROOT)),
                "status": "provisional",
                "alreadyExists": True,
            }
        raise FileExistsError("A different candidate already uses this Skill id; generate a new version/id.")
    directory.mkdir(parents=True, exist_ok=False)
    files = {
        ".trainer-category.json": json.dumps({'category': draft.get('category', 'course')}, ensure_ascii=False),
        "SKILL.md": draft["skillMarkdown"],
        "curriculum.yaml": draft["curriculumYaml"],
        "concepts/01-overview.md": draft["conceptMarkdown"],
        "exercises/01-practice.md": draft["exerciseMarkdown"],
        "VALIDATION.md": draft["validationChecklist"],
    }
    if isinstance(draft.get('ruleProvenance'), dict):
        files['RULE_PROVENANCE.json'] = json.dumps(draft['ruleProvenance'], ensure_ascii=False, sort_keys=True, indent=2)
    try:
        for relative, content in files.items():
            target = directory / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(target.suffix + ".tmp")
            temporary.write_text(content, encoding="utf-8")
            os.replace(temporary, target)
    except Exception:
        for path in sorted(directory.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink(missing_ok=True)
            elif path.is_dir():
                path.rmdir()
        directory.rmdir()
        raise
    return {"id": skill_id, "path": str(directory.relative_to(ROOT)), "status": "provisional"}
