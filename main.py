#!/usr/bin/env python3
import argparse
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.extractor import get_transcript
from src.transcriber import transcribe
from src.preprocessor import clean_transcript
from src.llm_client import LLMClient
from src.generator import identify_intent, generate_draft
from src.reviewer import review_draft
from src.refiner import refine_draft, apply_feedback
from src.writer import get_output_dir, save_markdown
from src.history import new_entry, save_entry, add_feedback, display_history, find_entry
from src.usage_tracker import UsageTracker, display_usage_stats


def step(n, total, msg):
    print(f"\n[{n}/{total}] {msg}")


def run(url: str, model: str, reviewer_model: str, local_model: str, notion: bool = False):
    TOTAL = 6 if notion else 5
    temp_dir = tempfile.mkdtemp()
    tracker = UsageTracker(url=url, model=model, reviewer=reviewer_model)

    # ── 1. 자막/오디오 추출 ──────────────────────────────────────────
    step(1, TOTAL, "자막 추출 중...")
    existing = find_entry(url)
    if existing:
        print(f"  ⚠️  이전 분석 이력 발견: {existing['title']} ({existing['created_at'][:10]})")
        try:
            answer = input("  새로 분석하시겠습니까? [y/N]: ").strip().lower()
        except EOFError:
            answer = "n"
        if answer != "y":
            print(f"  기존 결과물 경로: {existing['output_dir']}")
            return

    result = get_transcript(url, temp_dir=temp_dir)
    title = result["title"]
    tracker.title = title

    if result["method"] == "stt":
        step(1, TOTAL, "STT 변환 중...")
        text, lang = transcribe(result["audio_path"])
    else:
        text = result["text"]
        lang = result["lang"]

    text = clean_transcript(text, lang=lang or "ko")
    print(f"  ✅ 완료 — 언어: {lang}, 텍스트 길이: {len(text)}자")

    # ── 2. 초안 생성 ─────────────────────────────────────────────────
    step(2, TOTAL, f"초안 매뉴얼 생성 중... (모델: {model})")
    gen_client = LLMClient(model, local_model=local_model)

    intent = identify_intent(text, gen_client)
    tracker.add_step("의도 파악", gen_client.display_name, gen_client.pop_usage())
    print(f"  기술명 파악: {intent.get('tech_name', '?')}")

    output_dir = get_output_dir(title)
    draft_path = os.path.join(output_dir, "draft.md")

    draft = generate_draft(text, intent, url, gen_client)
    tracker.add_step("초안 생성", gen_client.display_name, gen_client.pop_usage())
    save_markdown(draft, draft_path)
    print(f"  ✅ 완료 → {draft_path}")

    # ── 3. AI 검증 ───────────────────────────────────────────────────
    step(3, TOTAL, f"AI 검증 중... (모델: {reviewer_model})")
    rev_client = LLMClient(reviewer_model, local_model=local_model)
    review = review_draft(draft, text, rev_client)
    tracker.add_step("AI 검증", rev_client.display_name, rev_client.pop_usage())

    review_path = os.path.join(output_dir, "review.md")
    save_markdown(review, review_path)
    print(f"  ✅ 완료 → {review_path}")

    # ── 4. 최종 매뉴얼 생성 ──────────────────────────────────────────
    step(4, TOTAL, "최종 매뉴얼 생성 중...")
    final = refine_draft(draft, review, gen_client)
    tracker.add_step("최종 생성", gen_client.display_name, gen_client.pop_usage())

    final_path = os.path.join(output_dir, "final.md")
    save_markdown(final, final_path)
    print(f"  ✅ 완료 → {final_path}")

    # ── 5. Notion 업로드 (선택) ──────────────────────────────────────
    notion_url = None
    if notion:
        step(5, TOTAL, "Notion 업로드 중...")
        api_key = os.environ.get("NOTION_API_KEY")
        page_id = os.environ.get("NOTION_PAGE_ID")
        if not api_key or not page_id:
            print("  ⚠️  NOTION_API_KEY 또는 NOTION_PAGE_ID 환경변수가 없습니다. 건너뜁니다.")
        else:
            from src.notion_uploader import upload_to_notion
            final_content = open(final_path, encoding="utf-8").read()
            notion_url = upload_to_notion(
                md_text=final_content,
                title=title,
                youtube_url=url,
                parent_page_id=page_id,
                api_key=api_key,
            )
            print(f"  ✅ 완료 → {notion_url}")

    # ── 사용량 저장 ──────────────────────────────────────────────────
    usage_path = tracker.save(output_dir)

    # ── 이력 저장 ────────────────────────────────────────────────────
    step(TOTAL, TOTAL, "이력 저장 중...")
    entry = new_entry(url, title, model, reviewer_model, output_dir)
    entry["versions"].append(final_path)
    entry["usage"] = {
        "total_tokens": tracker.total_tokens,
        "estimated_cost_usd": round(tracker.total_cost, 6),
        "model": model,
    }
    if notion_url:
        entry["notion_url"] = notion_url
    save_entry(entry)
    print(f"  ✅ 완료 → history.json")

    # ── 결과 출력 ────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"✅ 완료!")
    print(f"   제목    : {title}")
    print(f"   기술명  : {intent.get('tech_name', '?')}")
    print(f"   출력폴더: {output_dir}")
    print(f"{'='*60}")
    print(f"\n📄 결과물:")
    print(f"   초안    : {draft_path}")
    print(f"   검토    : {review_path}")
    print(f"   최종    : {final_path}")
    print(f"   사용량  : {usage_path}")
    if notion_url:
        print(f"   Notion  : {notion_url}")

    # ── AI 사용량 리포트 ─────────────────────────────────────────────
    tracker.print_report()

    # ── 사용자 피드백 루프 ────────────────────────────────────────────
    version = 1
    while True:
        print(f"\n{'─'*60}")
        try:
            feedback = input("추가 요구사항이 있으면 입력하세요 (없으면 Enter로 종료): ").strip()
        except EOFError:
            break
        if not feedback:
            print("완료. 최종 파일을 확인하세요.")
            break

        print(f"\n수정 중... (v{version + 1})")
        current_content = open(final_path, encoding="utf-8").read()
        updated = apply_feedback(current_content, feedback, gen_client)
        tracker.add_step(f"피드백 반영 v{version+1}", gen_client.display_name, gen_client.pop_usage())

        version += 1
        versioned_path = os.path.join(output_dir, f"final_v{version}.md")
        save_markdown(updated, versioned_path)
        save_markdown(updated, final_path)

        # 이력 업데이트
        all_history = _load_history()
        for h in reversed(all_history):
            if h.get("url") == url:
                add_feedback(h, feedback, versioned_path)
                h["usage"]["total_tokens"] = tracker.total_tokens
                h["usage"]["estimated_cost_usd"] = round(tracker.total_cost, 6)
                break
        _save_history(all_history)

        # 사용량 파일 갱신
        tracker.save(output_dir)
        tracker.print_report()
        print(f"✅ 수정 완료 → {versioned_path}")


def _load_history() -> list:
    if not os.path.exists("history.json"):
        return []
    with open("history.json", encoding="utf-8") as f:
        return json.load(f)


def _save_history(data: list) -> None:
    with open("history.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _notion_only(md_path: str):
    api_key = os.environ.get("NOTION_API_KEY")
    page_id = os.environ.get("NOTION_PAGE_ID")
    if not api_key or not page_id:
        print("❌ NOTION_API_KEY, NOTION_PAGE_ID 환경변수를 설정하세요.")
        sys.exit(1)
    if not os.path.exists(md_path):
        print(f"❌ 파일을 찾을 수 없습니다: {md_path}")
        sys.exit(1)

    from src.notion_uploader import upload_to_notion
    content = open(md_path, encoding="utf-8").read()
    title = os.path.basename(os.path.dirname(md_path))
    print(f"Notion 업로드 중: {md_path}")
    url = upload_to_notion(
        md_text=content,
        title=title,
        youtube_url="",
        parent_page_id=page_id,
        api_key=api_key,
    )
    print(f"✅ 완료 → {url}")


def main():
    parser = argparse.ArgumentParser(
        description="YouTube 기술 영상 → 기술 매뉴얼 Markdown 생성기",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python main.py --url "https://youtube.com/watch?v=..."
  python main.py --url "https://youtube.com/watch?v=..." --model local
  python main.py --url "https://youtube.com/watch?v=..." --model claude --reviewer local
  python main.py --url "https://youtube.com/watch?v=..." --notion
  python main.py --notion-only output/제목/final.md
  python main.py --history
  python main.py --usage

Notion 환경변수:
  export NOTION_API_KEY="secret_..."
  export NOTION_PAGE_ID="페이지ID"
        """
    )
    parser.add_argument("--url", help="YouTube 영상 URL")
    parser.add_argument(
        "--model", default="local",
        choices=["local", "claude", "gpt", "gemini"],
        help="매뉴얼 생성 AI 모델 (기본값: local)"
    )
    parser.add_argument(
        "--reviewer", default=None,
        choices=["local", "claude", "gpt", "gemini"],
        help="검증 AI 모델 (기본값: --model과 동일)"
    )
    parser.add_argument(
        "--local-model",
        default="mlx-community/gemma-4-e4b-it-4bit",
        help="로컬 LLM 모델명"
    )
    parser.add_argument("--history", action="store_true", help="분석 이력 조회")
    parser.add_argument("--usage", action="store_true", help="전체 AI 사용량 통계 조회")
    parser.add_argument(
        "--notion", action="store_true",
        help="최종 매뉴얼을 Notion에 업로드 (NOTION_API_KEY, NOTION_PAGE_ID 필요)"
    )
    parser.add_argument(
        "--notion-only", metavar="FINAL_MD",
        help="기존 final.md 파일을 Notion에만 업로드"
    )

    args = parser.parse_args()

    if args.history:
        display_history()
        return

    if args.usage:
        display_usage_stats()
        return

    if args.notion_only:
        _notion_only(args.notion_only)
        return

    if not args.url:
        parser.print_help()
        sys.exit(1)

    reviewer = args.reviewer or args.model

    try:
        run(
            url=args.url,
            model=args.model,
            reviewer_model=reviewer,
            local_model=args.local_model,
            notion=args.notion,
        )
    except KeyboardInterrupt:
        print("\n\n중단되었습니다.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        raise


if __name__ == "__main__":
    main()
