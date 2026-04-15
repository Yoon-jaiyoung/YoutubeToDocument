import json
import os
from datetime import datetime


# 모델별 1M 토큰당 USD 단가
_COST_TABLE = {
    "claude":  {"input": 3.00,  "output": 15.00},
    "gpt":     {"input": 2.50,  "output": 10.00},
    "gemini":  {"input": 1.25,  "output": 5.00},
    "local":   {"input": 0.00,  "output": 0.00},
}


def _cost(model_type: str, prompt: int, completion: int) -> float:
    rate = _COST_TABLE.get(model_type, {"input": 0.0, "output": 0.0})
    return (prompt * rate["input"] + completion * rate["output"]) / 1_000_000


class UsageTracker:
    def __init__(self, url: str = "", title: str = "", model: str = "", reviewer: str = ""):
        self.url = url
        self.title = title
        self.model = model
        self.reviewer = reviewer
        self.started_at = datetime.now().isoformat()
        self._steps: list[dict] = []

    def add_step(self, step_name: str, model_type: str, records: list[dict]) -> None:
        """단계별 usage 기록 추가. records = LLMClient.pop_usage() 결과"""
        if not records:
            return
        prompt = sum(r["prompt_tokens"] for r in records)
        completion = sum(r["completion_tokens"] for r in records)
        total = prompt + completion
        self._steps.append({
            "step": step_name,
            "model": model_type,
            "calls": len(records),
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": total,
            "estimated_cost_usd": _cost(model_type, prompt, completion),
        })

    # ── 집계 ────────────────────────────────────────────────────────
    @property
    def total_prompt(self) -> int:
        return sum(s["prompt_tokens"] for s in self._steps)

    @property
    def total_completion(self) -> int:
        return sum(s["completion_tokens"] for s in self._steps)

    @property
    def total_tokens(self) -> int:
        return self.total_prompt + self.total_completion

    @property
    def total_cost(self) -> float:
        return sum(s["estimated_cost_usd"] for s in self._steps)

    # ── 출력 ────────────────────────────────────────────────────────
    def print_report(self) -> None:
        W = 62
        print(f"\n{'─'*W}")
        print(f"  AI 사용량 리포트")
        print(f"{'─'*W}")
        print(f"  {'단계':<22} {'모델':<8} {'입력':>7} {'출력':>7} {'합계':>8}")
        print(f"  {'─'*22} {'─'*8} {'─'*7} {'─'*7} {'─'*8}")

        for s in self._steps:
            calls = f"({s['calls']}회)" if s['calls'] > 1 else ""
            step_label = f"{s['step']}{calls}"
            print(
                f"  {step_label:<22} {s['model']:<8}"
                f" {s['prompt_tokens']:>7,} {s['completion_tokens']:>7,}"
                f" {s['total_tokens']:>8,}"
            )

        print(f"  {'─'*22} {'─'*8} {'─'*7} {'─'*7} {'─'*8}")
        print(
            f"  {'합계':<22} {'':<8}"
            f" {self.total_prompt:>7,} {self.total_completion:>7,}"
            f" {self.total_tokens:>8,}"
        )

        if self.total_cost > 0:
            print(f"\n  예상 비용: ${self.total_cost:.4f} USD")
        else:
            print(f"\n  예상 비용: $0.00 (로컬 모델 무료)")
        print(f"{'─'*W}")

    # ── 직렬화 ──────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "title": self.title,
            "model": self.model,
            "reviewer": self.reviewer,
            "started_at": self.started_at,
            "total_prompt_tokens": self.total_prompt,
            "total_completion_tokens": self.total_completion,
            "total_tokens": self.total_tokens,
            "estimated_cost_usd": round(self.total_cost, 6),
            "steps": self._steps,
        }

    def save(self, output_dir: str) -> str:
        path = os.path.join(output_dir, "usage_report.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        return path


# ── 전체 이력 통계 조회 ──────────────────────────────────────────────
def display_usage_stats() -> None:
    """history.json에 누적된 usage 통계 출력"""
    if not os.path.exists("history.json"):
        print("이력이 없습니다.")
        return

    with open("history.json", encoding="utf-8") as f:
        history = json.load(f)

    entries_with_usage = [h for h in history if h.get("usage")]
    if not entries_with_usage:
        print("AI 사용량 데이터가 없습니다. (--url 로 새로 실행하면 기록됩니다)")
        return

    total_tokens = sum(h["usage"]["total_tokens"] for h in entries_with_usage)
    total_cost = sum(h["usage"].get("estimated_cost_usd", 0) for h in entries_with_usage)

    model_stats: dict[str, dict] = {}
    for h in entries_with_usage:
        m = h["usage"].get("model", "unknown")
        if m not in model_stats:
            model_stats[m] = {"tokens": 0, "cost": 0.0, "count": 0}
        model_stats[m]["tokens"] += h["usage"]["total_tokens"]
        model_stats[m]["cost"] += h["usage"].get("estimated_cost_usd", 0)
        model_stats[m]["count"] += 1

    W = 50
    print(f"\n{'─'*W}")
    print(f"  전체 AI 사용량 통계")
    print(f"{'─'*W}")
    print(f"  총 처리 영상  : {len(entries_with_usage)}개")
    print(f"  총 토큰 사용  : {total_tokens:,}")
    print(f"  총 예상 비용  : ${total_cost:.4f} USD")
    print(f"\n  모델별 사용량:")
    for model, stat in model_stats.items():
        cost_str = f"${stat['cost']:.4f}" if stat["cost"] > 0 else "무료"
        print(f"    {model:<20} {stat['tokens']:>8,} 토큰  {cost_str}")
    print(f"{'─'*W}")
