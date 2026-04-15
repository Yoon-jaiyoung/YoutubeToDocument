# YoutubeToDocument - 개발 계획

## 상태: 계획 중

---

## 전체 워크플로우
```
YouTube URL 입력
    ↓
[Phase 1] 자막/오디오 추출 → STT
    ↓
[Phase 2] AI(생성 모델) → 초안 매뉴얼 MD 생성
    ↓
[Phase 3] AI(검증 모델) → 초안 검토 → 수정 가이드 생성
    ↓
[Phase 4] AI(생성 모델) → 수정 가이드 반영 → 최종 MD 저장
    ↓
사용자 확인 → 추가 요구사항 입력
    ↓
[반복] 요구사항 반영 → 재수정 → 최종 MD 업데이트
    ↓
이력 기록 (history.json)
```

---

## Phase 1 - 기반 구축
- [ ] 프로젝트 환경 설정 (가상환경, requirements.txt)
- [ ] YouTube 자막 추출 구현 (`youtube-transcript-api`)
- [ ] 자막 없는 경우 오디오 다운로드 → STT 처리 (`yt-dlp` + `faster-whisper`)
- [ ] 한국어 자막/음성 자동 감지 및 처리 지원
- [ ] **[검증 반영]** STT 전처리 모듈 (`preprocessor.py`) 추가
  - 노이즈 제거, 문맥 흐름 정리, 불필요한 발화 필터링

## Phase 2 - AI 매뉴얼 생성 (초안)
- [ ] AI 모델 선택 연동 (claude / gpt / gemini / local)
- [ ] **[검증 반영]** 의도 식별 단계 추가: 영상 핵심 목표/주제 먼저 추출 후 LLM에 메타데이터 함께 전달
- [ ] 추출된 텍스트 → 기술 매뉴얼 구조화 프롬프트 작성 (기술 흐름 분석 포함)
- [ ] 출력 구조 정의:
  - 기술 개요
  - 왜 이 기술을 써야 하는가
  - 사용법 (설치, 기본 사용, 주요 API)
  - 예시 코드
  - 참고 자료
- [ ] 초안 저장: `output/{제목}/draft.md`

## Phase 3 - AI 검증 및 수정 가이드
- [ ] 검증용 AI 모델 연동 (생성 모델과 별도 지정 가능, `--reviewer` 인자)
- [ ] 검증 프롬프트 작성:
  - 누락된 내용 확인
  - 잘못된 정보 확인
  - 구조 완성도 평가
  - 예시 코드 적절성 확인
  - **[검증 반영]** 피드백 형식 강제: "이 부분 수정 필요 (이유: X)" 구체적 형식으로 출력
- [ ] 수정 가이드 저장: `output/{제목}/review.md`
- [ ] 수정 가이드 기반으로 최종 MD 자동 재생성
- [ ] 최종 저장: `output/{제목}/final.md`

## Phase 4 - 사용자 피드백 반영
- [ ] 최종 MD 생성 후 사용자에게 확인 요청 출력
- [ ] 추가 요구사항 입력 받기 (`--feedback` 인자 또는 인터랙티브 입력)
- [ ] 요구사항 반영 → final.md 재수정
- [ ] 수정 이력 기록

## Phase 5 - 이력 관리
- [ ] URL 분석 이력 저장: `history.json`
  - URL, 영상 제목, 처리 일시, 사용 모델, 출력 파일 경로
  - 사용자 피드백 내용
  - 버전별 수정 이력
- [ ] 이력 조회 CLI: `python main.py --history`
- [ ] 동일 URL 재실행 시 이력 표시 및 덮어쓰기 여부 확인

## Phase 6 - AI 사용량 리포트
- [ ] 각 LLM 호출 시 토큰 사용량 수집 (prompt_tokens, completion_tokens, total_tokens)
- [ ] 실행 완료 후 사용량 요약 출력
  ```
  ── AI 사용량 리포트 ──────────────────
  단계              모델       입력    출력   합계
  의도 파악         local       567    312    879
  초안 생성 (1/3)   local      1243   1890   3133
  초안 생성 (2/3)   local      1102   1754   2856
  초안 생성 (3/3)   local       998   1621   2619
  AI 검증           local      2341    987   3328
  최종 생성         local      3102   2890   5992
  ──────────────────────────────────────
  합계                         9353   9454  18807
  예상 비용 (claude-sonnet): $0.056
  ```
- [ ] 사용량 `usage_report.json`으로 저장 (output/{제목}/ 하위)
- [ ] 이력에 누적 사용량 기록 → `python main.py --history`에서 통계 표시
- [ ] `--usage` 플래그로 이력 전체 사용량 통계 조회

## Phase 7 - 개선
- [ ] 긴 영상 처리 (텍스트 청크 분할)
- [ ] 오류 처리 및 재시도 로직

---

## CLI 인터페이스
```bash
# 기본 실행
python main.py --url "https://youtube.com/watch?v=..."

# 모델 선택
python main.py --url "..." --model claude
python main.py --url "..." --model gpt
python main.py --url "..." --model gemini
python main.py --url "..." --model local

# 생성/검증 모델 각각 지정
python main.py --url "..." --model local --reviewer claude

# 이력 조회
python main.py --history

# 실행 결과 출력 예시
# [1/5] 자막 추출 중...       ✅ 완료 (ko, 1,243줄)
# [2/5] 초안 매뉴얼 생성 중... ✅ 완료 → output/제목/draft.md
# [3/5] AI 검증 중...         ✅ 완료 → output/제목/review.md
# [4/5] 최종 매뉴얼 생성 중... ✅ 완료 → output/제목/final.md
# [5/5] 이력 저장...          ✅ 완료 → history.json
#
# 👉 결과물 확인: output/제목/final.md
# 추가 요구사항이 있으면 입력하세요 (없으면 Enter):
```

---

## 기술 결정 사항
| 항목 | 결정 | 비고 |
|---|---|---|
| 언어 | Python | - |
| 자막 추출 | youtube-transcript-api | - |
| STT | faster-whisper | 확정 (한국어 포함 다국어 지원) |
| AI 모델 | Claude / GPT / Gemini / Local LLM | CLI `--model` 인자로 선택 |
| 검증 모델 | 생성 모델과 별도 지정 가능 | CLI `--reviewer` 인자 |
| 실행 방식 | CLI | 확정 |
| 출력 형식 | Markdown (.md) | 초안/검토/최종 분리 저장 |
| 이력 관리 | history.json | URL별 처리 이력 누적 |

---

## 디렉토리 구조 (예정)
```
YoutubeToDocument/
├── main.py
├── requirements.txt
├── history.json              # URL 분석 이력
├── research.md
├── plan.md
├── src/
│   ├── extractor.py          # 자막/오디오 추출
│   ├── preprocessor.py       # STT 전처리 (노이즈 제거, 흐름 정리) ← 검증 반영 추가
│   ├── transcriber.py        # STT 처리
│   ├── generator.py          # AI 매뉴얼 생성 (의도 식별 + 초안)
│   ├── reviewer.py           # AI 검증 및 수정 가이드
│   ├── refiner.py            # 수정 가이드 반영 최종본 생성
│   ├── history.py            # 이력 관리
│   └── writer.py             # MD 파일 저장
└── output/
    └── {영상제목}/
        ├── draft.md          # AI 생성 초안
        ├── review.md         # 검증 AI 수정 가이드
        └── final.md          # 최종 매뉴얼
```
