"""
Markdown → Notion 페이지 업로더

사전 준비:
1. https://www.notion.so/my-integrations 에서 Integration 생성 → API 키 발급
2. Notion 페이지 열기 → ··· 메뉴 → Connections → Integration 연결
3. 환경변수 설정:
   export NOTION_API_KEY="secret_..."
   export NOTION_PAGE_ID="페이지ID (URL에서 복사)"
"""

import os
import re


# ──────────────────────────────────────────────
# 지원 언어 목록 (Notion 코드 블록)
# ──────────────────────────────────────────────
_NOTION_LANGUAGES = {
    "abap", "arduino", "bash", "basic", "c", "clojure", "coffeescript",
    "c++", "c#", "css", "dart", "diff", "docker", "elixir", "elm",
    "erlang", "flow", "fortran", "f#", "gherkin", "glsl", "go", "graphql",
    "groovy", "haskell", "html", "java", "javascript", "json", "julia",
    "kotlin", "latex", "less", "lisp", "livescript", "lua", "makefile",
    "markdown", "markup", "matlab", "mermaid", "nix", "objective-c", "ocaml",
    "pascal", "perl", "php", "plain text", "powershell", "prolog",
    "protobuf", "python", "r", "reason", "ruby", "rust", "sass", "scala",
    "scheme", "scss", "shell", "sql", "swift", "typescript", "vb.net",
    "verilog", "vhdl", "visual basic", "webassembly", "xml", "yaml",
}

_LANG_ALIASES = {
    "py": "python", "js": "javascript", "ts": "typescript",
    "sh": "shell", "zsh": "shell", "fish": "shell",
    "yml": "yaml", "jsx": "javascript", "tsx": "typescript",
    "cpp": "c++", "cs": "c#", "rb": "ruby", "rs": "rust",
    "kt": "kotlin", "swift": "swift", "go": "go",
    "dockerfile": "docker",
}


def _detect_language(info: str) -> str:
    lang = (info or "").lower().strip().split()[0] if info else ""
    lang = _LANG_ALIASES.get(lang, lang)
    return lang if lang in _NOTION_LANGUAGES else "plain text"


# ──────────────────────────────────────────────
# Rich Text 헬퍼
# ──────────────────────────────────────────────
def _rt(text: str, bold=False, italic=False, code=False, link=None) -> dict:
    """Notion rich_text 항목 하나 생성 (2000자 제한 준수)"""
    chunks = [text[i:i+2000] for i in range(0, max(len(text), 1), 2000)]
    items = []
    for chunk in chunks:
        item: dict = {"type": "text", "text": {"content": chunk}}
        ann = {}
        if bold:
            ann["bold"] = True
        if italic:
            ann["italic"] = True
        if code:
            ann["code"] = True
        if ann:
            item["annotations"] = ann
        if link:
            item["text"]["link"] = {"url": link}
        items.append(item)
    return items


def _parse_inline(children: list) -> list:
    """인라인 AST 노드 → Notion rich_text 리스트"""
    result = []
    for node in children:
        t = node.get("type", "")

        if t == "text":
            result += _rt(node.get("raw", ""))

        elif t == "strong":
            for inner in node.get("children") or []:
                raw = inner.get("raw", "")
                if raw:
                    result += _rt(raw, bold=True)

        elif t == "emphasis":
            for inner in node.get("children") or []:
                raw = inner.get("raw", "")
                if raw:
                    result += _rt(raw, italic=True)

        elif t == "codespan":
            result += _rt(node.get("raw", ""), code=True)

        elif t == "link":
            url = (node.get("attrs") or {}).get("url", "")
            for inner in node.get("children") or []:
                raw = inner.get("raw", "")
                if raw:
                    result += _rt(raw, link=url or None)

        elif t in ("softbreak", "linebreak"):
            result += _rt("\n")

        elif t == "image":
            alt = (node.get("attrs") or {}).get("alt", "[이미지]")
            result += _rt(f"[이미지: {alt}]")

        else:
            raw = node.get("raw", "")
            if raw:
                result += _rt(raw)

    return result or _rt("")


# ──────────────────────────────────────────────
# AST 토큰 → Notion 블록 변환
# ──────────────────────────────────────────────
def _list_item_to_block(item: dict, ordered: bool) -> dict:
    block_type = "numbered_list_item" if ordered else "bulleted_list_item"
    rich = []
    sub_blocks = []

    for child in item.get("children") or []:
        ct = child.get("type", "")
        if ct == "list":
            sub_blocks.extend(_token_to_blocks(child))
        elif ct in ("block_text", "paragraph"):
            rich = _parse_inline(child.get("children") or [])
        else:
            raw = child.get("raw", "")
            if raw:
                rich = _rt(raw)

    block = {
        "object": "block",
        "type": block_type,
        block_type: {"rich_text": rich or _rt("")},
    }
    if sub_blocks:
        block[block_type]["children"] = sub_blocks
    return block


def _table_to_block(token: dict) -> dict | None:
    rows_data = []

    for section in token.get("children") or []:
        st = section.get("type", "")
        if st in ("table_head", "table_body"):
            for row in section.get("children") or []:
                cells = [
                    _parse_inline(cell.get("children") or [])
                    for cell in row.get("children") or []
                ]
                rows_data.append(cells)

    if not rows_data:
        return None

    col_count = max(len(r) for r in rows_data)
    # 셀 수 맞추기
    for row in rows_data:
        while len(row) < col_count:
            row.append(_rt(""))

    table_rows = [
        {
            "object": "block",
            "type": "table_row",
            "table_row": {"cells": [c[:col_count] for c in row[:col_count]]},
        }
        for row in rows_data
    ]

    return {
        "object": "block",
        "type": "table",
        "table": {
            "table_width": col_count,
            "has_column_header": True,
            "has_row_header": False,
            "children": table_rows,
        },
    }


def _token_to_blocks(token: dict) -> list[dict]:
    t = token.get("type", "")
    children = token.get("children") or []
    attrs = token.get("attrs") or {}

    # ── 헤딩 ──────────────────────────────────
    if t == "heading":
        level = min(attrs.get("level", 1), 3)
        bt = f"heading_{level}"
        return [{"object": "block", "type": bt, bt: {"rich_text": _parse_inline(children)}}]

    # ── 문단 ──────────────────────────────────
    elif t == "paragraph":
        return [{"object": "block", "type": "paragraph",
                 "paragraph": {"rich_text": _parse_inline(children)}}]

    # ── 코드 블록 ─────────────────────────────
    elif t == "block_code":
        lang = _detect_language(attrs.get("info", ""))
        raw = token.get("raw", "")
        # 2000자 초과 시 분할
        blocks = []
        for i in range(0, max(len(raw), 1), 1900):
            chunk = raw[i:i+1900]
            blocks.append({
                "object": "block",
                "type": "code",
                "code": {
                    "language": lang,
                    "rich_text": [{"type": "text", "text": {"content": chunk}}],
                },
            })
        return blocks

    # ── 목록 ──────────────────────────────────
    elif t == "list":
        ordered = attrs.get("ordered", False)
        return [_list_item_to_block(item, ordered)
                for item in children if item.get("type") == "list_item"]

    # ── 인용 ──────────────────────────────────
    elif t == "block_quote":
        rich = []
        sub = []
        for child in children:
            ct = child.get("type", "")
            if ct == "paragraph":
                rich = _parse_inline(child.get("children") or [])
            elif ct in ("list", "block_code", "heading"):
                sub.extend(_token_to_blocks(child))
            else:
                rich = _parse_inline([child])
        blocks = [{"object": "block", "type": "quote",
                   "quote": {"rich_text": rich or _rt("")}}]
        blocks.extend(sub)
        return blocks

    # ── 구분선 ────────────────────────────────
    elif t == "thematic_break":
        return [{"object": "block", "type": "divider", "divider": {}}]

    # ── 테이블 ────────────────────────────────
    elif t == "table":
        block = _table_to_block(token)
        return [block] if block else []

    # ── 빈 줄 / 기타 ──────────────────────────
    elif t == "blank_line":
        return []

    else:
        raw = token.get("raw", "")
        if raw.strip():
            return [{"object": "block", "type": "paragraph",
                     "paragraph": {"rich_text": _rt(raw)}}]
        return []


# ──────────────────────────────────────────────
# 공개 API
# ──────────────────────────────────────────────
def md_to_notion_blocks(md_text: str) -> list[dict]:
    """Markdown 텍스트 → Notion 블록 리스트"""
    import mistune
    md = mistune.create_markdown(renderer=None, plugins=["table"])
    tokens = md(md_text)
    blocks = []
    for token in tokens:
        blocks.extend(_token_to_blocks(token))
    return blocks


def upload_to_notion(
    md_text: str,
    title: str,
    youtube_url: str,
    parent_page_id: str,
    api_key: str,
) -> str:
    """
    Markdown → Notion 페이지 생성
    Returns: 생성된 페이지 URL
    """
    from notion_client import Client

    client = Client(auth=api_key)

    # 상단 callout: 원본 영상 링크
    callout = {
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": [
                {"type": "text", "text": {"content": "원본 YouTube 영상: "}},
                {"type": "text", "text": {"content": youtube_url,
                                          "link": {"url": youtube_url}}},
            ],
            "icon": {"type": "emoji", "emoji": "📺"},
            "color": "blue_background",
        },
    }

    content_blocks = md_to_notion_blocks(md_text)
    all_blocks = [callout] + content_blocks

    # 첫 100블록으로 페이지 생성
    page = client.pages.create(
        parent={"page_id": parent_page_id},
        properties={
            "title": {"title": [{"type": "text", "text": {"content": title}}]}
        },
        children=all_blocks[:100],
    )

    page_id = page["id"]

    # 나머지 블록 100개씩 추가
    remaining = all_blocks[100:]
    for i in range(0, len(remaining), 100):
        client.blocks.children.append(page_id, children=remaining[i:i+100])

    return page.get("url", f"https://www.notion.so/{page_id.replace('-', '')}")
