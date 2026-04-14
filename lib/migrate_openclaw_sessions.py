#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import shutil
import time
from pathlib import Path


SESSION_FIELDS_TO_DROP = [
    "authProfileOverride",
    "authProfileOverrideSource",
    "authProfileOverrideCompactionCount",
    "modelProvider",
    "model",
    "contextTokens",
]


def deep_copy(value):
    return copy.deepcopy(value)


def load_json(path: Path):
    return json.loads(path.read_text())


def agent_model_map(config: dict) -> tuple[dict[str, str], str]:
    agents = config.get("agents") or {}
    defaults = agents.get("defaults") or {}
    default_model = defaults.get("model")
    if isinstance(default_model, dict):
        default_model = str(default_model.get("primary") or "").strip()
    else:
        default_model = str(default_model or "").strip()

    models: dict[str, str] = {}
    for entry in agents.get("list") or []:
        if not isinstance(entry, dict):
            continue
        agent_id = str(entry.get("id") or "").strip()
        if not agent_id:
            continue
        model = entry.get("model")
        if isinstance(model, dict):
            model = str(model.get("primary") or "").strip()
        else:
            model = str(model or "").strip()
        if model:
            models[agent_id] = model
    return models, default_model


def migrate_store(path: Path, *, models: dict[str, str], default_model: str) -> dict:
    data = load_json(path)
    if not isinstance(data, dict):
        return {"path": str(path), "changedCount": 0, "changed": []}

    changed: list[dict] = []
    for session_key, entry in data.items():
        if not isinstance(entry, dict):
            continue
        parts = str(session_key).split(":")
        if len(parts) < 2 or parts[0] != "agent":
            continue
        agent_id = parts[1]
        model = models.get(agent_id) or default_model
        if not str(model or "").startswith("claude-cli/"):
            continue

        removed = []
        for field in SESSION_FIELDS_TO_DROP:
            if field in entry:
                entry.pop(field, None)
                removed.append(field)
        if removed:
            changed.append({"sessionKey": session_key, "removed": removed})

    if changed:
        backup = path.with_name(f"{path.name}.overlay-pre-provider-migrate-{int(time.time())}.bak")
        shutil.copy2(path, backup)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        return {
            "path": str(path),
            "backup": str(backup),
            "changedCount": len(changed),
            "changed": changed,
        }

    return {"path": str(path), "changedCount": 0, "changed": []}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--state-dir", required=True)
    args = parser.parse_args()

    config = load_json(Path(args.config))
    models, default_model = agent_model_map(config)
    results = []
    state_dir = Path(args.state_dir)
    for path in sorted(state_dir.glob("agents/*/sessions/sessions.json")):
        results.append(
            migrate_store(
                path,
                models=deep_copy(models),
                default_model=default_model,
            )
        )

    print(json.dumps({"stores": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
