# Trainer local Python model gateway

The gateway is the only development component that holds an AI-provider key; the macOS app never receives it. It binds only to `127.0.0.1`. Generation returns a draft for review; a separate explicit approval endpoint is the only route that writes a `provisional` generated Skill to disk.

On macOS, Trainer can instead read a key named `trainer-openai-api-key` for account `Trainer` from Keychain. This avoids placing the secret in `.env`, source code, or the client app.

## Start

```bash
cd gateway
python3 server.py
```

Check setup without generating content:

```bash
curl http://127.0.0.1:8787/health
```

## Contract

`POST /v1/skills/generate` accepts a detailed `seed`, optional `language`, and optional `projectContext`. It sends core teaching rules, the curriculum map, and the Skill specification to the model. The model must return a JSON-schema-constrained provisional draft. The gateway then validates the result before sending it back to the app.

The gateway supports `deepseek` (default) and `openai` providers. It reads `trainer-deepseek-api-key` or `trainer-openai-api-key` from macOS Keychain. For development-only overrides, set `DEEPSEEK_API_KEY` or `OPENAI_API_KEY`, then set `TRAINER_MODEL_PROVIDER=deepseek|openai` before starting it. Use `DEEPSEEK_MODEL` or `OPENAI_MODEL` to select a model, and `TRAINER_MAX_OUTPUT_TOKENS` to cap generated draft size. The implementation uses Python standard library only.

DeepSeek uses the official OpenAI-compatible chat-completions API. Trainer forces a strict function-call schema, then runs its own deterministic validator before returning a draft.

For production, replace this local process with an authenticated server-side gateway with user identity, rate limits, secret redaction, budgets, auditing, and an approval workflow.

## Additional local contracts

- `POST /v1/skills/generate/jobs` and `GET /v1/jobs/<id>` run generation as an in-process development job so the native UI stays responsive.
- `POST /v1/skills/<id>/approve` accepts a validator-approved draft and writes it under `skills/generated/`; it cannot modify `verified` assets.
- `POST /v1/evidence` and `GET /v1/learners/<id>/profile` keep learning evidence in local SQLite.
- `POST /v1/editor/context` accepts only user-selected VS Code context. `GET /v1/editor/context` returns the latest selection to the native app.
- `POST /v1/labs/python/run` is a deliberately restricted AST interpreter for beginner experiments. It supports simple assignment and one-argument `print`; imports, calls other than `print`, files, networking, and arbitrary code execution are rejected.
