from .llm_client import LLMClient


REVIEW_SYSTEM = """당신은 기술 문서 검토 전문가입니다.
주어진 기술 매뉴얼 초안을 검토하고, 개선이 필요한 부분을 구체적으로 지적하세요.

반드시 아래 형식으로 출력하세요:

## 검토 결과 요약
(전반적인 품질 평가 1-2문장)

## 수정 필요 사항

### [수정 필요] {섹션명}
- 문제: {구체적인 문제 설명}
- 이유: {왜 수정이 필요한지}
- 제안: {어떻게 수정하면 좋은지}

(수정 필요 사항이 여러 개면 위 형식을 반복)

## 보완이 필요한 내용
(영상 원문에는 있지만 매뉴얼에 빠진 중요 정보)

## 잘된 점
(잘 작성된 부분)
"""

REVIEW_USER = """아래 기술 매뉴얼 초안을 검토하세요.

## 매뉴얼 초안:
{draft}

## 원본 영상 텍스트 (참고용):
{original_text}
"""


def review_draft(draft: str, original_text: str, client: LLMClient) -> str:
    """초안 검증 및 수정 가이드 생성"""
    # 원본 텍스트가 너무 길면 앞부분만 참고
    ref_text = original_text[:3000] if len(original_text) > 3000 else original_text

    return client.generate(
        system=REVIEW_SYSTEM,
        user=REVIEW_USER.format(draft=draft, original_text=ref_text),
        max_tokens=3000,
    )
