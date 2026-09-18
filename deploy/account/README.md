# Trainer account service

From the repository root run:

```sh
docker compose -f deploy/account/compose.yaml up -d --build
```

Place an HTTPS reverse proxy in front of loopback port 8080. Limit bodies to
1 MiB and rate-limit `/v1/session` before public exposure. Back up the accounts
volume. Do not publish the desktop Gateway on port 8787.
Set TRAINER_CLOUD_ENDPOINT to your HTTPS account service URL in the environment
that launches Trainer. GitHub credentials remain in the macOS Keychain.

GitHub identity is checked at https://api.github.com/user; numeric IDs own the
records. The cloud discards GitHub tokens and stores hashed expiring sessions.
Reference: https://docs.github.com/en/rest/users/users#get-the-authenticated-user

All routes use JSON POST. `/v1/session` takes githubToken, deviceId (32 hex),
deviceName. Other routes require a Trainer Bearer session:

- /v1/sync: changes (up to 100), cursor; optimistic revisions, paginated download.
- /v1/devices: device list.
- /v1/devices/revoke: deviceId; revokes all sessions for the selected device.
- /v1/sign-out: revoke this device.
- /v1/account/delete: confirmed=true; deletes this user's cloud data.

Current limits: manual batches, memory-only desktop sessions (explicit login
after restart), conflicts retained locally for review. Remote learning evidence
remains a summary, not a fabricated local assessment. Course bodies, custom
avatar files, code, answer text, terminal output and model keys are excluded.
Automatic background sync and conflict resolution UI remain follow-up work.

Deployment acceptance: TLS and rate limits, backup/restore drill, image build on
target server, live GitHub login and two-device tests against the actual host.
