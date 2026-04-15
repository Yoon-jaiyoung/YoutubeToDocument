"""System MCP 핸들러 — get_history, get_usage_stats, read_manual, list_outputs"""
import json
import os


def run(tool_name: str, args: dict) -> dict:
    if tool_name == "get_history":
        return _get_history()
    elif tool_name == "get_usage_stats":
        return _get_usage_stats()
    elif tool_name == "read_manual":
        return _read_manual(args)
    elif tool_name == "list_outputs":
        return _list_outputs()
    raise ValueError(f"Unknown tool: {tool_name}")


def _get_history() -> dict:
    if not os.path.exists("history.json"):
        return {"type": "history", "items": []}
    with open("history.json", encoding="utf-8") as f:
        return {"type": "history", "items": json.load(f)}


def _get_usage_stats() -> dict:
    if not os.path.exists("history.json"):
        return {"type": "usage_stats", "entries": 0, "total_tokens": 0, "total_cost": 0, "model_stats": {}}
    with open("history.json", encoding="utf-8") as f:
        history = json.load(f)

    entries      = [h for h in history if h.get("usage")]
    total_tokens = sum(h["usage"]["total_tokens"] for h in entries)
    total_cost   = sum(h["usage"].get("estimated_cost_usd", 0) for h in entries)

    model_stats: dict = {}
    for h in entries:
        m = h["usage"].get("model", "unknown")
        model_stats.setdefault(m, {"tokens": 0, "cost": 0.0, "count": 0})
        model_stats[m]["tokens"] += h["usage"]["total_tokens"]
        model_stats[m]["cost"]   += h["usage"].get("estimated_cost_usd", 0)
        model_stats[m]["count"]  += 1

    return {
        "type": "usage_stats",
        "entries": len(entries),
        "total_tokens": total_tokens,
        "total_cost": total_cost,
        "model_stats": model_stats,
    }


def _read_manual(args: dict) -> dict:
    output_dir = args["output_dir"]
    file_type  = args.get("file", "final")
    path       = os.path.join(output_dir, f"{file_type}.md")
    if not os.path.exists(path):
        raise FileNotFoundError(f"파일 없음: {path}")
    with open(path, encoding="utf-8") as f:
        content = f.read()
    return {"type": "manual", "path": path, "file": file_type, "content": content}


def _list_outputs() -> dict:
    if not os.path.exists("output"):
        return {"type": "outputs", "items": []}
    items = []
    for d in sorted(os.listdir("output")):
        path = os.path.join("output", d)
        if os.path.isdir(path):
            files = [f for f in os.listdir(path) if f.endswith(".md")]
            items.append({"dir": path, "name": d, "files": files})
    return {"type": "outputs", "items": items}
