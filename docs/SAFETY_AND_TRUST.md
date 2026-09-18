# Safety and Trust Model

## Trust states

| State | Meaning | Teaching use |
|---|---|---|
| `core` | Maintained product principles and fundamental concepts | Always available |
| `verified` | Reviewed, sourced, and validated asset | Standard instruction |
| `provisional` | AI-created or newly updated material with basic checks | Clearly labelled exploration |
| `personalized` | Private material derived from a user's own project | Only for that learner unless promoted |

## Controls

- Show source, version, validation date, and trust state for curriculum content.
- Require preview and approval for edits; require separate approval for command execution.
- Never request or store seed phrases, private keys, passwords, or production credentials.
- Treat blockchain transaction construction and security guidance as high-risk: use testnets/simulations by default and identify assumptions.
- Redact obvious secrets before external model calls and offer local-only mode.
- Give the learner access to view, export, and delete their learning record.

## Skill promotion gate

A generated Skill may become verified only when it has: a stable ID; declared outcomes and prerequisites; source metadata; a safety class; exercises with assessable evidence; validation result; and a human or policy-defined approval record.
