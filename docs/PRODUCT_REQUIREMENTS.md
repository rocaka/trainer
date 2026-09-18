# Trainer Product Requirements Document

## 1. Product thesis

AI is making it possible to build software without typing every line, but it does not automatically give people the ability to read, evaluate, repair, or safely extend what was built. Trainer is a local-first macOS application that turns a user's live code, errors, and goals into an adaptive technical education.

The product is not an answer bot, a static course catalog, or an IDE replacement. It is an AI technical mentor embedded beside the user's real editor and projects.

## 2. Problem

Learners face three linked failures:

1. Generated code hides the concepts and trade-offs needed to own a project.
2. Traditional courses are disconnected from the code and mistakes the learner has today.
3. Technical knowledge changes faster than a fixed curriculum can be updated.

## 3. Target users

| User | Primary job | Initial product value |
|---|---|---|
| AI-assisted builder | Understand and safely modify generated project code | Code microscope and project-guided lessons |
| Aspiring developer | Build durable fundamentals while making projects | Guided experiments and capability map |
| Web3 builder | Learn chain-specific execution and security, not just syntax | Runtime visualizations and security labs |
| AI application builder | Understand RAG/agents beyond API calls | Data-flow experiments and evaluation habits |

## 4. Product promise

After a learning session, a user should be able to explain what the relevant code does, predict a meaningful change in behaviour, make a scoped modification, and identify its limits or risks.

## 5. Learning model

Every unit follows the same loop:

```text
real problem → prediction → observable execution → controlled change
→ learner explanation → project application → mastery update
```

The competency ladder is L0 recognition, L1 explanation, L2 prediction, L3 repair, L4 implementation, L5 design/review, and L6 transfer/teaching. Promotion requires evidence, not time spent.

## 6. Scope for the first releasable product

### Included

- Native macOS workbench for code inspection and structured learning.
- Import/paste of a focused code snippet.
- JavaScript/TypeScript, Python, and Solidity concept identification.
- Explanation at syntax, function, runtime, system, and safety layers.
- Prediction and micro-experiment exercises.
- A local learner profile and concept mastery record.
- Versioned Skills: core pedagogy, programming fundamentals, AI/RAG, and Solidity/EVM.
- VS Code bridge design, initially sending selected code to Trainer.

### Explicitly excluded from v1

- Autonomous terminal execution or applying edits without preview and approval.
- Holding private keys, signing blockchain transactions, or connecting production wallets.
- Claiming assessment is a formal certification.
- Supporting every programming language or framework with equal depth.

## 7. Success measures

| Metric | Initial target |
|---|---|
| Explain-to-predict conversion | 70% of learners make a prediction after an explanation |
| Verified understanding | 50% correctly complete a follow-up transfer task |
| Return rate | 35% of activated users return within seven days |
| Unsafe autonomous changes | 0 |
| Skill quality | 100% promoted Skills have sources, outcomes, and validation evidence |

## 8. Product requirements

1. The app must clearly distinguish AI inference, verified curriculum, and user-specific drafts.
2. It must reveal the smallest missing prerequisite before expanding a lesson.
3. It must prefer a question or experiment to an unsolicited long explanation.
4. It must retain learner mastery locally and let the user inspect/delete it.
5. It must request explicit approval before reading a project, executing commands, or writing files.
6. Skills must be file-based, versioned, inspectable, and mapped to a concept graph.

## 9. Future capability boundaries

The product can grow to cover web development, databases, cloud infrastructure, AI, blockchain, and security through domain Skills. The stable cross-domain foundation remains computation, programming, engineering practice, systems, security, and transfer.
