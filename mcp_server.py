#!/usr/bin/env python3
"""
YoutubeToDocument MCP Server

Claude Desktop 등록 방법:
{
  "mcpServers": {
    "youtube-to-document": {
      "command": "/path/to/.venv/bin/python3",
      "args": ["/path/to/YoutubeToDocument/mcp_server.py"],
      "cwd": "/path/to/YoutubeToDocument"
    }
  }
}
"""
import asyncio
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mcp.types as types
from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

app = Server("youtube-to-document")


# ── Tool 정의 ────────────────────────────────────────────────────────
TOOLS = [
    types.Tool(
        name="process_youtube",
        description="YouTube 기술 영상 URL을 처리하여 구조화된 기술 매뉴얼을 생성합니다. "
                    "자막 추출(없으면 STT), AI 초안 생성, AI 검증, 최종본 생성을 자동 수행합니다.",
        inputSchema={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "YouTube 영상 URL"},
                "model": {
                    "type": "string",
                    "enum": ["local", "claude", "gpt", "gemini"],
                    "default": "local",
                    "description": "매뉴얼 생성 AI 모델",
                },
                "reviewer": {
                    "type": "string",
                    "enum": ["local", "claude", "gpt", "gemini"],
                    "description": "검증 AI 모델 (미지정 시 model과 동일)",
                },
            },
            "required": ["url"],
        },
    ),
    types.Tool(
        name="get_history",
        description="처리된 YouTube 영상 이력을 조회합니다.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    types.Tool(
        name="get_usage_stats",
        description="AI 모델 누적 사용량 및 비용 통계를 조회합니다.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    types.Tool(
        name="read_manual",
        description="생성된 기술 매뉴얼 파일 내용을 읽습니다.",
        inputSchema={
            "type": "object",
            "properties": {
                "output_dir": {"type": "string", "description": "output 디렉토리 경로"},
                "file": {
                    "type": "string",
                    "enum": ["draft", "review", "final"],
                    "default": "final",
                },
            },
            "required": ["output_dir"],
        },
    ),
    types.Tool(
        name="apply_feedback",
        description="생성된 매뉴얼에 피드백을 반영하여 수정합니다.",
        inputSchema={
            "type": "object",
            "properties": {
                "output_dir": {"type": "string", "description": "output 디렉토리 경로"},
                "feedback": {"type": "string", "description": "반영할 피드백 내용"},
                "model": {
                    "type": "string",
                    "enum": ["local", "claude", "gpt", "gemini"],
                    "default": "local",
                },
            },
            "required": ["output_dir", "feedback"],
        },
    ),
    types.Tool(
        name="upload_to_notion",
        description="생성된 매뉴얼을 Notion에 업로드합니다. NOTION_API_KEY, NOTION_PAGE_ID 환경변수 필요.",
        inputSchema={
            "type": "object",
            "properties": {
                "output_dir": {"type": "string", "description": "output 디렉토리 경로"},
            },
            "required": ["output_dir"],
        },
    ),
    types.Tool(
        name="list_outputs",
        description="생성된 매뉴얼 목록을 조회합니다.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
]


@app.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return TOOLS


@app.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> list[types.ContentBlock]:
    args = arguments or {}
    try:
        result = await asyncio.to_thread(_execute_tool, name, args)
        return [types.TextContent(type="text", text=result)]
    except Exception as e:
        return [types.TextContent(type="text", text=f"❌ 오류: {e}")]


# ── 동기 툴 실행 (스레드에서 실행) ──────────────────────────────────────
def _execute_tool(name: str, args: dict) -> str:
    if name == "process_youtube":
        return _process_youtube(args)
    elif name == "get_history":
        return _get_history()
    elif name == "get_usage_stats":
        return _get_usage_stats()
    elif name == "read_manual":
        return _read_manual(args)
    elif name == "apply_feedback":
        return _apply_feedback(args)
    elif name == "upload_to_notion":
        return _upload_to_notion(args)
    elif name == "list_outputs":
        return _list_outputs()
    else:
        raise ValueError(f"알 수 없는 툴: {name}")


def _process_youtube(args: dict) -> str:
    from src.extractor import get_transcript
    from src.transcriber import transcribe
    from src.preprocessor import clean_transcript
    from src.llm_client import LLMClient
    from src.generator import identify_intent, generate_draft
    from src.reviewer import review_draft
    from src.refiner import refine_draft
    from src.writer import get_output_dir, save_markdown
    from src.history import new_entry, save_entry
    from src.usage_tracker import UsageTracker

    url = args["url"]
    model = args.get("model", "local")
    reviewer_model = args.get("reviewer", model)
    temp_dir = tempfile.mkdtemp()

    result = get_transcript(url, temp_dir=temp_dir)
    title = result["title"]

    if result["method"] == "stt":
        text, lang = transcribe(result["audio_path"])
    else:
        text, lang = result["text"], result["lang"]

    text = clean_transcript(text, lang=lang or "ko")

    tracker = UsageTracker(url=url, title=title, model=model, reviewer=reviewer_model)
    gen_client = LLMClient(model)
    rev_client = LLMClient(reviewer_model)

    intent = identify_intent(text, gen_client)
    tracker.add_step("의도 파악", gen_client.display_name, gen_client.pop_usage())

    output_dir = get_output_dir(title)
    draft = generate_draft(text, intent, url, gen_client)
    tracker.add_step("초안 생성", gen_client.display_name, gen_client.pop_usage())
    save_markdown(draft, f"{output_dir}/draft.md")

    review = review_draft(draft, text, rev_client)
    tracker.add_step("AI 검증", rev_client.display_name, rev_client.pop_usage())
    save_markdown(review, f"{output_dir}/review.md")

    final = refine_draft(draft, review, gen_client)
    tracker.add_step("최종 생성", gen_client.display_name, gen_client.pop_usage())
    save_markdown(final, f"{output_dir}/final.md")
    tracker.save(output_dir)

    entry = new_entry(url, title, model, reviewer_model, output_dir)
    entry["versions"].append(f"{output_dir}/final.md")
    entry["usage"] = {"total_tokens": tracker.total_tokens, "model": model}
    save_entry(entry)

    return json.dumps({
        "title": title,
        "tech_name": intent.get("tech_name"),
        "output_dir": output_dir,
        "final_path": f"{output_dir}/final.md",
        "total_tokens": tracker.total_tokens,
    }, ensure_ascii=False)


def _get_history() -> str:
    from src.history import load_history
    return json.dumps(load_history(), ensure_ascii=False, indent=2)


def _get_usage_stats() -> str:
    import io
    from contextlib import redirect_stdout
    from src.usage_tracker import display_usage_stats
    buf = io.StringIO()
    with redirect_stdout(buf):
        display_usage_stats()
    return buf.getvalue()


def _read_manual(args: dict) -> str:
    output_dir = args["output_dir"]
    file_type = args.get("file", "final")
    path = os.path.join(output_dir, f"{file_type}.md")
    if not os.path.exists(path):
        return f"파일을 찾을 수 없습니다: {path}"
    with open(path, encoding="utf-8") as f:
        return f.read()


def _apply_feedback(args: dict) -> str:
    from src.llm_client import LLMClient
    from src.refiner import apply_feedback
    from src.writer import save_markdown

    output_dir = args["output_dir"]
    feedback = args["feedback"]
    model = args.get("model", "local")
    final_path = os.path.join(output_dir, "final.md")

    with open(final_path, encoding="utf-8") as f:
        current = f.read()

    client = LLMClient(model)
    updated = apply_feedback(current, feedback, client)

    import glob
    versions = glob.glob(os.path.join(output_dir, "final_v*.md"))
    version = len(versions) + 2
    versioned = os.path.join(output_dir, f"final_v{version}.md")
    save_markdown(updated, versioned)
    save_markdown(updated, final_path)
    return json.dumps({"versioned_path": versioned, "updated": True}, ensure_ascii=False)


def _upload_to_notion(args: dict) -> str:
    from src.notion_uploader import upload_to_notion
    output_dir = args["output_dir"]
    final_path = os.path.join(output_dir, "final.md")
    api_key = os.environ.get("NOTION_API_KEY")
    page_id = os.environ.get("NOTION_PAGE_ID")
    if not api_key or not page_id:
        return "NOTION_API_KEY 또는 NOTION_PAGE_ID 환경변수가 설정되지 않았습니다."
    with open(final_path, encoding="utf-8") as f:
        content = f.read()
    title = os.path.basename(output_dir)
    url = upload_to_notion(content, title, "", page_id, api_key)
    return json.dumps({"notion_url": url}, ensure_ascii=False)


def _list_outputs() -> str:
    if not os.path.exists("output"):
        return json.dumps([], ensure_ascii=False)
    items = []
    for d in sorted(os.listdir("output")):
        path = os.path.join("output", d)
        if os.path.isdir(path):
            files = os.listdir(path)
            items.append({"dir": path, "name": d, "files": files})
    return json.dumps(items, ensure_ascii=False)


# ── 서버 실행 ────────────────────────────────────────────────────────
async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="youtube-to-document",
                server_version="1.0.0",
                capabilities=app.get_capabilities(
                    notification_options=None,
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    asyncio.run(main())
