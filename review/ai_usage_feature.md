# AI 사용량 리포트 기능 설계

## 목적
각 실행에서 AI 모델 호출 시 소비된 토큰 수를 추적하고,
실행 완료 후 요약 리포트를 출력 및 저장한다.

---

## 수집 항목

| 항목 | 설명 |
|---|---|
| `step` | 파이프라인 단계명 (의도 파악, 초안 생성, AI 검증, 최종 생성) |
| `model` | 사용한 모델명 |
| `prompt_tokens` | 입력 토큰 수 |
| `completion_tokens` | 출력 토큰 수 |
| `total_tokens` | 합계 |
| `called_at` | 호출 일시 |

---

## 모델별 예상 비용 기준 (참고)

| 모델 | 입력 (1M 토큰) | 출력 (1M 토큰) |
|---|---|---|
| claude-sonnet-4-6 | $3.00 | $15.00 |
| gpt-4o | $2.50 | $10.00 |
| gemini-1.5-pro | $1.25 | $5.00 |
| local | $0.00 | $0.00 |

---

## 출력 파일

- `output/{제목}/usage_report.json`

```json
{
  "url": "https://youtube.com/watch?v=...",
  "title": "영상 제목",
  "model": "local",
  "reviewer": "local",
  "total_tokens": 18807,
  "estimated_cost_usd": 0.0,
  "steps": [
    {
      "step": "의도 파악",
      "model": "local",
      "prompt_tokens": 567,
      "completion_tokens": 312,
      "total_tokens": 879,
      "called_at": "2026-04-15T10:23:11"
    }
  ]
}
```

---

## 구현 위치

- `src/llm_client.py` — `generate()` 반환값에 usage 포함
- `src/usage_tracker.py` — 신규 모듈, 사용량 누적 및 리포트 생성
- `main.py` — 실행 완료 후 리포트 출력 및 저장

---

## CLI 추가 인자

```bash
# 이력 전체 사용량 통계 조회
python main.py --usage
```

출력 예시:
```
── 전체 AI 사용량 통계 ──────────────
총 처리 영상: 3개
총 토큰 사용: 52,341
예상 누적 비용: $0.00 (local 모델)

모델별 사용량:
  local : 52,341 토큰
```
