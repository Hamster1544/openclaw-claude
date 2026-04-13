# Migration Notes

## Рабочий сценарий

Старая машина:

```bash
sudo ./export.sh /root/openclaw-transfer.tar.gz
```

Новая машина:

```bash
git clone <repo>
cd openclaw-claude-overlay
sudo ./import.sh /path/to/openclaw-transfer.tar.gz
sudo ./doctor.sh
```

## Что делает import

`import.sh`:
- восстанавливает `agents/` и workspace;
- смержит `openclaw.json`, сохранив текущие `channels`, `gateway`, `credentials`, `auth`;
- затем автоматически запускает `install.sh`.

## Что делает install

`install.sh`:
- создаёт пользователя `openclaw`;
- синхронизирует Claude credentials из `/root/.claude*`;
- ставит runtime в `/usr/local/bin` и `/opt/openclaw-bridge`;
- патчит `openclaw.json` под `claude-cli/claude-opus-4-6`;
- включает multi-agent runtime и background subagents.

## Зачем merge вместо replace

Так не теряются:
- `channels.telegram.botToken`
- текущие channel/surface настройки
- gateway auth и другие локальные параметры машины
- уже существующие агенты, если они были настроены вручную
