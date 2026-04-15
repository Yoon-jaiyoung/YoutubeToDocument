import os
import re
import tempfile


def _extract_video_id(url: str) -> str:
    patterns = [
        r'(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})',
        r'(?:embed/)([a-zA-Z0-9_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise ValueError(f"YouTube URL에서 비디오 ID를 추출할 수 없습니다: {url}")


def _clean_url(url: str) -> str:
    """비디오 ID만 사용하는 순수 URL로 정규화"""
    video_id = _extract_video_id(url)
    return f"https://www.youtube.com/watch?v={video_id}"


def _get_video_title(url: str) -> str:
    try:
        import yt_dlp
        clean = _clean_url(url)
        opts = {'quiet': True, 'no_warnings': True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(clean, download=False)
            return info.get('title', 'untitled')
    except Exception:
        return 'untitled'


def _try_subtitle(video_id: str) -> tuple[str, str] | None:
    """youtube-transcript-api로 자막 추출 시도. 성공 시 (text, lang) 반환"""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

        # 한국어 우선, 없으면 영어, 그 외 첫 번째
        for lang in ['ko', 'en']:
            try:
                transcript = transcript_list.find_transcript([lang])
                entries = transcript.fetch()
                text = ' '.join(e['text'] for e in entries)
                return text, lang
            except NoTranscriptFound:
                continue

        # 생성된 자막(자동 생성) 포함하여 재시도
        for transcript in transcript_list:
            entries = transcript.fetch()
            text = ' '.join(e['text'] for e in entries)
            return text, transcript.language_code

    except Exception:
        return None


def _download_audio(url: str, output_dir: str) -> str:
    """yt-dlp로 오디오 다운로드. 파일 경로 반환"""
    import yt_dlp

    output_template = os.path.join(output_dir, "audio.%(ext)s")
    opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url)
        ext = info.get('ext', 'webm')
        # yt-dlp가 실제로 저장한 파일명 탐색
        for f in os.listdir(output_dir):
            if f.startswith("audio."):
                return os.path.join(output_dir, f)
        return os.path.join(output_dir, f"audio.{ext}")


def get_transcript(url: str, temp_dir: str = None) -> dict:
    """
    YouTube URL에서 자막/음성 추출
    Returns:
      {
        "text": str,
        "lang": str,
        "title": str,
        "method": "subtitle" | "stt",
        "audio_path": str | None,
      }
    """
    print("  영상 정보 조회 중...")
    url = _clean_url(url)  # playlist 파라미터 제거
    title = _get_video_title(url)
    video_id = _extract_video_id(url)

    print("  자막 추출 시도 중...")
    result = _try_subtitle(video_id)
    if result:
        text, lang = result
        print(f"  자막 추출 성공 ({lang})")
        return {
            "text": text,
            "lang": lang,
            "title": title,
            "method": "subtitle",
            "audio_path": None,
        }

    # 자막 없음 → 오디오 다운로드
    print("  자막 없음 → 오디오 다운로드 중...")
    if temp_dir is None:
        temp_dir = tempfile.mkdtemp()
    audio_path = _download_audio(url, temp_dir)
    print(f"  오디오 다운로드 완료: {os.path.basename(audio_path)}")

    return {
        "text": None,
        "lang": None,
        "title": title,
        "method": "stt",
        "audio_path": audio_path,
    }
