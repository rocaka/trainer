# Trainer Architecture

## Design: local-first, agent-assisted, explicit permissions

```text
SwiftUI macOS application
  ├─ Learning workbench (native shell + code/visual views)
  ├─ Learner model (SQLite, local)
  ├─ Skill repository (Markdown/YAML files, local/Git-backed)
  ├─ Concept graph index (SQLite)
  ├─ Local agent gateway (future localhost service)
  └─ Editor connectors (VS Code extension first)
          ↕ explicit, scoped user consent
AI provider / optional local model / isolated exercise runners
```

## Source-of-truth model

| Asset | Storage | Why |
|---|---|---|
| Teaching rules and concepts | Markdown + YAML | Human-readable, diffable, reviewable |
| Dependency graph and learner state | SQLite | Fast queries, durable local personalization |
| Exercises | Source files + tests | Behaviour can be verified |
| Generated drafts | `skills/generated/` | Never overwrite trusted material |
| Provenance | YAML front matter / source manifests | Version and trust are inspectable |

## Agent roles

- **Signal detector:** detects intent, topic, misconception, and missing knowledge from consented context.
- **Curriculum planner:** selects the shortest safe path through prerequisites.
- **Teaching coach:** asks, explains, adapts scaffolding, and records evidence.
- **Knowledge builder:** drafts Skills and learning artifacts when a true curriculum gap exists.
- **Validator:** validates schema, sources, code tests, dependency graph, and risk class.

No role can silently grant itself filesystem, terminal, wallet, or editor write permissions.

## Implemented MVP services

The Python Gateway now provides asynchronous generation jobs, a file-backed `skills/generated/` repository, SQLite learning evidence, a deliberately limited Python experiment interpreter, and a consent-based editor-context endpoint. Generated Skills require explicit client approval after validation before they are written to disk.

## VS Code integration

A VS Code extension communicates with the local app over a per-install authenticated localhost channel or Unix socket. The v1 connector may send only the active selection, language, relative path, and diagnostics after user action. Project indexing, terminal output, and patch application are separate opt-in capabilities.
