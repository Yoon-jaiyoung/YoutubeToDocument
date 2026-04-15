import json
import os
from datetime import datetime


HISTORY_FILE = "history.json"


def load_history() -> list:
    if not os.path.exists(HISTORY_FILE):
        return []
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_entry(entry: dict) -> None:
    history = load_history()
    history.append(entry)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def find_entry(url: str) -> dict | None:
    history = load_history()
    for entry in reversed(history):
        if entry.get("url") == url:
            return entry
    return None


def new_entry(url: str, title: str, model: str, reviewer: str, output_dir: str) -> dict:
    return {
        "url": url,
        "title": title,
        "model": model,
        "reviewer": reviewer,
        "output_dir": output_dir,
        "created_at": datetime.now().isoformat(),
        "feedbacks": [],
        "versions": [],
    }


def add_feedback(entry: dict, feedback: str, version_path: str) -> None:
    entry["feedbacks"].append({
        "text": feedback,
        "at": datetime.now().isoformat(),
        "file": version_path,
    })
    entry["versions"].append(version_path)


def display_history() -> None:
    history = load_history()
    if not history:
        print("이력이 없습니다.")
        return
    print(f"\n{'='*60}")
    print(f"{'#':<4} {'제목':<30} {'모델':<10} {'날짜':<20}")
    print(f"{'='*60}")
    for i, entry in enumerate(history, 1):
        created = entry.get("created_at", "")[:10]
        title = entry.get("title", "")[:28]
        model = entry.get("model", "")[:8]
        print(f"{i:<4} {title:<30} {model:<10} {created:<20}")
        print(f"     URL: {entry.get('url', '')}")
        print(f"     출력: {entry.get('output_dir', '')}")
        feedbacks = entry.get("feedbacks", [])
        if feedbacks:
            print(f"     피드백 수: {len(feedbacks)}건")
        print()
