import re


FILLER_WORDS_KO = [
    r'\b(어+|음+|아+|에+|그+|저+|뭐+|네+|예+)\b',
    r'\[음악\]', r'\[박수\]', r'\[웃음\]', r'\[Music\]', r'\[Applause\]',
]

FILLER_WORDS_EN = [
    r'\b(uh+|um+|er+|ah+|like|you know|i mean|basically|literally|actually|right\?|okay\?)\b',
]


def clean_transcript(text: str, lang: str = "ko") -> str:
    # 줄바꿈 정리
    text = re.sub(r'\n+', ' ', text)
    # 특수문자 정리
    text = re.sub(r'[^\w\s\.,!?;:()\-\'"가-힣]', ' ', text)
    # 한국어 필러 제거
    for pattern in FILLER_WORDS_KO:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    # 영어 필러 제거
    if lang == "en":
        for pattern in FILLER_WORDS_EN:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    # 연속 공백 정리
    text = re.sub(r'\s{2,}', ' ', text)
    # 반복 문장 제거 (연속으로 같은 문장이 2회 이상 등장)
    sentences = text.split('. ')
    seen = []
    for s in sentences:
        s = s.strip()
        if s and s not in seen[-3:]:
            seen.append(s)
    text = '. '.join(seen)
    return text.strip()


def chunk_text(text: str, max_chars: int = 8000) -> list[str]:
    """긴 텍스트를 청크로 분할 (문장 단위)"""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    current = []
    current_len = 0
    for sentence in sentences:
        if current_len + len(sentence) > max_chars and current:
            chunks.append(' '.join(current))
            current = [sentence]
            current_len = len(sentence)
        else:
            current.append(sentence)
            current_len += len(sentence)
    if current:
        chunks.append(' '.join(current))
    return chunks
