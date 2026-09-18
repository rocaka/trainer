"""Consent-based, in-memory editor context shared by the VS Code connector."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Any


LOCK = Lock()
LATEST: dict[str, Any] | None = None


def set_context(payload: dict[str, Any]) -> dict[str, Any]:
    language = str(payload.get("language", "")).strip()
    selection = str(payload.get("selection", ""))
    relative_path = str(payload.get("relativePath", ""))
    if not language or not selection:
        raise ValueError("language and selected code are required.")
    if len(selection) > 24_000:
        raise ValueError("Selected code is too large.")
    stored = {
        "language": language,
        "selection": selection,
        "relativePath": relative_path,
        "diagnostics": payload.get("diagnostics", []),
        "receivedAt": datetime.now(timezone.utc).isoformat(),
    }
    with LOCK:
        global LATEST
        LATEST = stored
    return {"accepted": True, "receivedAt": stored["receivedAt"]}


def latest_context() -> dict[str, Any] | None:
    with LOCK:
        return dict(LATEST) if LATEST else None


def attach_teaching_job(job_id: str) -> None:
    """Associate the latest user-authorized automatic job with its selection."""
    with LOCK:
        if LATEST is not None:
            LATEST["teachingJobId"] = job_id


def draft_brief_from_context(context: dict[str, Any]) -> dict[str, str] | None:
    """Create a bounded candidate brief from code the learner explicitly chose.

    This never crawls the workspace. The bridge supplies only the selection and
    up to five diagnostics after the learner invokes its command.
    """
    selection = str(context.get("selection", "")).strip()
    language = str(context.get("language", "")).strip()
    diagnostics = context.get("diagnostics", [])
    if len(selection) < 40 or not language:
        return None
    messages = [str(item.get("message", "")) for item in diagnostics[:5] if isinstance(item, dict)]
    problem = "; ".join(message for message in messages if message) or "学习者主动选择了这段代码，希望理解其语法、运行时行为与项目作用。"
    return {
        "seed": (
            f"从用户显式选中的 {language} 项目片段自动识别教学需求。\n"
            f"文件：{context.get('relativePath') or 'unknown'}\n"
            f"遇到的问题：{problem}\n代码：\n{selection}\n"
            "请只围绕该片段建立严格的、从必要基础到项目语境的教学 Skill。"
        ),
        "language": language,
        "projectContext": f"用户显式选择：{context.get('relativePath') or 'unknown'}；不读取其它工作区文件。",
    }


def draft_brief_from_signal(payload: dict[str, Any]) -> dict[str, str]:
    """Normalize an explicit in-app question into the same strict draft input."""
    text = str(payload.get("text", "")).strip()
    if len(text) < 20:
        raise ValueError("Please describe the question in at least 20 characters.")
    language = str(payload.get("language", "")).strip()
    project_context = str(payload.get("projectContext", "")).strip()
    return {
        "seed": (
            "从学习者主动提出的问题自动识别教学需求。\n"
            f"问题：{text}\n"
            "请建立严格的 provisional 教学 Skill：先补齐必要基础，再解释当前项目语境；不要把未经证实的推测写成事实。"
        ),
        "language": language or "由来源问题识别",
        "projectContext": project_context or "学习者主动提出的问题；无其它项目扫描。",
    }
