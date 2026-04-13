#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
from datetime import datetime, timezone
from pathlib import Path


def deep_copy(value):
    return copy.deepcopy(value)


def ensure_dict(parent: dict, key: str) -> dict:
    value = parent.get(key)
    if not isinstance(value, dict):
        value = {}
        parent[key] = value
    return value


def ensure_list(parent: dict, key: str) -> list:
    value = parent.get(key)
    if not isinstance(value, list):
        value = []
        parent[key] = value
    return value


def merge_allow_all(value):
    if value == "*":
        return ["*"]
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
        if "*" not in items:
            items.append("*")
        return items
    return ["*"]


def ensure_agent(agents_list: list, agent_id: str, *, workspace: str, default: bool = False, name: str | None = None):
    entry = None
    for item in agents_list:
        if isinstance(item, dict) and str(item.get("id") or "").strip() == agent_id:
            entry = item
            break
    if entry is None:
        entry = {"id": agent_id}
        agents_list.append(entry)

    if name and not entry.get("name"):
        entry["name"] = name
    if default:
        entry["default"] = True
    if workspace:
        entry["workspace"] = workspace

    subagents = ensure_dict(entry, "subagents")
    subagents["allowAgents"] = merge_allow_all(subagents.get("allowAgents"))
    return entry


def patch_config(data: dict, *, relay_path: str, bridge_path: str, model: str, workspace: str) -> dict:
    cfg = deep_copy(data)

    agents = ensure_dict(cfg, "agents")
    defaults = ensure_dict(agents, "defaults")

    model_cfg = defaults.get("model")
    if not isinstance(model_cfg, dict):
        model_cfg = {"primary": str(model_cfg).strip()} if model_cfg else {}
        defaults["model"] = model_cfg
    model_cfg["primary"] = model

    if workspace:
        defaults["workspace"] = workspace

    cli_backends = ensure_dict(defaults, "cliBackends")
    claude_cli = ensure_dict(cli_backends, "claude-cli")
    claude_cli["command"] = relay_path
    claude_cli["serialize"] = False
    claude_cli["sessionMode"] = "always"

    subagents = ensure_dict(defaults, "subagents")
    subagents["allowAgents"] = merge_allow_all(subagents.get("allowAgents"))

    tools = ensure_dict(cfg, "tools")
    agent_to_agent = ensure_dict(tools, "agentToAgent")
    agent_to_agent["enabled"] = True
    agent_to_agent["allow"] = merge_allow_all(agent_to_agent.get("allow"))

    agents_list = ensure_list(agents, "list")
    ensure_agent(agents_list, "main", workspace=workspace, default=True, name="Main")
    ensure_agent(agents_list, "news", workspace=workspace, name="News")

    overlay = ensure_dict(cfg, "overlay")
    overlay["openclawClaudeOverlay"] = {
        "installed": True,
        "relay": relay_path,
        "bridge": bridge_path,
        "model": model,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }
    return cfg


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--relay-path", required=True)
    parser.add_argument("--bridge-path", required=True)
    parser.add_argument("--model", default="claude-cli/claude-opus-4-6")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    path = Path(args.config)
    if path.exists():
      data = json.loads(path.read_text())
    else:
      data = {}

    patched = patch_config(
        data,
        relay_path=args.relay_path,
        bridge_path=args.bridge_path,
        model=args.model,
        workspace=args.workspace,
    )

    text = json.dumps(patched, ensure_ascii=False, indent=2) + "\n"
    if args.write:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
