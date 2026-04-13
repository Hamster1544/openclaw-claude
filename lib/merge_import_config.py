#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path


PRESERVE_TOP_LEVEL = {"channels", "gateway", "credentials", "auth"}


def merge_lists(current: list, imported: list):
    if not current:
        return copy.deepcopy(imported)
    if not imported:
        return copy.deepcopy(current)
    return copy.deepcopy(imported)


def merge_agent_lists(current: list, imported: list):
    by_id = {}
    order = []
    for source in (current, imported):
        for item in source:
            if not isinstance(item, dict):
                continue
            agent_id = str(item.get("id") or "").strip()
            if not agent_id:
                continue
            if agent_id not in by_id:
                by_id[agent_id] = {}
                order.append(agent_id)
            by_id[agent_id] = merge_dicts(by_id[agent_id], item)
    return [by_id[agent_id] for agent_id in order]


def merge_dicts(current: dict, imported: dict):
    result = copy.deepcopy(current)
    for key, value in imported.items():
        if key in PRESERVE_TOP_LEVEL and key in current:
            continue
        if key == "list" and isinstance(value, list) and isinstance(current.get(key), list):
            result[key] = merge_agent_lists(current[key], value)
            continue
        cur_value = current.get(key)
        if isinstance(cur_value, dict) and isinstance(value, dict):
            result[key] = merge_dicts(cur_value, value)
        elif isinstance(cur_value, list) and isinstance(value, list):
            result[key] = merge_lists(cur_value, value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--current", required=True)
    parser.add_argument("--imported", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    current_path = Path(args.current)
    imported_path = Path(args.imported)
    output_path = Path(args.output)

    current = json.loads(current_path.read_text()) if current_path.exists() else {}
    imported = json.loads(imported_path.read_text()) if imported_path.exists() else {}
    merged = merge_dicts(current if isinstance(current, dict) else {}, imported if isinstance(imported, dict) else {})

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
