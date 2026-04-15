#!/bin/bash
cd "$(dirname "$0")"

# 한글 등 UTF-8 인코딩 강제
export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1

# 기존 서버 종료
PID=$(lsof -ti:8000 2>/dev/null)
if [ -n "$PID" ]; then
  kill "$PID"
  echo "🛑 기존 서버 종료 (PID: $PID)"
fi

# .env 로드
if [ -f ".env" ]; then
  set -a && source .env && set +a
  echo "✅ .env 로드 완료"
else
  echo "⚠️  .env 없음 — .env.example 참고"
fi

# 모델 상태
echo "── AI 모델 ──────────────────────"
[ -n "$ANTHROPIC_API_KEY" ] && echo "  ✅ Claude" || echo "  ⬜ Claude"
[ -n "$OPENAI_API_KEY"    ] && echo "  ✅ GPT"    || echo "  ⬜ GPT"
[ -n "$GOOGLE_API_KEY"    ] && echo "  ✅ Gemini" || echo "  ⬜ Gemini"
echo "─────────────────────────────────"

PORT=${PORT:-8000}
echo ""
echo "🚀 http://localhost:$PORT"
echo ""

open "http://localhost:$PORT" &
sleep 1

.venv/bin/python3 -m uvicorn backend.app:app --reload --port "$PORT"
