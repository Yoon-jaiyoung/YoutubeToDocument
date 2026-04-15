#!/usr/bin/env python3
import argparse
import os
import sys
import tempfile

# 프로젝트 루트를 경로에 추가
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


def step(n, total, msg):
    print(f"\n[{n}/{total}] {msg}")


def run(url: str, model: str, reviewer_model: str, local_model: str, notion: bool = False):
    TOTAL = 6 if notion else 5
    temp_dir = tempfile.mkdtemp()

    # ── 1. 자막/오디오 추출 ──────────────────────────────────────────
    step(1, TOTAL, "자막 추출 중...")
    existing = find_entry(url)
    if existing:
        print(f"  ⚠️  이전 분석 이력 발견: {existing['title']} ({existing['created_at'][:10]})")
        answer = input("  새로 분석하시겠습니까? [y/N]: ").strip().lower()
        if answer != 'y':
            print(f"  기존 결과물 경로: {existing['output_dir']}")
            return

    result = get_transcript(url, temp_dir=temp_dir)
    title = result["title"]

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
    print(f"  기술명 파악: {intent.get('tech_name', '?')}")

    output_dir = get_output_dir(title)
    draft_path = os.path.join(output_dir, "draft.md")

    draft = generate_draft(text, intent, url, gen_client)
    save_markdown(draft, draft_path)
    print(f"  ✅ 완료 → {draft_path}")

    # ── 3. AI 검증 ───────────────────────────────────────────────────
    step(3, TOTAL, f"AI 검증 중... (모델: {reviewer_model})")
    rev_client = LLMClient(reviewer_model, local_model=local_model)
    review = review_draft(draft, text, rev_client)

    review_path = os.path.join(output_dir, "review.md")
    save_markdown(review, review_path)
    print(f"  ✅ 완료 → {review_path}")

    # ── 4. 최종 매뉴얼 생성 ──────────────────────────────────────────
    step(4, TOTAL, "최종 매뉴얼 생성 중...")
    final = refine_draft(draft, review, gen_client)

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

    # ── 6. 이력 저장 ─────────────────────────────────────────────────
    step(TOTAL, TOTAL, "이력 저장 중...")
    entry = new_entry(url, title, model, reviewer_model, output_dir)
    entry["versions"].append(final_path)
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
    if notion_url:
        print(f"   Notion  : {notion_url}")

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

        version += 1
        versioned_path = os.path.join(output_dir, f"final_v{version}.md")
        save_markdown(updated, versioned_path)
        # final.md도 최신으로 덮어쓰기
        save_markdown(updated, final_path)

        # 이력에 피드백 추가
        history = __import__('src.history', fromlist=['load_history'])
        from src.history import load_history
        all_history = load_history()
        for h in reversed(all_history):
            if h.get("url") == url:
                add_feedback(h, feedback, versioned_path)
                break
        import json
        with open("history.json", "w", encoding="utf-8") as f:
            json.dump(all_history, f, ensure_ascii=False, indent=2)

        print(f"✅ 수정 완료 → {versioned_path}")
        print(f"   (final.md도 최신 버전으로 업데이트됨)")


def _notion_only(md_path: str):
    """기존 MD 파일을 Notion에만 업로드"""
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

Notion 환경변수:
  export NOTION_API_KEY="secret_..."
  export NOTION_PAGE_ID="페이지ID"
        """
    )
    parser.add_argument("--url", help="YouTube 영상 URL")
    parser.add_argument(
        "--model",
        default="local",
        choices=["local", "claude", "gpt", "gemini"],
        help="매뉴얼 생성 AI 모델 (기본값: local)"
    )
    parser.add_argument(
        "--reviewer",
        default=None,
        choices=["local", "claude", "gpt", "gemini"],
        help="검증 AI 모델 (기본값: --model과 동일)"
    )
    parser.add_argument(
        "--local-model",
        default="mlx-community/gemma-4-e4b-it-4bit",
        help="로컬 LLM 모델명 (기본값: mlx-community/gemma-4-e4b-it-4bit)"
    )
    parser.add_argument("--history", action="store_true", help="분석 이력 조회")
    parser.add_argument(
        "--notion",
        action="store_true",
        help="최종 매뉴얼을 Notion에 업로드 (NOTION_API_KEY, NOTION_PAGE_ID 환경변수 필요)"
    )
    parser.add_argument(
        "--notion-only",
        metavar="FINAL_MD",
        help="기존 final.md 파일을 Notion에만 업로드 (재처리 없이)"
    )

    args = parser.parse_args()

    if args.history:
        display_history()
        return

    # Notion 단독 업로드 모드
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
