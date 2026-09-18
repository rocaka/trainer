# Curriculum Charter

## Why a charter exists

Trainer's content must remain coherent even though AI may draft new lessons. This charter is the stable contract for what technical understanding means, how it is sequenced, and what evidence is sufficient to advance.

## Universal learning dimensions

Every domain Skill maps its content to these dimensions:

1. **Purpose:** what real problem a technology solves and why alternatives exist.
2. **Concept:** the minimal abstractions, terminology, and relationships.
3. **Expression:** language syntax, APIs, tooling, and conventions.
4. **Mechanism:** execution, state, resource use, and failure behaviour.
5. **Practice:** implementation, testing, debugging, and review in a realistic task.
6. **Engineering:** design trade-offs, operations, maintainability, and collaboration.
7. **Safety:** security, privacy, correctness, and system boundaries.
8. **Transfer:** applying the model in another language, framework, or scenario.

## Stable curriculum domains

```text
Computing & programming foundations
  data, types, control flow, functions, data structures, algorithms,
  runtime, operating systems, networking, debugging

Software engineering foundations
  version control, testing, architecture, APIs, observability, performance,
  deployment, collaboration, code review, secure development

Application systems
  web frontend/backend, databases, caching, queues, mobile, cloud, containers

AI systems
  math/ML basics, deep learning, transformers, LLMs, RAG, agents, evaluation,
  deployment, safety, governance and cost

Blockchain systems
  cryptography, distributed systems, consensus, transaction models, EVM,
  contracts, DeFi, cross-chain systems, indexing, protocol security

Language/framework specializations
  TypeScript, Python, Rust, Solidity, Go, SQL, React, Node.js, Docker, etc.
```

## Non-negotiable beginner sequence

No domain-specific Skill may make unfamiliar source code the learner's first screen. A complete beginner starts with everyday intent and moves through this ordered spine:

```text
0. What code is: an instruction expressed precisely
1. Values and labels: text, numbers, true/false, variables
2. Expressions and changes: calculate, compare, update
3. Conditions: choose a path when something is true/false
4. Functions: name and reuse a small set of steps
5. Data structures: keep related information together
6. Errors and debugging: observe, predict, repair
7. Files, modules and a tiny project
8. Language-specific syntax and runtime
9. Domain systems: Web, database, AI, blockchain, cloud, security
```

The learner can declare existing experience or pass diagnostics to enter later. However, a Skill must make its required foundation visible and offer a one-click bridge lesson. A planner selects only the prerequisites needed to safely reach the learner's current project objective; it never hides those prerequisites behind unexplained code.

## Mastery rubric

| Level | Evidence required |
|---|---|
| L0 Recognize | Identify terms and relevant code locations |
| L1 Explain | Accurately explain a known snippet in plain language |
| L2 Predict | Predict behaviour before execution and justify it |
| L3 Repair | Diagnose and repair a bounded failure |
| L4 Build | Implement a small feature with tests |
| L5 Design/review | Compare options, articulate trade-offs, and flag risks |
| L6 Transfer/teach | Solve an analogous problem in a new context or teach it clearly |

Passing a multiple-choice question is never enough to claim L3 or higher. Evidence is stored with the context, rubric, date, and confidence.

## Required unit composition

Each published unit needs: declared outcome; prerequisites; conceptual explanation; minimum runnable example; misconception catalogue; prediction; experiment; application task; review prompt; transfer task; assessment rubric; source/version metadata; and safety classification.

For foundation units, the first explanation must use a human goal and visual/interactive decomposition before showing syntax. The first code sample contains one new concept only. Terms such as `mapping`, `async`, `transaction`, `type`, or `function` may not be introduced as assumed vocabulary.

## Contextual foundation, not generic language class

The concept graph is shared, but a lesson is always compiled for the learner's actual context. Trainer derives context in this priority order:

```text
active project/runtime → active Skill → selected language → beginner preference
```

Thus, “values and labels” remains the same concept, while its teaching surface changes:

| Context | First relevant expression | What is introduced now |
|---|---|---|
| TypeScript project | `let name = "小明"` | label and text value |
| Python project | `name = "小明"` | label and text value |
| Solidity contract | `string memory name = "小明"` | label and text value; type/storage words are visibly deferred |
| SQL lesson | `SELECT '小明' AS name` | named result value |

No learner is sent to a separate generic programming track unless there is no project, language, or Skill context. Even then, the app asks for a target language early and changes examples immediately.

## Spacing and adaptation

The learner model schedules review when an important concept is likely to be forgotten, when a related project event occurs, or when a misconception repeats. It must not increase difficulty merely because time elapsed; advancement depends on evidence.
