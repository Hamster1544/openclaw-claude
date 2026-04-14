#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
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


def normalize_workspace_path(value: str | None) -> str:
    path = str(value or "").strip()
    if len(path) >= 3 and path[1:3] == ":\\":
        path = path[2:].replace("\\", "/")
        if not path.startswith("/"):
            path = "/" + path
    return path


def normalize_model_ref(value: str | None, default_model: str, *, rewrite_mode: str, force_any: bool = False) -> str | None:
    ref = str(value or "").strip()
    if not ref:
        return default_model if force_any else None
    if ref.startswith("claude-cli/"):
        return ref
    if ref.startswith("anthropic/claude-"):
        return "claude-cli/" + ref.split("/", 1)[1]
    if ref.startswith("claude-"):
        return "claude-cli/" + ref
    if force_any or rewrite_mode == "overlay-all":
        return default_model
    return ref


def patch_model_block(value, *, default_model: str, rewrite_mode: str, force_primary: bool = False):
    if isinstance(value, dict):
        result = deep_copy(value)
        primary = normalize_model_ref(result.get("primary"), default_model, rewrite_mode=rewrite_mode, force_any=force_primary)
        if primary:
            result["primary"] = primary
        fallbacks = result.get("fallbacks")
        if isinstance(fallbacks, list):
            result["fallbacks"] = [
                normalize_model_ref(item, default_model, rewrite_mode=rewrite_mode, force_any=False) or item
                for item in fallbacks
            ]
        return result
    rewritten = normalize_model_ref(value, default_model, rewrite_mode=rewrite_mode, force_any=force_primary)
    return rewritten or value


def ensure_agent(agents_list: list, agent_id: str, *, workspace: str | None = None, default: bool = False, name: str | None = None):
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
    if default and "default" not in entry:
        entry["default"] = True
    current_workspace = normalize_workspace_path(entry.get("workspace"))
    if current_workspace:
        entry["workspace"] = current_workspace
    elif workspace:
        entry["workspace"] = workspace

    return entry


def patch_agent_models(agents_list: list, *, default_model: str, rewrite_mode: str, force_agent_models: bool):
    for entry in agents_list:
        if not isinstance(entry, dict):
            continue
        workspace = normalize_workspace_path(entry.get("workspace"))
        if workspace:
            entry["workspace"] = workspace
        if "model" in entry:
            entry["model"] = patch_model_block(
                entry.get("model"),
                default_model=default_model,
                rewrite_mode=rewrite_mode,
                force_primary=force_agent_models,
            )
        subagents = ensure_dict(entry, "subagents")
        if not subagents.get("allowAgents"):
            subagents["allowAgents"] = ["*"]


def patch_model_catalog(defaults: dict, default_model: str):
    catalog = ensure_dict(defaults, "models")
    catalog.setdefault(default_model, {})


def patch_config(
    data: dict,
    *,
    relay_path: str,
    bridge_path: str,
    model: str,
    workspace: str,
    rewrite_mode: str,
    force_default_model: bool,
    force_agent_models: bool,
    ensure_news_agent: bool,
    runtime_user: str,
    runtime_home: str,
    state_dir: str,
) -> dict:
    cfg = deep_copy(data)

    agents = ensure_dict(cfg, "agents")
    defaults = ensure_dict(agents, "defaults")

    model_cfg = patch_model_block(
        defaults.get("model"),
        default_model=model,
        rewrite_mode=rewrite_mode,
        force_primary=force_default_model or not defaults.get("model"),
    )
    defaults["model"] = model_cfg if isinstance(model_cfg, dict) else {"primary": model_cfg}

    current_default_workspace = normalize_workspace_path(defaults.get("workspace"))
    if current_default_workspace:
        defaults["workspace"] = current_default_workspace
    elif workspace:
        defaults["workspace"] = workspace

    patch_model_catalog(defaults, model)

    cli_backends = ensure_dict(defaults, "cliBackends")
    claude_cli = ensure_dict(cli_backends, "claude-cli")
    claude_cli["command"] = relay_path
    claude_cli["serialize"] = False
    claude_cli["sessionMode"] = "always"

    tools = ensure_dict(cfg, "tools")
    agent_to_agent = ensure_dict(tools, "agentToAgent")
    agent_to_agent["enabled"] = True
    if not agent_to_agent.get("allow"):
        agent_to_agent["allow"] = ["*"]

    agents_list = ensure_list(agents, "list")
    if not agents_list:
        ensure_agent(agents_list, "main", workspace=workspace, default=True, name="Main")
    patch_agent_models(
        agents_list,
        default_model=model,
        rewrite_mode=rewrite_mode,
        force_agent_models=force_agent_models,
    )

    if ensure_news_agent:
        ensure_agent(agents_list, "news", workspace=workspace, name="News")

    return cfg


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--relay-path", required=True)
    parser.add_argument("--bridge-path", required=True)
    parser.add_argument("--model", default="claude-cli/claude-opus-4-6")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--rewrite-mode", choices=["claude-only", "overlay-all"], default="overlay-all")
    parser.add_argument("--force-default-model", type=int, default=0)
    parser.add_argument("--force-agent-models", type=int, default=0)
    parser.add_argument("--ensure-news-agent", type=int, default=0)
    parser.add_argument("--runtime-user", default="openclaw")
    parser.add_argument("--runtime-home", default="/home/openclaw")
    parser.add_argument("--state-dir", default="/root/.openclaw")
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
        rewrite_mode=args.rewrite_mode,
        force_default_model=bool(args.force_default_model),
        force_agent_models=bool(args.force_agent_models),
        ensure_news_agent=bool(args.ensure_news_agent),
        runtime_user=args.runtime_user,
        runtime_home=args.runtime_home,
        state_dir=args.state_dir,
    )

    text = json.dumps(patched, ensure_ascii=False, indent=2) + "\n"
    if args.write:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
