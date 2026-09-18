# MVP Release Checklist

## Included in the local MVP

- Native macOS learning workbench and frosted-glass UI.
- Python-only AI Gateway with DeepSeek/OpenAI provider adapters.
- Keychain-backed local key lookup; no keys in the application client or repository.
- Background Skill generation, deterministic validation, user approval, and file-backed provisional Skill storage.
- Dynamic Skill index, local SQLite learner evidence, restricted Python experiments, and a consent-triggered VS Code bridge.

## Before distributing outside this computer

- [ ] Replace in-process job map with durable, authenticated job storage.
- [ ] Add model budget controls, cancellation, retry policy, redaction, and audit events.
- [ ] Add source provenance and review UI before promotion from `provisional` to `verified`.
- [ ] Implement content rendering from every saved Skill plus generated-lab sandboxing.
- [ ] Package and sign the VS Code extension; test it against supported VS Code versions.
- [ ] Add unit/integration/UI tests, accessibility testing, and a privacy review.
- [ ] Code-sign and notarize the `.app` with the project's Apple Developer identity.

## Build a local development app

```bash
cd /Users/cloud/Projects/trainer
./scripts/package-macos.sh
open dist/Trainer.app
```

The output is an unsigned development bundle. It is not yet suitable for public distribution.
