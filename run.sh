#!/bin/bash
# YoutubeToDocument 웹 서버 시작 스크립트
# 사용법: ./run.sh

cd "$(dirname "$0")"

# 한글 등 UTF-8 인코딩 강제 설정
export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1

# .env 파일 로드
if [ -f ".env" ]; then
  set -a
  source .env
  set +a
  echo "✅ .env 로드 완료"
else
  echo "⚠️  .env 파일이 없습니다."
  echo "   cp .env.example .env 후 API 키를 입력하세요."
  echo ""
fi

# 사용 가능한 모델 표시
echo "── AI 모델 상태 ──────────────────"
[ -n "$ANTHROPIC_API_KEY" ] && echo "  ✅ Claude    (ANTHROPIC_API_KEY 설정됨)" || echo "  ⬜ Claude    (미설정)"
[ -n "$OPENAI_API_KEY"    ] && echo "  ✅ GPT       (OPENAI_API_KEY 설정됨)"    || echo "  ⬜ GPT       (미설정)"
[ -n "$GOOGLE_API_KEY"    ] && echo "  ✅ Gemini    (GOOGLE_API_KEY 설정됨)"    || echo "  ⬜ Gemini    (미설정)"
[ -n "$NOTION_API_KEY"    ] && echo "  ✅ Notion    (NOTION_API_KEY 설정됨)"    || echo "  ⬜ Notion    (미설정)"
echo "──────────────────────────────────"

PORT=${PORT:-8000}
echo ""
echo "🚀 서버 시작: http://localhost:$PORT"
echo ""

.venv/bin/python3 -m uvicorn backend.app:app --reload --port "$PORT"
