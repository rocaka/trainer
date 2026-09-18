# Model-Driven Teaching Asset Pipeline

## Core product loop

```text
detailed source Skill / Markdown + project context
  → context resolver (language, runtime, framework, learner level)
  → OpenAI Gateway
  → structured provisional draft
  → deterministic validation
  → in-app preview and human approval
  → skills/generated/<id>/
  → optional reviewed promotion to skills/verified/<id>/
```

This is Trainer's central content-production capability. A model is not asked to “write a lesson” in isolation. It is constrained by the core teaching Skill, the curriculum dependency map, the Skill schema, the caller's target language/runtime, and an explicit output schema.

## Inputs

The generator accepts:

- a detailed source Skill, Markdown, technical brief, or project need;
- active language, runtime, framework, and project role;
- optional learner evidence and desired capability level;
- the maintained core pedagogy and dependency map.

Attached source text is reference material. It never overrides safety, trust-state, or curriculum rules.

## Required generated assets

The model returns a `provisional` draft containing:

1. `SKILL.md`: bounded agent teaching instructions;
2. `curriculum.yaml`: outcomes, prerequisites, and context;
3. concept lesson: human intent before syntax;
4. prediction/exercise asset: observable learning evidence;
5. validation checklist: assertions for review.

Generation is staged. Stage 1 produces a bounded, structured blueprint that can be schema-validated quickly. Only after it passes does a later Python expansion task deepen a selected concept, lab, or assessment. This prevents a single giant response from being cut off and makes every expansion independently reviewable.

## Validation gates

The local validator rejects drafts with missing metadata, invalid IDs, missing `provisional` trust state, no prerequisite declaration, no language/runtime context, or no assessable exercise. The next implementation step is schema/YAML parsing, source-verification, executable lab tests, concept graph cycle detection, and reviewer approval.

## API boundary

The macOS client calls only `http://127.0.0.1:8787`. The **Python Gateway** can route to OpenAI Responses or DeepSeek's OpenAI-compatible chat-completions API. It reads provider-specific keys from its own environment or macOS Keychain and returns only the generated draft. It binds to loopback, does not write files, and does not permit model-issued filesystem or shell tool calls.

For production, the loopback Gateway becomes an authenticated backend with per-user spending caps, redaction, audit logs, rate limiting, model version pinning, and content review workflow.

## Current operational setup

```bash
cd /Users/cloud/Projects/trainer/gateway
python3 server.py
```

The Trainer app's Skill Library then offers **生成候选 Skill**. A draft is previewed with its validation result and remains non-persistent until a future explicit approval action.
