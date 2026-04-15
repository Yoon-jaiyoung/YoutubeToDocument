"""로컬 LLM 및 API 키 설정 현황"""
import os
import httpx


async def get_status() -> dict:
    local_ok    = False
    local_model = None
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get("http://localhost:8080/v1/models")
            if r.status_code == 200:
                data   = r.json()
                models = data.get("data", [])
                local_ok    = True
                local_model = models[0]["id"] if models else "local"
    except Exception:
        pass

    return {
        "local": {"ok": local_ok, "model": local_model},
        "models": {
            "local":  local_ok,
            "claude": bool(os.environ.get("ANTHROPIC_API_KEY")),
            "gpt":    bool(os.environ.get("OPENAI_API_KEY")),
            "gemini": bool(os.environ.get("GOOGLE_API_KEY")),
        },
    }
