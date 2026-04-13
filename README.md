# OpenClaw Claude Overlay

Этот репозиторий накатывается поверх уже установленного `openclaw` на Linux и добавляет `claude-cli` runtime как бережный overlay, а не как жёсткую замену существующей конфигурации.

Что делает overlay:
- ставит relay для OpenClaw;
- ставит MCP bridge для Telegram/file sending и background subagents;
- сохраняет существующие `channels`, `gateway`, bot token и прочие чужие поля;
- по умолчанию переводит все агентские модели на `claude-cli`, сохраняя `opus/sonnet`, если агент уже был на Claude;
- для не-Claude моделей использует выбранную overlay-модель по умолчанию;
- автоматически раздаёт runtime user доступ ко всем workspace из конфига.

## Базовые требования

- Linux
- запуск от `root`
- уже установлен `openclaw`
- уже установлен `claude`
- кто-то уже залогинен в `claude cli`

По умолчанию installer ищет OpenClaw state так:
1. `OVERLAY_CONFIG_PATH`, если задан
2. `/root/.openclaw/openclaw.json`, если он существует
3. `~/.openclaw/openclaw.json`

## Что installer делает

Installer не переустанавливает `openclaw`, а:
- ставит relay в `/usr/local/bin/claude-openclaw-relay` по умолчанию;
- ставит bridge в `/opt/openclaw-bridge/openclaw_bridge_server.py` по умолчанию;
- создаёт Unix-пользователя `openclaw`, если его ещё нет;
- копирует Claude credentials из `OVERLAY_CLAUDE_SOURCE_HOME` или из detected target home;
- ставит Python venv для bridge;
- даёт runtime user passwordless sudo;
- патчит `openclaw.json` идемпотентно.

## Поведение patcher

По умолчанию patcher работает в режиме `overlay-all`:
- `anthropic/claude-opus-*` -> `claude-cli/claude-opus-*`
- `anthropic/claude-sonnet-*` -> `claude-cli/claude-sonnet-*`
- уже существующие `claude-cli/*` остаются как есть
- не-Claude модели переводятся на `OVERLAY_MODEL`

Это значит:
- агент, который был на Opus, останется на Opus;
- агент, который был на Sonnet, останется на Sonnet;
- агент на другом провайдере тоже перейдёт на наш `claude-cli` путь.

Если нужен более мягкий режим:
- `OVERLAY_MODEL_REWRITE_MODE=claude-only`
- `OVERLAY_FORCE_DEFAULT_MODEL=0`
- `OVERLAY_FORCE_AGENT_MODELS=0`

## Полезные env vars

- `OVERLAY_CONFIG_PATH` — явный путь к `openclaw.json`
- `OVERLAY_STATE_DIR` — явный путь к `.openclaw`
- `OVERLAY_TARGET_HOME` — home владельца OpenClaw state
- `OVERLAY_TARGET_USER` — владелец OpenClaw state
- `OVERLAY_OPENCLAW_USER` — Unix user, под которым будет крутиться Claude runtime
- `OVERLAY_OPENCLAW_HOME` — home этого runtime user
- `OVERLAY_CLAUDE_SOURCE_HOME` — откуда копировать `.claude*`
- `OVERLAY_WORKSPACE` — явный workspace path
- `OVERLAY_MODEL` — default Claude model, по умолчанию `claude-cli/claude-opus-4-6`
- `OVERLAY_MODEL_REWRITE_MODE` — `overlay-all` или `claude-only`
- `OVERLAY_FORCE_DEFAULT_MODEL=1` — принудительно заменить default model
- `OVERLAY_FORCE_AGENT_MODELS=1` — принудительно заменить явные agent models
- `OVERLAY_ENSURE_NEWS_AGENT=1` — добавить `news` агент
- `OVERLAY_TAKE_WORKSPACE_OWNERSHIP=1` — если ACL недоступны, рекурсивно сменить владельца workspace на runtime user

## Быстрая установка

```bash
git clone https://github.com/Hamster1544/openclaw-claude.git
cd openclaw-claude
sudo ./install.sh
sudo ./doctor.sh
```

Одной командой:

```bash
curl -fsSL https://raw.githubusercontent.com/Hamster1544/openclaw-claude/main/bootstrap.sh | sudo bash
```

## Перенос

На старой машине:

```bash
cd openclaw-claude
sudo ./export.sh /root/openclaw-transfer.tar.gz
```

На новой машине:

```bash
git clone https://github.com/Hamster1544/openclaw-claude.git
cd openclaw-claude
sudo ./import.sh /path/to/openclaw-transfer.tar.gz
sudo ./doctor.sh
```

Или одной командой:

```bash
curl -fsSL https://raw.githubusercontent.com/Hamster1544/openclaw-claude/main/bootstrap.sh | sudo bash -s -- --import /path/to/openclaw-transfer.tar.gz
```

## Что входит в export

Export включает:
- detected `openclaw.json`
- `agents/`
- текущий workspace

Export не включает:
- runtime из `/opt/openclaw-bridge` и `/usr/local/bin`
- временные файлы
- Claude credentials

## Файлы

Главные entrypoints:
- `install.sh`
- `export.sh`
- `import.sh`
- `doctor.sh`

Ключевая логика:
- `lib/common.sh`
- `lib/patch_openclaw_config.py`
- `lib/merge_import_config.py`
- `runtime/claude-openclaw-relay`
- `runtime/openclaw_bridge_server.py`
