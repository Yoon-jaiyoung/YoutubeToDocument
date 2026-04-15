from .llm_client import LLMClient
from .preprocessor import chunk_text


INTENT_SYSTEM = """당신은 기술 영상 분석 전문가입니다.
주어진 영상 전사 텍스트를 분석하여 핵심 정보를 JSON 형식으로 추출하세요.
반드시 아래 JSON 형식만 출력하세요. 다른 텍스트는 포함하지 마세요.

{
  "tech_name": "기술/도구/라이브러리 이름",
  "purpose": "이 기술의 핵심 목적 한 줄 요약",
  "main_topics": ["주제1", "주제2", "주제3"],
  "key_features": ["핵심 기능1", "핵심 기능2"],
  "target_audience": "대상 독자 (예: Python 초보자, 백엔드 개발자)"
}"""

INTENT_USER = """다음 YouTube 영상 전사 텍스트를 분석하세요:

{text}"""


DRAFT_SYSTEM = """당신은 기술 문서 작성 전문가입니다.
주어진 영상 전사 텍스트와 메타데이터를 기반으로 구조화된 기술 매뉴얼을 Markdown으로 작성하세요.

반드시 아래 구조를 따르세요:

# {tech_name}

## 개요
(이 기술이 무엇인지 명확하고 간결하게)

## 왜 이 기술을 사용해야 하는가?
(장점, 문제 해결, 기존 방법 대비 차이점)

## 설치 방법
(설치 명령어, 환경 설정)

## 기본 사용법
(핵심 사용 방법, 주요 명령어/API)

## 예시 코드
(실제 동작하는 코드 예시, 코드 블록 사용)

## 주요 개념 및 팁
(알아두면 유용한 개념, 자주 하는 실수, 팁)

## 참고 자료
- 원본 영상: {url}
"""

DRAFT_USER = """아래 정보를 바탕으로 기술 매뉴얼을 작성하세요.

## 영상 메타데이터
- 기술명: {tech_name}
- 목적: {purpose}
- 주요 주제: {main_topics}
- 핵심 기능: {key_features}
- 대상 독자: {target_audience}

## 영상 전사 텍스트
{text}
"""


def identify_intent(text: str, client: LLMClient) -> dict:
    """영상의 핵심 의도/주제 파악"""
    import json

    # 텍스트가 길면 앞부분만 사용 (의도 파악에는 충분)
    sample = text[:4000] if len(text) > 4000 else text
    response = client.generate(
        system=INTENT_SYSTEM,
        user=INTENT_USER.format(text=sample),
        max_tokens=500,
    )

    # JSON 파싱
    try:
        # 코드 블록 제거
        clean = response.strip()
        if clean.startswith("```"):
            clean = "\n".join(clean.split("\n")[1:-1])
        return json.loads(clean)
    except Exception:
        # 파싱 실패 시 기본값
        return {
            "tech_name": "기술 매뉴얼",
            "purpose": "영상 내용 기반 기술 정리",
            "main_topics": [],
            "key_features": [],
            "target_audience": "개발자",
        }


def generate_draft(text: str, intent: dict, url: str, client: LLMClient) -> str:
    """초안 매뉴얼 생성"""
    chunks = chunk_text(text, max_chars=6000)

    if len(chunks) == 1:
        # 짧은 영상: 한 번에 처리
        return client.generate(
            system=DRAFT_SYSTEM.format(tech_name=intent.get("tech_name", "기술"), url=url),
            user=DRAFT_USER.format(
                tech_name=intent.get("tech_name", "기술"),
                purpose=intent.get("purpose", ""),
                main_topics=", ".join(intent.get("main_topics", [])),
                key_features=", ".join(intent.get("key_features", [])),
                target_audience=intent.get("target_audience", "개발자"),
                text=chunks[0],
            ),
            max_tokens=4000,
        )

    # 긴 영상: 청크별 처리 후 합치기
    print(f"  긴 영상 감지 — {len(chunks)}개 청크로 분할 처리")
    parts = []
    for i, chunk in enumerate(chunks):
        print(f"  청크 {i+1}/{len(chunks)} 처리 중...")
        part = client.generate(
            system="당신은 기술 문서 작성 전문가입니다. 주어진 영상 텍스트에서 기술적으로 중요한 내용만 추출하여 Markdown으로 정리하세요. 헤더, 코드 블록, 목록을 적극 활용하세요.",
            user=f"다음 영상 텍스트(파트 {i+1}/{len(chunks)})에서 중요한 기술 정보를 추출하세요:\n\n{chunk}",
            max_tokens=2000,
        )
        parts.append(part)

    # 합친 내용으로 최종 구조화
    combined = "\n\n---\n\n".join(parts)
    return client.generate(
        system=DRAFT_SYSTEM.format(tech_name=intent.get("tech_name", "기술"), url=url),
        user=f"""아래 분석된 내용들을 하나의 완성된 기술 매뉴얼로 통합하세요.

기술명: {intent.get('tech_name', '기술')}
목적: {intent.get('purpose', '')}

## 분석된 내용들:
{combined}
""",
        max_tokens=4000,
    )
