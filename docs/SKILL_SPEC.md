# Skill Specification v0.1

## Purpose

A Skill is a versioned, inspectable package that tells the learning agent how to teach a bounded technical capability. It is not merely reference documentation and it is not unrestricted prompt text.

## Minimum layout

```text
<domain>/<skill-id>/
  SKILL.md              # Agent instructions and front matter
  curriculum.yaml       # outcomes, prerequisites, competency mapping
  concepts/             # learner-facing explanations
  exercises/            # prediction, debugging, build, review tasks
  labs/                 # runnable or simulated experiments
  assessments/          # rubrics and mastery evidence
  sources/              # provenance/version data
  tests/                # schema and executable-example validation
```

## Required front matter

```yaml
id: blockchain.solidity.evm
title: Solidity and the EVM
version: 0.1.0
status: provisional # core | verified | provisional | personalized
scope: "Reading and safely experimenting with basic EVM contracts"
contexts:
  languages: [Solidity]
  runtimes: [EVM]
  frameworks: []
prerequisites: [programming.fundamentals]
outcomes: []
safetyClass: high # low | medium | high
sources: []
generatedBy: null
validatedAt: null
```

## Automated generation contract

The knowledge builder must first search the concept graph and existing Skills. It creates a draft only when an actual gap exists. Every generated draft must declare the signal that prompted it, its target language/runtime/framework/project context, distinguish sourced claims from inference, include at least one assessable interaction, and stay in `provisional` status. A domain Skill must declare its exact prerequisites from `core/curriculum-map.yaml` and a beginner bridge; it cannot use advanced code as its first lesson. Validation rejects missing metadata, cyclic prerequisites, unsourced high-risk claims, malformed examples, assessments without evidence criteria, a context-less code sample, and domain Skills with no foundational path.

## Promotion contract

Promotion to `verified` requires successful schema/exercise checks and an approval record. Updates never overwrite an earlier version in place; a new semantic version preserves learner reproducibility and auditability.
