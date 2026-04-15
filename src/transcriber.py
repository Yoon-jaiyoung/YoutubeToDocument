import os


def transcribe(audio_path: str, model_size: str = "base") -> tuple[str, str]:
    """
    오디오 파일을 텍스트로 변환 (faster-whisper)
    Returns: (text, language)
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise ImportError("faster-whisper가 설치되지 않았습니다. pip install faster-whisper")

    print(f"  STT 모델 로딩 중 ({model_size})...")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")

    print(f"  음성 인식 중: {os.path.basename(audio_path)}")
    segments, info = model.transcribe(audio_path, beam_size=5)

    texts = []
    for segment in segments:
        texts.append(segment.text.strip())

    full_text = " ".join(texts)
    language = info.language

    print(f"  감지된 언어: {language}")
    return full_text, language
