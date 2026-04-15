#!/usr/bin/env python3
"""
YoutubeToDocument Backend
실행: .venv/bin/python3 -m uvicorn backend.app:app --reload --port 8000
"""
import asyncio
import importlib
import json
import os
import sys
import threading
import uuid
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

app = FastAPI(title="YoutubeToDocument")

# ── 정적 파일 (프론트엔드) ──────────────────────────────────────────
frontend_dir = ROOT / "frontend"
app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")


# ── stdout 캡처 (스레드별 SSE 라우팅) ──────────────────────────────
import threading as _threading
_local = _threading.local()
_original_stdout = sys.stdout


class _SmartWriter:
    def write(self, text: str):
        try:
            _original_stdout.write(text)
        except UnicodeEncodeError:
            # 터미널 인코딩이 ASCII인 경우 한글 등 비ASCII 문자 → 대체 출력
            _original_stdout.write(text.encode("utf-8", errors="replace").decode("ascii", errors="replace"))
        q    = getattr(_local, "queue", None)
        loop = getattr(_local, "loop", None)
        if q and loop and text.strip():
            asyncio.run_coroutine_threadsafe(
                q.put({"type": "log", "text": text.strip()}), loop
            )

    def flush(self):
        _original_stdout.flush()


sys.stdout = _SmartWriter()


# ── MCP 폴더 자동 탐색 및 핸들러 등록 ──────────────────────────────
MCPS_DIR = Path(__file__).parent / "mcps"
_mcp_handlers: dict[str, object] = {}   # tool_name → handler module
_tool_groups: list[dict] = []           # [{group, group_icon, order, tools}]


def _load_mcp_modules():
    global _tool_groups
    groups = []
    for folder in sorted(MCPS_DIR.iterdir()):
        config_path = folder / "config.json"
        handler_path = folder / "handler.py"
        if not (folder.is_dir() and config_path.exists() and handler_path.exists()):
            continue
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)
        groups.append(config)
        module = importlib.import_module(f"backend.mcps.{folder.name}.handler")
        for tool in config.get("tools", []):
            _mcp_handlers[tool["name"]] = module.run
    _tool_groups = sorted(groups, key=lambda g: g.get("order", 99))


_load_mcp_modules()


# ── 실행 중인 태스크 ────────────────────────────────────────────────
_tasks: dict[str, asyncio.Queue] = {}


# ── 엔드포인트 ──────────────────────────────────────────────────────
@app.get("/")
async def index():
    return FileResponse(str(frontend_dir / "index.html"))


@app.get("/api/status")
async def get_status():
    from backend.core.status import get_status as _get_status
    return await _get_status()


@app.get("/api/tools")
async def list_tools():
    """MCP 폴더를 다시 스캔해서 최신 도구 목록 반환"""
    _load_mcp_modules()
    return _tool_groups


@app.get("/api/outputs")
async def list_outputs():
    if not os.path.exists("output"):
        return []
    return [
        {"dir": os.path.join("output", d), "name": d}
        for d in sorted(os.listdir("output"))
        if os.path.isdir(os.path.join("output", d))
    ]


# ── 내장 도구 실행 ────────────────────────────────────────────────────
class ExecuteRequest(BaseModel):
    args: dict = {}


@app.post("/api/execute/{tool_name}")
async def execute_tool(tool_name: str, body: ExecuteRequest):
    handler = _mcp_handlers.get(tool_name)
    if not handler:
        raise HTTPException(404, f"도구 '{tool_name}'를 찾을 수 없습니다.")

    # coming_soon 차단
    for group in _tool_groups:
        for t in group.get("tools", []):
            if t["name"] == tool_name and t.get("status") == "coming_soon":
                raise HTTPException(400, "아직 개발 중인 도구입니다.")

    task_id = str(uuid.uuid4())
    loop    = asyncio.get_event_loop()
    q: asyncio.Queue = asyncio.Queue()
    _tasks[task_id] = q

    def worker():
        _local.queue = q
        _local.loop  = loop
        try:
            result = handler(tool_name, body.args)
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
async def stream_events(task_id: str):
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


# ── 외부 MCP 서버 관리 ────────────────────────────────────────────────
from backend.core import mcp_manager


class MCPServerConfig(BaseModel):
    name: str
    label: str
    command: str
    args: list = []
    cwd: str = ""
    env: dict = {}


@app.get("/api/mcp/servers")
async def list_mcp_servers():
    return mcp_manager.load_servers()


@app.post("/api/mcp/servers")
async def add_mcp_server(config: MCPServerConfig):
    servers = mcp_manager.load_servers()
    if any(s["name"] == config.name for s in servers):
        raise HTTPException(400, "이미 존재하는 서버 이름입니다.")
    servers.append(config.model_dump())
    mcp_manager.save_servers(servers)
    return {"ok": True}


@app.delete("/api/mcp/servers/{name}")
async def delete_mcp_server(name: str):
    servers = [s for s in mcp_manager.load_servers() if s["name"] != name]
    mcp_manager.save_servers(servers)
    return {"ok": True}


@app.get("/api/mcp/servers/{name}/tools")
async def get_mcp_server_tools(name: str):
    try:
        return await mcp_manager.list_tools(name)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"MCP 서버 연결 실패: {e}")


@app.post("/api/mcp/execute/{server_name}/{tool_name}")
async def execute_mcp_tool(server_name: str, tool_name: str, body: ExecuteRequest):
    task_id = str(uuid.uuid4())
    q: asyncio.Queue = asyncio.Queue()
    _tasks[task_id] = q

    async def worker():
        await mcp_manager.call_tool(server_name, tool_name, body.args, q)
        await q.put({"type": "done"})

    asyncio.create_task(worker())
    return {"task_id": task_id}
