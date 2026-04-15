import os
import re


def sanitize_filename(title: str) -> str:
    title = re.sub(r'[\\/*?:"<>|]', "", title)
    title = re.sub(r'\s+', "_", title.strip())
    return title[:80]


def get_output_dir(title: str, base_dir: str = "output") -> str:
    safe_title = sanitize_filename(title)
    output_dir = os.path.join(base_dir, safe_title)
    os.makedirs(output_dir, exist_ok=True)
    return output_dir


def save_markdown(content: str, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
