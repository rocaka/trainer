"""User-authorized, bounded project inspection for teaching-skill generation.

The desktop app only sends a directory after the learner chooses it in the native
file picker.  This module intentionally avoids dependency folders, secrets and
binary assets; it creates a small structural brief rather than uploading a
workspace wholesale.
"""

from __future__ import annotations

import json
import ast
import os
import re
from pathlib import Path
from typing import Any


MAX_FILES = 5000
MAX_TREE_ENTRIES = 100
MAX_SAMPLE_FILES = 5
MAX_SAMPLE_CHARS = 3_200
MAX_TOTAL_SAMPLE_CHARS = 14_000

IGNORED_DIRECTORIES = {
    ".git", ".hg", ".svn", "node_modules", "vendor", ".next", "dist", "build",
    "coverage", ".venv", "venv", "__pycache__", ".turbo", ".cache", "Pods",
}
IGNORED_FILE_NAMES = {".env", ".env.local", ".env.production", ".env.development"}
SOURCE_SUFFIXES = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".sol", ".rs", ".go", ".java", ".kt",
    ".rb", ".php", ".swift", ".c", ".h", ".cpp", ".cs", ".sql", ".vue", ".svelte",
}
MANIFEST_NAMES = {
    "package.json", "pyproject.toml", "requirements.txt", "Cargo.toml", "go.mod",
    "pom.xml", "build.gradle", "docker-compose.yml", "Dockerfile", "README.md",
}


def _is_allowed(path: Path) -> bool:
    return (
        not path.is_symlink()
        and not path.name.lower().startswith('.env')
        and path.name.lower() not in {'credentials.json', 'secrets.json', 'id_rsa', 'id_ed25519'}
        and path.name not in IGNORED_FILE_NAMES
        and path.suffix.lower() in SOURCE_SUFFIXES | {".json", ".toml", ".txt", ".md", ".yml", ".yaml"}
        and not any(part in IGNORED_DIRECTORIES for part in path.parts)
        and not path.name.lower().endswith((".pem", ".key", ".p12", ".mobileprovision"))
    )


def _read_text(path: Path, limit: int) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def _detect_stack(files: list[Path], root: Path) -> list[str]:
    suffixes = {item.suffix.lower() for item in files}
    names = {item.name.lower() for item in files}
    detected: list[str] = []

    def add(name: str, present: bool) -> None:
        if present and name not in detected:
            detected.append(name)

    add("TypeScript", bool({".ts", ".tsx"} & suffixes))
    add("JavaScript", bool({".js", ".jsx"} & suffixes) and "TypeScript" not in detected)
    add("Python", ".py" in suffixes or "pyproject.toml" in names or "requirements.txt" in names)
    add("Solidity", ".sol" in suffixes)
    add("Rust", ".rs" in suffixes or "cargo.toml" in names)
    add("Go", ".go" in suffixes or "go.mod" in names)
    add("Java", ".java" in suffixes or "pom.xml" in names or "build.gradle" in names)
    add("Swift", ".swift" in suffixes)
    add("SQL", ".sql" in suffixes)
    add("Next.js", (root / "next.config.js").exists() or (root / "next.config.mjs").exists() or (root / "next.config.ts").exists())
    add("React", ".tsx" in suffixes or ".jsx" in suffixes)
    add("Vue", ".vue" in suffixes)
    add("Svelte", ".svelte" in suffixes)
    package_json = root / "package.json"
    if package_json.exists():
        raw = _read_text(package_json, 12_000).lower()
        add("Next.js", '"next"' in raw)
        add("PostgreSQL", "postgres" in raw or "pg" in raw or "prisma" in raw)
        add("Node.js", bool({"TypeScript", "JavaScript"} & set(detected)))
    add("Docker", "dockerfile" in names or "docker-compose.yml" in names)
    return detected or ["待 AI 从项目结构识别"]


def inspect_project(path_value: str) -> dict[str, Any]:
    """Return a strictly bounded, user-authorized project brief for the model."""
    root = Path(path_value).expanduser().resolve()
    if not root.is_dir():
        raise ValueError("请选择一个可读取的项目文件夹。")

    files: list[Path] = []
    try:
        for directory, subdirectories, names in os.walk(root, followlinks=False):
            subdirectories[:] = sorted(name for name in subdirectories if name not in IGNORED_DIRECTORIES and not (Path(directory) / name).is_symlink())
            for name in sorted(names):
                item = Path(directory) / name
                if len(files) >= MAX_FILES:
                    break
                if item.is_file() and _is_allowed(item):
                    files.append(item)
            if len(files) >= MAX_FILES:
                break
    except OSError as error:
        raise ValueError(f"无法读取项目目录：{error}") from error

    relative_paths = [item.relative_to(root).as_posix() for item in files]
    stack = _detect_stack(files, root)
    manifests = [item for item in files if item.name in MANIFEST_NAMES]
    source_files = [item for item in files if item.suffix.lower() in SOURCE_SUFFIXES]
    preferred = manifests + source_files
    samples: list[str] = []
    total = 0
    used: set[Path] = set()
    for item in preferred:
        if item in used or len(samples) >= MAX_SAMPLE_FILES or total >= MAX_TOTAL_SAMPLE_CHARS:
            continue
        used.add(item)
        content = _read_text(item, min(MAX_SAMPLE_CHARS, MAX_TOTAL_SAMPLE_CHARS - total))
        if not content.strip():
            continue
        total += len(content)
        samples.append(f"### {item.relative_to(root).as_posix()}\n{content}")

    tree = "\n".join(f"- {name}" for name in relative_paths[:MAX_TREE_ENTRIES]) or "- （未发现可分析的源码文件）"
    sample_text = "\n\n".join(samples) or "（未读取到可安全摘要的文本源码）"
    stack_text = " · ".join(stack)
    project_name = root.name
    documents = {}
    inventory = []
    for item in source_files:
        relative = item.relative_to(root).as_posix()
        content = _read_text(item, 100000)
        symbols = []
        if item.suffix == '.py':
            try:
                tree_node = ast.parse(content)
                symbols = [{'name': node.name, 'line': node.lineno, 'end': getattr(node, 'end_lineno', node.lineno), 'kind': type(node).__name__}
                           for node in ast.walk(tree_node) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
            except SyntaxError:
                pass
        else:
            for number, line in enumerate(content.splitlines(), 1):
                if re.search(r'\b(function|func|fn|class|interface|struct|contract)\s+\w+|(?:const|let)\s+\w+.*=>', line):
                    symbols.append({'name': line.strip()[:160], 'line': number, 'kind': 'lexical-candidate'})
        # Project material is stored as inspectable documents, never executed.
        documents['project/source/' + relative + '.md'] = '# 源文件：' + relative + '\n\n```' + item.suffix[1:] + '\n' + content + '\n```\n'
        inventory.append({'path': relative, 'lines': len(content.splitlines()), 'truncated': item.stat().st_size > 100000, 'symbols': symbols, 'coverage': '待教学'})
    documents['project/STRUCTURE.md'] = '# 项目结构\n\n' + '\n'.join('- ' + p for p in relative_paths) + '\n\n扫描上限：5000 文件。跳过依赖、构建产物、符号链接与常见密钥文件。\n'
    documents['project/INVENTORY.md'] = '# 文件与函数覆盖清单\n\n```json\n' + json.dumps(inventory, ensure_ascii=False, indent=2) + '\n```\n\nPython 使用 AST；其他语言使用词法候选识别，不能视为完整语义解析。\n'
    return {
        "projectName": project_name,
        "generationMode": "project-import",
        "stack": stack,
        "fileCount": len(files),
        "projectDocuments": documents,
        "seed": (
            "用户已在桌面端明确授权导入以下本地项目，仅基于受限的结构摘要与代表性源码片段生成教学内容。\n"
            f"项目：{project_name}\n识别技术栈：{stack_text}\n"
            f"已纳入结构摘要的文件数：{len(files)}（上限 {MAX_FILES}；已排除依赖目录、构建产物与常见密钥文件）\n"
            f"项目结构：\n{tree}\n\n代表性文件（最多 {MAX_SAMPLE_FILES} 个）：\n{sample_text}\n\n"
            "按 PROJECT_IMPORT_PROTOCOL_V1 规划：读懂 → 跑通 → 修改 → 测试 → 独立重建关键模块。"
            "从真实项目补足基础到高级知识，每个阶段写清源码依据、产物、提交材料和验收标准。"
            "当前只是有限摘要：明确已确认、待核对和待补材料，后续按源码模块展开，不把候选概览当作完整课程。"
        ),
        "language": " · ".join(stack),
        "projectContext": f"用户授权导入的本地项目“{project_name}”；技术栈：{stack_text}；仅使用受限摘要，不读取依赖目录、构建产物或密钥文件。",
    }
