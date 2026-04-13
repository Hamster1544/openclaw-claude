# OpenClaw Claude Overlay

Этот репозиторий накатывается поверх уже установленного `openclaw` на Linux и добавляет рабочий `claude-cli` runtime с:
- relay для OpenClaw;
- MCP bridge для Telegram/file sending;
- multi-agent spawn в фоне;
- переносом памяти, workspace и агентских данных между машинами.

Ограничения текущей сборки:
- только Linux;
- запускать как `root`;
- на машине уже должны быть установлены `openclaw` и `claude`;
- `root` уже должен быть залогинен в `claude cli`.

## Что installer делает

Installer не переустанавливает `openclaw`, а:
- ставит relay в `/usr/local/bin/claude-openclaw-relay`;
- ставит bridge в `/opt/openclaw-bridge/openclaw_bridge_server.py`;
- создаёт Unix-пользователя `openclaw`, если его ещё нет;
- копирует Claude credentials из `/root/.claude*` в `/home/openclaw`;
- ставит Python venv для bridge;
- даёт `openclaw` passwordless sudo;
- мягко патчит `/root/.openclaw/openclaw.json`, не затирая `channels`, `gateway`, bot token и прочие чужие поля.

## Быстрый перенос

На старой машине:

```bash
cd openclaw-claude-overlay
sudo ./export.sh /root/openclaw-transfer.tar.gz
```

На новой машине:

```bash
git clone <repo>
cd openclaw-claude-overlay
sudo ./import.sh /path/to/openclaw-transfer.tar.gz
sudo ./doctor.sh
```

Или одной командой:

```bash
curl -fsSL https://raw.githubusercontent.com/Hamster1544/openclaw-claude/main/bootstrap.sh | sudo bash -s -- --import /path/to/openclaw-transfer.tar.gz
```

`import.sh` сам:
- восстановит `workspace` и `agents`;
- аккуратно смержит `openclaw.json`;
- затем автоматически запустит `install.sh`, чтобы runtime и конфиг точно совпали с overlay.

## Если нужен только runtime без переноса данных

```bash
git clone <repo>
cd openclaw-claude-overlay
sudo ./install.sh
sudo ./doctor.sh
```

Или одной командой:

```bash
curl -fsSL https://raw.githubusercontent.com/Hamster1544/openclaw-claude/main/bootstrap.sh | sudo bash
```

## Что входит в export

Export включает:
- `/root/.openclaw/openclaw.json`
- `/root/.openclaw/agents/`
- весь текущий workspace агента
- файловую память: `MEMORY.md`, `memory/`, `skills/`, `AGENTS.md`, `SOUL.md`, `USER.md`, `TOOLS.md`, `HEARTBEAT.md`

Export не включает:
- логи
- временные файлы
- Claude credentials
- runtime из `/opt/openclaw-bridge` и `/usr/local/bin`, потому что это восстанавливает `install.sh`

## Файлы

Главные entrypoints:
- `install.sh`
- `export.sh`
- `import.sh`
- `doctor.sh`

Ключевая логика:
- `lib/patch_openclaw_config.py`
- `lib/merge_import_config.py`
- `runtime/claude-openclaw-relay`
- `runtime/openclaw_bridge_server.py`
