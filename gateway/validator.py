"""Deterministic validation for model-generated Trainer teaching drafts."""

from __future__ import annotations

import re
from typing import Any


REQUIRED_FIELDS = (
    "id",
    "title",
    "summary",
    "skillMarkdown",
    "curriculumYaml",
    "conceptMarkdown",
    "exerciseMarkdown",
    "validationChecklist",
)


def validate_import_quality(draft):
    """Deterministic presence gate only; not semantic correctness or mastery."""
    errors = []
    for field, headings in [('exerciseMarkdown', ['读懂', '跑通', '修改', '测试', '独立重建', '提交材料']),
                            ('validationChecklist', ['验收标准'])]:
        value = draft.get(field, '')
        value = value if isinstance(value, str) else ''
        # Ignore fenced examples: sample headings cannot satisfy the document contract.
        value = re.sub(r'```[^\n]*\n[\s\S]*?(?:```|$)', '', value)
        sections = re.findall(r'^#{2,3}\s+([^\n]+)\n([\s\S]*?)(?=^#{1,3}\s|\Z)', value, re.MULTILINE)
        for heading in headings:
            if not any(heading in title and len(body.strip()) >= 10 for title, body in sections):
                errors.append(f'导入课程缺少「{heading}」章节或具体说明（{field}），请优化候选后再审批。')
    return {'valid': not errors, 'errors': errors, 'level': 'structure-only', 'protocol': 'PROJECT_IMPORT_PROTOCOL_V1'}


def validate_draft(draft: dict[str, Any]) -> dict[str, Any]:
    """Return a deterministic validation result; never promote draft trust state."""
    errors: list[str] = []
    for field in REQUIRED_FIELDS:
        if not isinstance(draft.get(field), str) or not draft[field].strip():
            errors.append(f"Missing {field}.")

    skill_id = draft.get("id", "")
    if skill_id and not re.fullmatch(r"[a-z][a-z0-9.-]+", skill_id):
        errors.append("Skill id must use lowercase letters, digits, dots, and hyphens.")
    if "status: provisional" not in draft.get("skillMarkdown", ""):
        errors.append("Generated Skill must remain provisional.")
    curriculum = draft.get("curriculumYaml", "")
    if "prerequisites:" not in curriculum:
        errors.append("Curriculum must declare prerequisites.")
    if "contexts:" not in curriculum:
        errors.append("Curriculum must declare language/runtime context.")
    exercise = draft.get("exerciseMarkdown", "")
    if not re.search(r"预测|experiment|练习|exercise", exercise, flags=re.IGNORECASE):
        errors.append("An assessable prediction or exercise is required.")
    return {"valid": not errors, "errors": errors}
