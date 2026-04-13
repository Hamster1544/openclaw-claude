# Data Layout

Overlay переносит не runtime-мусор, а пользовательский профиль OpenClaw.

## Что входит в export/import

State:
- `/root/.openclaw/openclaw.json`
- `/root/.openclaw/agents/`

Workspace:
- `AGENTS.md`
- `SOUL.md`
- `USER.md`
- `TOOLS.md`
- `HEARTBEAT.md`
- `MEMORY.md`
- `memory/`
- `skills/`
- остальные рабочие файлы проекта

## Что не входит

- `/opt/openclaw-bridge`
- `/usr/local/bin/claude-openclaw-relay`
- `/tmp/openclaw`
- временные логи
- venv
- `node_modules`
- Claude credentials из `/root/.claude*`

## Принцип

Память должна жить в файлах workspace и в state OpenClaw. Тогда перенос на другую машину не теряет контекст и не зависит от временных Claude session ids.
