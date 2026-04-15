"""Notion MCP 핸들러 — upload_to_notion"""
import os


def run(tool_name: str, args: dict) -> dict:
    if tool_name == "upload_to_notion":
        return _upload_to_notion(args)
    raise ValueError(f"Unknown tool: {tool_name}")


def _upload_to_notion(args: dict) -> dict:
    from src.notion_uploader import upload_to_notion

    output_dir = args["output_dir"]
    final_path = os.path.join(output_dir, "final.md")
    api_key    = os.environ.get("NOTION_API_KEY")
    page_id    = os.environ.get("NOTION_PAGE_ID")

    if not api_key or not page_id:
        raise EnvironmentError("NOTION_API_KEY 또는 NOTION_PAGE_ID 환경변수가 없습니다.")

    with open(final_path, encoding="utf-8") as f:
        content = f.read()

    title = os.path.basename(output_dir)
    print(f"Notion 업로드 중...")
    notion_url = upload_to_notion(content, title, "", page_id, api_key)
    print(f"  ✅ 완료 → {notion_url}")

    return {"type": "notion", "url": notion_url}
