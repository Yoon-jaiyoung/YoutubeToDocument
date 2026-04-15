# YoutubeToDocument - 기술 조사

## 프로그램 목적
YouTube 기술 영상 URL을 입력하면, 해당 영상의 내용을 분석하여
구조화된 기술 매뉴얼 Markdown 파일로 출력한다.

## 출력 문서 구조 (목표)
```
# 기술명

## 개요
- 이 기술이 무엇인지

## 왜 이 기술을 사용해야 하는가?
- 장점, 문제 해결, 기존 대비 차이점

## 사용법
- 설치 방법
- 기본 사용법
- 주요 명령어 / API

## 예시 코드
- 실제 사용 예시

## 참고 자료
- 원본 YouTube URL
```

---

## 기술 스택 조사

### 언어
- **Python** — 라이브러리 생태계 풍부, 추천

### YouTube 자막 추출
| 라이브러리 | 방식 | 특징 |
|---|---|---|
| `youtube-transcript-api` | 자막 직접 추출 | 빠름, 오디오 다운로드 불필요 |
| `yt-dlp` | 오디오/영상 다운로드 | 자막 없는 영상도 처리 가능 |

### 음성 → 텍스트 (자막 없는 경우)
| 라이브러리 | 방식 | 특징 |
|---|---|---|
| `faster-whisper` | 로컬 STT | 빠름, 무료, 다국어 |
| OpenAI Whisper API | 클라우드 STT | 편리, API 비용 발생 |

### AI 텍스트 분석 및 매뉴얼 생성 (선택 가능)
| 라이브러리 | 모델 | 특징 |
|---|---|---|
| `anthropic` | Claude (claude-sonnet 등) | 긴 문서 처리, 구조화 품질 높음 |
| `openai` | GPT-4o 등 | 요약, 구조화 |
| `google-generativeai` | Gemini 1.5 Pro 등 | 긴 컨텍스트, 무료 티어 제공 |
| `openai` (base_url 변경) | 로컬 LLM | `http://localhost:8080/v1` — OpenAI 호환 API, 무료, 인터넷 불필요 |

### 로컬 LLM 연동 방식
```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8080/v1",
    api_key="none"  # 로컬 서버는 키 불필요
)
# 사용 가능한 모델 확인: GET http://localhost:8080/v1/models
```

### 문서 출력
- Markdown (.md) 파일 직접 저장

---

## Notion 연동 조사

### 방식 비교

| 방식 | 라이브러리 | 장점 | 단점 |
|---|---|---|---|
| **① Notion API 직접 연동** | `notion-client` (공식 Python SDK) | 공식 지원, 안정적, 페이지 자동 생성 | MD → Notion 블록 변환 직접 구현 필요 |
| **② MD 변환 후 업로드** | `md2notion` + `notion-client` | MD 구조 자동 파싱 | 오래된 라이브러리, 일부 문법 미지원 |
| **③ 커스텀 변환기** | `mistune` + `notion-client` | 완전한 제어, 코드블록/테이블 완벽 지원 | 구현 공수 있음 (추천) |

### 추천: ③ 커스텀 변환기 (`mistune` + `notion-client`)

**이유:**
- `md2notion`은 2021년 이후 업데이트 없음 → Notion API v2 미지원
- `mistune`으로 MD를 AST로 파싱 후 Notion 블록으로 직접 변환 → 완전한 제어
- 코드 블록 언어 감지, 테이블, 이모지 헤더 등 완벽 지원

### Notion 블록 매핑 설계

| Markdown 요소 | Notion 블록 타입 |
|---|---|
| `# 제목` | `heading_1` |
| `## 소제목` | `heading_2` |
| `### 소소제목` | `heading_3` |
| `- 항목` | `bulleted_list_item` |
| `1. 항목` | `numbered_list_item` |
| ` ```python ` | `code` (language: python) |
| `> 인용` | `quote` |
| `\| 표 \|` | `table` |
| `---` | `divider` |
| 일반 문단 | `paragraph` |
| `**굵게**` | `bold` annotation |
| `` `인라인 코드` `` | `code` annotation |

### 연동 흐름
```
final.md
    ↓
mistune으로 MD 파싱 (AST)
    ↓
Notion 블록 리스트로 변환
    ↓
notion-client로 페이지 생성 / 업데이트
    ↓
Notion 데이터베이스 또는 페이지에 추가
```

### 필요한 Notion 설정
1. Notion Integration 생성 → API 키 발급
2. 대상 페이지/데이터베이스에 Integration 권한 부여
3. `NOTION_API_KEY`, `NOTION_PAGE_ID` 환경변수 설정

### 설치
```
notion-client>=2.2.1
mistune>=3.0.0
```

### Notion 포맷 최적화 포인트
- 페이지 상단에 **callout 블록**으로 영상 URL + 생성일 표시
- 코드 블록에 언어 자동 감지 적용
- 섹션 구분에 `divider` 블록 활용
- 긴 텍스트는 `toggle` 블록으로 접기 (예: 예시 코드)

---

## 처리 흐름
```
YouTube URL 입력
    ↓
자막 추출 (youtube-transcript-api)
    ↓ 자막 없는 경우
오디오 다운로드 (yt-dlp) → STT (faster-whisper)
    ↓
전체 텍스트 → AI 분석 (Claude API)
    ↓
구조화된 기술 매뉴얼 Markdown 생성
    ↓
output/{영상제목}.md 저장
```

---

## 미결 사항 (결정 필요)
- [x] 실행 방식: CLI 확정 (추후 Web UI 확장 가능)
- [x] AI 모델: CLI `--model` 인자로 선택 (claude / gpt / gemini / ollama)
- [x] 자막 없는 영상 STT 지원 → `yt-dlp` + `faster-whisper` 사용
- [x] 한국어 영상 지원 → `faster-whisper` 다국어 자동 감지, 한국어 프롬프트 처리
- [ ] 출력 파일 저장 경로 규칙
