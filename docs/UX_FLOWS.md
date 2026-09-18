# Trainer UX Flows

## Interaction principles

- Teach from the learner's actual code whenever possible.
- Ask one discriminating question at a time.
- Make invisible state visible: stack, data flow, storage, transaction, or model pipeline.
- Reduce assistance as evidence of mastery improves.
- Never conflate an AI-generated explanation with a verified fact.

## Core flow: understand selected code

```text
VS Code selection or pasted code
  → language/runtime detection
  → concept and prerequisite lookup
  → learner-model match
  → minimal learning goal
  → prediction prompt
  → execution visualization or sandbox experiment
  → learner's explanation and feedback
  → mastery evidence + suggested next action
```

Example: for a Solidity `transfer`, the app exposes generic concepts (function, parameter, conditional), language concepts (`mapping`, `uint256`, `external`), and runtime concepts (transaction, `msg.sender`, atomic state change, gas) separately.

## Core flow: deliberate practice

1. The coach presents a small changed requirement or a controlled bug.
2. The learner predicts an output, chooses a cause, or edits a single location.
3. A local sandbox or deterministic simulator shows the result.
4. The coach explains the causal path, names the misconception if applicable, and records evidence.
5. A second transfer question confirms learning in a different code context.

## Core flow: automatic curriculum growth

1. The signal detector observes repeated learner confusion, a novel project technology, or an unmapped concept.
2. The planner checks existing Skills and prerequisite graph before proposing content.
3. The knowledge builder creates a **provisional** asset with outcomes, sources, exercises, and tests.
4. The validator checks metadata, references, dependency cycles, code examples, and safety class.
5. The asset can personalize the current lesson; only a reviewed/validated asset becomes **verified** shared curriculum.

## Workbench layout

```text
Sidebar                 Main canvas                         Coach panel
Learning map            Source / runtime / experiment        Current goal
Skills library           Layered explanation                  Prediction
Project context          Diff or state visualization           Feedback
```

The prototype implements this layout with a focused EVM transfer lesson.

## Visual system: macOS glass

Trainer uses a transparent macOS window with a native vibrancy backdrop. The workspace panes are translucent materials rather than opaque application panels. Interactive cards use a subtle glass border and stronger selected-state colour.

Transparency is not allowed to reduce instructional readability: code, long explanations, answer options, and text input retain a high-contrast frosted surface. The app respects the system accessibility preference for increased contrast; a future Appearance setting will offer `System`, `Glass`, and `High contrast` modes.
