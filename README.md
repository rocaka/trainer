# Trainer

Trainer is a local-first macOS learning companion for people who want to understand the code and systems that AI helps them build. It teaches through a loop of **inspect, predict, experiment, explain, and apply**—rather than simply generating an answer.

This repository contains the product foundation and a runnable SwiftUI prototype of the learning workbench.

## What works now

- Three-pane native macOS learning workspace: learning map, code microscope, and AI coach.
- A beginner-first start: human intent → values and labels → functions → projects, before domain code.
- A compact, guided Solidity transfer lesson that becomes available only after the learner chooses the advanced path.
- Prediction, evidence-based feedback, and a learner capability record.
- A browsable, versioned Skill repository with core teaching rules and initial domain Skills.
- A local Python AI Gateway (DeepSeek by default; OpenAI optional) and in-app Skill Builder. It generates schema-constrained, validated `provisional` teaching drafts from a detailed source Skill/Markdown and project context; only an explicit approval writes them to the local candidate repository.
- A privacy-bounded VS Code bridge: the learner explicitly sends selected code and diagnostics, and Trainer uses that context to switch the teaching language.
- A safe, visible Python micro-lab for beginners. It interprets only assignments, values, basic arithmetic, lists, and `print`, then shows the learning trace; it never executes a workspace, shell command, file, import, or network request.
- Documented product requirements, UX flows, architecture, safety model, and delivery roadmap.

## Run

Requirements: macOS 14+ and Xcode 15+ command-line tools.

```bash
cd Trainer
swift run Trainer
```

## Repository map

```text
docs/       Product, UX, architecture, safety, and roadmap documents
skills/     Versioned teaching assets for the agent
Trainer/    Native SwiftUI macOS prototype
gateway/    Python local-only OpenAI API bridge; never exposes its key to the app
vscode-trainer-extension/  Explicit-selection VS Code integration
```

## Product principle

AI may create and revise candidate teaching assets, but it must not silently promote them to trusted curriculum. Every asset has an owner, source/version metadata, validation state, and a learning outcome.

## Development launch

Start the local gateway in one terminal, then launch the app in another:

```bash
cd gateway && python3 server.py
cd Trainer && swift run Trainer
```

To make an unsigned local application bundle instead, run `./scripts/package-macos.sh`; the result is `dist/Trainer.app`.
