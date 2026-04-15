#!/usr/bin/env python3
"""
YoutubeToDocument Web Backend

실행: .venv/bin/python3 -m uvicorn web.app:app --reload --port 8000
"""
import asyncio
import glob
import json
import os
import sys
import tempfile
import threading
import uuid
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

app = FastAPI(title="YoutubeToDocument")

# ── 정적 파일 서빙 ──────────────────────────────────────────────────
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# ── 스트리밍 stdout 캡처 ────────────────────────────────────────────
import threading as _threading
_local = _threading.local()
_original_stdout = sys.stdout


class _SmartWriter:
    """스레드별 queue로 print를 라우팅"""
    def write(self, text: str):
        _original_stdout.write(text)
        q    = getattr(_local, "queue", None)
        loop = getattr(_local, "loop", None)
        if q and loop and text.strip():
            asyncio.run_coroutine_threadsafe(
                q.put({"type": "log", "text": text.strip()}), loop
            )

    def flush(self):
        _original_stdout.flush()


sys.stdout = _SmartWriter()


# ── 툴 정의 ────────────────────────────────────────────────────────
TOOLS = [
    {
        "name": "process_youtube",
        "label": "YouTube 영상 처리",
        "icon": "▶",
        "description": "YouTube URL을 입력하면 자막/STT 추출 → AI 초안 생성 → AI 검증 → 최종 매뉴얼을 자동 생성합니다.",
        "fields": [
            {"key": "url",      "label": "YouTube URL",    "type": "text",   "required": True,  "placeholder": "https://youtube.com/watch?v=..."},
            {"key": "model",    "label": "생성 AI 모델",    "type": "select", "required": False, "options": ["local","claude","gpt","gemini"], "default": "local"},
            {"key": "reviewer", "label": "검증 AI 모델",    "type": "select", "required": False, "options": ["local","claude","gpt","gemini"], "default": "local"},
        ],
    },
    {
        "name": "apply_feedback",
        "label": "피드백 반영",
        "icon": "✏",
        "description": "기존 매뉴얼에 피드백을 반영하여 재수정합니다.",
        "fields": [
            {"key": "output_dir", "label": "output 폴더",  "type": "output_select", "required": True},
            {"key": "feedback",   "label": "피드백 내용",   "type": "textarea", "required": True, "placeholder": "수정할 내용을 입력하세요"},
            {"key": "model",      "label": "AI 모델",       "type": "select",   "required": False, "options": ["local","claude","gpt","gemini"], "default": "local"},
        ],
    },
    {
        "name": "upload_to_notion",
        "label": "Notion 업로드",
        "icon": "📤",
        "description": "생성된 매뉴얼을 Notion 페이지에 업로드합니다. NOTION_API_KEY, NOTION_PAGE_ID 환경변수 필요.",
        "fields": [
            {"key": "output_dir", "label": "output 폴더", "type": "output_select", "required": True},
        ],
    },
    {
        "name": "get_history",
        "label": "이력 조회",
        "icon": "📋",
        "description": "처리된 YouTube 영상 이력을 조회합니다.",
        "fields": [],
    },
    {
        "name": "get_usage_stats",
        "label": "AI 사용량 통계",
        "icon": "📊",
        "description": "AI 모델 누적 사용량 및 비용 통계를 조회합니다.",
        "fields": [],
    },
    {
        "name": "read_manual",
        "label": "매뉴얼 보기",
        "icon": "📄",
        "description": "생성된 매뉴얼 파일을 읽어 표시합니다.",
        "fields": [
            {"key": "output_dir", "label": "output 폴더", "type": "output_select", "required": True},
            {"key": "file",       "label": "파일 종류",    "type": "select",        "required": False,
             "options": ["final","draft","review"], "default": "final"},
        ],
    },
    {
        "name": "list_outputs",
        "label": "생성 목록",
        "icon": "📁",
        "description": "지금까지 생성된 모든 매뉴얼 목록을 표시합니다.",
        "fields": [],
    },
]

# ── 실행 중인 태스크 ────────────────────────────────────────────────
_tasks: dict[str, asyncio.Queue] = {}


# ── API 엔드포인트 ──────────────────────────────────────────────────
@app.get("/")
async def index():
    return FileResponse(str(static_dir / "index.html"))


@app.get("/api/tools")
async def list_tools():
    return TOOLS


@app.get("/api/outputs")
async def list_outputs():
    if not os.path.exists("output"):
        return []
    items = []
    for d in sorted(os.listdir("output")):
        path = os.path.join("output", d)
        if os.path.isdir(path):
            items.append({"dir": path, "name": d})
    return items


class ExecuteRequest(BaseModel):
    args: dict = {}


@app.post("/api/execute/{tool_name}")
async def execute_tool(tool_name: str, body: ExecuteRequest):
    task_id = str(uuid.uuid4())
    loop = asyncio.get_event_loop()
    q: asyncio.Queue = asyncio.Queue()
    _tasks[task_id] = q

    def worker():
        _local.queue = q
        _local.loop  = loop
        try:
            result = _run_tool(tool_name, body.args)
            asyncio.run_coroutine_threadsafe(
                q.put({"type": "result", "data": result}), loop
            )
        except Exception as e:
            asyncio.run_coroutine_threadsafe(
                q.put({"type": "error", "message": str(e)}), loop
            )
        finally:
            asyncio.run_coroutine_threadsafe(q.put({"type": "done"}), loop)

    threading.Thread(target=worker, daemon=True).start()
    return {"task_id": task_id}


@app.get("/api/stream/{task_id}")
async def stream_events(task_id: str, request=None):
    q = _tasks.get(task_id)
    if not q:
        raise HTTPException(404, "task not found")

    async def generator():
        try:
            while True:
                item = await asyncio.wait_for(q.get(), timeout=300)
                yield {"data": json.dumps(item, ensure_ascii=False)}
                if item["type"] in ("done", "error"):
                    break
        finally:
            _tasks.pop(task_id, None)

    return EventSourceResponse(generator())


# ── 툴 실행 로직 ────────────────────────────────────────────────────
def _run_tool(name: str, args: dict) -> dict:
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


def _process_youtube(args: dict) -> dict:
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

    url           = args["url"]
    model         = args.get("model", "local")
    reviewer_model = args.get("reviewer") or model
    temp_dir      = tempfile.mkdtemp()

    print(f"[1/5] 자막 추출 중...")
    result = get_transcript(url, temp_dir=temp_dir)
    title  = result["title"]

    if result["method"] == "stt":
        print(f"[1/5] STT 변환 중...")
        text, lang = transcribe(result["audio_path"])
    else:
        text, lang = result["text"], result["lang"]

    text = clean_transcript(text, lang=lang or "ko")
    print(f"  ✅ 언어: {lang}, 텍스트: {len(text)}자")

    tracker    = UsageTracker(url=url, title=title, model=model, reviewer=reviewer_model)
    gen_client = LLMClient(model)
    rev_client = LLMClient(reviewer_model)

    print(f"[2/5] 초안 생성 중... (모델: {gen_client.display_name})")
    intent = identify_intent(text, gen_client)
    tracker.add_step("의도 파악", gen_client.display_name, gen_client.pop_usage())
    print(f"  기술명: {intent.get('tech_name','?')}")

    output_dir = get_output_dir(title)
    draft = generate_draft(text, intent, url, gen_client)
    tracker.add_step("초안 생성", gen_client.display_name, gen_client.pop_usage())
    save_markdown(draft, f"{output_dir}/draft.md")
    print(f"  ✅ 초안 저장 → {output_dir}/draft.md")

    print(f"[3/5] AI 검증 중... (모델: {rev_client.display_name})")
    review = review_draft(draft, text, rev_client)
    tracker.add_step("AI 검증", rev_client.display_name, rev_client.pop_usage())
    save_markdown(review, f"{output_dir}/review.md")
    print(f"  ✅ 검증 저장 → {output_dir}/review.md")

    print(f"[4/5] 최종 매뉴얼 생성 중...")
    final = refine_draft(draft, review, gen_client)
    tracker.add_step("최종 생성", gen_client.display_name, gen_client.pop_usage())
    save_markdown(final, f"{output_dir}/final.md")
    print(f"  ✅ 최종 저장 → {output_dir}/final.md")

    print(f"[5/5] 이력 저장 중...")
    usage_path = tracker.save(output_dir)
    entry = new_entry(url, title, model, reviewer_model, output_dir)
    entry["versions"].append(f"{output_dir}/final.md")
    entry["usage"] = {"total_tokens": tracker.total_tokens, "model": model,
                      "estimated_cost_usd": round(tracker.total_cost, 6)}
    save_entry(entry)
    print(f"  ✅ 완료!")

    with open(f"{output_dir}/final.md", encoding="utf-8") as f:
        final_content = f.read()

    return {
        "type": "manual",
        "title": title,
        "tech_name": intent.get("tech_name"),
        "output_dir": output_dir,
        "final_path": f"{output_dir}/final.md",
        "total_tokens": tracker.total_tokens,
        "estimated_cost": tracker.total_cost,
        "content": final_content,
        "usage_steps": tracker.to_dict()["steps"],
    }


def _get_history() -> dict:
    if not os.path.exists("history.json"):
        return {"type": "history", "items": []}
    with open("history.json", encoding="utf-8") as f:
        return {"type": "history", "items": json.load(f)}


def _get_usage_stats() -> dict:
    if not os.path.exists("history.json"):
        return {"type": "usage_stats", "entries": [], "total_tokens": 0, "total_cost": 0}
    with open("history.json", encoding="utf-8") as f:
        history = json.load(f)
    entries = [h for h in history if h.get("usage")]
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


def _apply_feedback(args: dict) -> dict:
    from src.llm_client import LLMClient
    from src.refiner import apply_feedback
    from src.writer import save_markdown

    output_dir = args["output_dir"]
    feedback   = args["feedback"]
    model      = args.get("model", "local")
    final_path = os.path.join(output_dir, "final.md")

    print(f"피드백 반영 중... (모델: {model})")
    with open(final_path, encoding="utf-8") as f:
        current = f.read()

    client  = LLMClient(model)
    updated = apply_feedback(current, feedback, client)

    versions = glob.glob(os.path.join(output_dir, "final_v*.md"))
    version  = len(versions) + 2
    versioned = os.path.join(output_dir, f"final_v{version}.md")
    save_markdown(updated, versioned)
    save_markdown(updated, final_path)
    print(f"  ✅ 수정 완료 → {versioned}")

    return {"type": "manual", "versioned_path": versioned, "content": updated}


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
    title     = os.path.basename(output_dir)
    print(f"Notion 업로드 중...")
    notion_url = upload_to_notion(content, title, "", page_id, api_key)
    print(f"  ✅ 완료 → {notion_url}")
    return {"type": "notion", "url": notion_url}


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
