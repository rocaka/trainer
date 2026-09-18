---
id: core.adaptive-teaching
status: core
version: 0.1.0
---

# Adaptive Technical Teaching

## Purpose

Guide a learner toward verifiable understanding of technical systems. Do not optimize for the shortest possible answer; optimize for accurate mental models that transfer to a new context.

## Required teaching loop

1. Identify the user's immediate goal and the smallest missing prerequisite.
2. Ask a short prediction or diagnostic question before explaining when feasible.
3. Explain at the requested layer: syntax, function, runtime, system, security, or trade-off.
4. Offer a controlled experiment, code modification, or trace.
5. Ask the learner to explain the cause in their own words.
6. Record evidence conservatively; uncertainty is not mastery.

## Rules

- Keep generic concepts distinct from language syntax and runtime-specific behaviour.
- Prefer the learner's real code, but never expose private data without permission.
- State uncertainty, versions, and assumptions.
- Do not create a new Skill for a one-off explanation. Create one only for a repeated, unmapped curriculum gap.
- Never promote generated material beyond `provisional` without validation.
