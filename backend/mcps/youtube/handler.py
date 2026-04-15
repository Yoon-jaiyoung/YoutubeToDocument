"""YouTube MCP 핸들러 — process_youtube, apply_feedback"""
import glob
import os
import tempfile


def run(tool_name: str, args: dict) -> dict:
    if tool_name == "process_youtube":
        return _process_youtube(args)
    elif tool_name == "apply_feedback":
        return _apply_feedback(args)
    raise ValueError(f"Unknown tool: {tool_name}")


def _process_youtube(args: dict) -> dict:
    from src.extractor import get_transcript
    from src.transcriber import transcribe
    from src.preprocessor import clean_transcript
    from src.llm_client import LLMClient
    from src.generator import identify_intent, generate_draft
    from src.reviewer import review_draft
    from src.refiner import refine_draft
    from src.writer import get_output_dir, save_markdown
    from src.history import new_entry, save_entry
    from src.usage_tracker import UsageTracker

    url            = args["url"]
    model          = args.get("model", "local")
    reviewer_model = args.get("reviewer") or model
    temp_dir       = tempfile.mkdtemp()

    print(f"[1/5] 자막 추출 중...")
    result = get_transcript(url, temp_dir=temp_dir)
    title  = result["title"]

    if result["method"] == "stt":
        print(f"[1/5] STT 변환 중...")
        text, lang = transcribe(result["audio_path"])
    else:
        text, lang = result["text"], result["lang"]

    text = clean_transcript(text, lang=lang or "ko")
    print(f"  ✅ 언어: {lang}, 텍스트: {len(text)}자")

    tracker    = UsageTracker(url=url, title=title, model=model, reviewer=reviewer_model)
    gen_client = LLMClient(model)
    rev_client = LLMClient(reviewer_model)

    print(f"[2/5] 초안 생성 중... (모델: {gen_client.display_name})")
    intent = identify_intent(text, gen_client)
    tracker.add_step("의도 파악", gen_client.display_name, gen_client.pop_usage())
    print(f"  기술명: {intent.get('tech_name','?')}")

    output_dir = get_output_dir(title)
    draft = generate_draft(text, intent, url, gen_client)
    tracker.add_step("초안 생성", gen_client.display_name, gen_client.pop_usage())
    save_markdown(draft, f"{output_dir}/draft.md")
    print(f"  ✅ 초안 저장 → {output_dir}/draft.md")

    print(f"[3/5] AI 검증 중... (모델: {rev_client.display_name})")
    review = review_draft(draft, text, rev_client)
    tracker.add_step("AI 검증", rev_client.display_name, rev_client.pop_usage())
    save_markdown(review, f"{output_dir}/review.md")
    print(f"  ✅ 검증 저장 → {output_dir}/review.md")

    print(f"[4/5] 최종 매뉴얼 생성 중...")
    final = refine_draft(draft, review, gen_client)
    tracker.add_step("최종 생성", gen_client.display_name, gen_client.pop_usage())
    save_markdown(final, f"{output_dir}/final.md")
    print(f"  ✅ 최종 저장 → {output_dir}/final.md")

    print(f"[5/5] 이력 저장 중...")
    tracker.save(output_dir)
    entry = new_entry(url, title, model, reviewer_model, output_dir)
    entry["versions"].append(f"{output_dir}/final.md")
    entry["usage"] = {
        "total_tokens": tracker.total_tokens,
        "model": model,
        "estimated_cost_usd": round(tracker.total_cost, 6),
    }
    save_entry(entry)
    print(f"  ✅ 완료!")

    with open(f"{output_dir}/final.md", encoding="utf-8") as f:
        final_content = f.read()

    return {
        "type": "manual",
        "title": title,
        "tech_name": intent.get("tech_name"),
        "output_dir": output_dir,
        "final_path": f"{output_dir}/final.md",
        "total_tokens": tracker.total_tokens,
        "estimated_cost": tracker.total_cost,
        "content": final_content,
        "usage_steps": tracker.to_dict()["steps"],
    }


def _apply_feedback(args: dict) -> dict:
    from src.llm_client import LLMClient
    from src.refiner import apply_feedback
    from src.writer import save_markdown

    output_dir = args["output_dir"]
    feedback   = args["feedback"]
    model      = args.get("model", "local")
    final_path = os.path.join(output_dir, "final.md")

    print(f"피드백 반영 중... (모델: {model})")
    with open(final_path, encoding="utf-8") as f:
        current = f.read()

    client  = LLMClient(model)
    updated = apply_feedback(current, feedback, client)

    versions = glob.glob(os.path.join(output_dir, "final_v*.md"))
    version  = len(versions) + 2
    versioned = os.path.join(output_dir, f"final_v{version}.md")
    save_markdown(updated, versioned)
    save_markdown(updated, final_path)
    print(f"  ✅ 수정 완료 → {versioned}")

    return {"type": "manual", "versioned_path": versioned, "content": updated}
