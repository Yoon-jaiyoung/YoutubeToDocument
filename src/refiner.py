from .llm_client import LLMClient


REFINE_SYSTEM = """당신은 기술 문서 작성 전문가입니다.
주어진 매뉴얼 초안과 검토 의견을 바탕으로 완성도 높은 최종 기술 매뉴얼을 작성하세요.

규칙:
- 검토 의견의 수정 사항을 모두 반영하세요
- 초안의 좋은 부분은 유지하세요
- Markdown 형식을 정확히 지키세요
- 코드 예시는 실제 동작 가능하도록 작성하세요
- 최종 출력은 완성된 Markdown 문서만 포함하세요 (설명 텍스트 없이)
"""

REFINE_USER = """아래 초안과 검토 의견을 바탕으로 최종 매뉴얼을 작성하세요.

## 매뉴얼 초안:
{draft}

## 검토 의견:
{review}
"""

FEEDBACK_SYSTEM = """당신은 기술 문서 작성 전문가입니다.
주어진 기술 매뉴얼과 사용자 요구사항을 바탕으로 매뉴얼을 수정하세요.

규칙:
- 사용자 요구사항을 정확히 반영하세요
- 기존 내용 중 요구사항과 무관한 부분은 그대로 유지하세요
- 최종 출력은 완성된 Markdown 문서만 포함하세요
"""

FEEDBACK_USER = """아래 매뉴얼을 사용자 요구사항에 맞게 수정하세요.

## 현재 매뉴얼:
{current}

## 사용자 요구사항:
{feedback}
"""


def refine_draft(draft: str, review: str, client: LLMClient) -> str:
    """검토 의견 반영하여 최종 매뉴얼 생성"""
    return client.generate(
        system=REFINE_SYSTEM,
        user=REFINE_USER.format(draft=draft, review=review),
        max_tokens=4000,
    )


def apply_feedback(current: str, feedback: str, client: LLMClient) -> str:
    """사용자 피드백 반영하여 매뉴얼 재수정"""
    return client.generate(
        system=FEEDBACK_SYSTEM,
        user=FEEDBACK_USER.format(current=current, feedback=feedback),
        max_tokens=4000,
    )
