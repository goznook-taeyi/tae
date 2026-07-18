"""자막(캡션) 생성 — STT 래퍼 + cue 분할 + 타임코드 포맷.

순수 로직(cue 분할, 타임코드, SRT)은 FFmpeg/whisper 없이 테스트된다.
실제 음성인식 transcribe()만 faster-whisper에 의존한다.

시간 단위는 '초(float)'.
"""

from __future__ import annotations

# 한 자막 cue의 권장 상한(가독성). 세로 숏폼 기준.
MAX_CHARS = 20
MAX_CUE_DURATION = 5.0


def format_timecode(seconds: float, sep: str = ",") -> str:
    """초 → "HH:MM:SS,mmm" (SRT 표준). 음수는 0으로 클램프."""
    if seconds < 0:
        seconds = 0.0
    total_ms = int(round(seconds * 1000))
    ms = total_ms % 1000
    total_s = total_ms // 1000
    s = total_s % 60
    m = (total_s // 60) % 60
    h = total_s // 3600
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def split_cue(cue: dict, max_chars: int = MAX_CHARS,
              max_duration: float = MAX_CUE_DURATION) -> list[dict]:
    """긴 자막 하나를 여러 cue로 쪼갠다(글자수/길이 기준).

    시간은 각 조각의 글자수 비율로 나눠 배분한다.
    cue: {"start","end","text", (optional) "source_id"}
    """
    text = (cue["text"] or "").strip()
    start = float(cue["start"])
    end = float(cue["end"])
    sid = cue.get("source_id")
    duration = max(end - start, 0.0)

    if not text:
        return []

    need_split = len(text) > max_chars or duration > max_duration
    if not need_split:
        out = {"start": start, "end": end, "text": text}
        if sid is not None:
            out["source_id"] = sid
        return [out]

    # 단어 단위로 max_chars 이하 줄로 묶기(공백 없는 언어는 글자 단위로).
    lines = _wrap(text, max_chars)
    total_chars = sum(len(ln) for ln in lines) or 1
    pieces: list[dict] = []
    cursor = start
    for i, line in enumerate(lines):
        share = len(line) / total_chars
        seg_dur = duration * share
        seg_start = cursor
        seg_end = end if i == len(lines) - 1 else cursor + seg_dur
        piece = {"start": seg_start, "end": seg_end, "text": line}
        if sid is not None:
            piece["source_id"] = sid
        pieces.append(piece)
        cursor = seg_end
    return pieces


def _wrap(text: str, max_chars: int) -> list[str]:
    """텍스트를 max_chars 이하 줄들로 나눈다."""
    words = text.split()
    if not words:  # 공백이 없으면 글자 단위로 잘라냄
        return [text[i:i + max_chars] for i in range(0, len(text), max_chars)] or [text]

    lines: list[str] = []
    cur = ""
    for w in words:
        candidate = w if not cur else f"{cur} {w}"
        if len(candidate) <= max_chars:
            cur = candidate
        else:
            if cur:
                lines.append(cur)
            # 단어 자체가 너무 길면 강제로 쪼갠다
            if len(w) > max_chars:
                for i in range(0, len(w), max_chars):
                    lines.append(w[i:i + max_chars])
                cur = ""
            else:
                cur = w
    if cur:
        lines.append(cur)
    return lines


def cues_from_segments(segments: list[dict], source_id: str,
                       max_chars: int = MAX_CHARS,
                       max_duration: float = MAX_CUE_DURATION) -> list[dict]:
    """STT 원시 세그먼트 목록을 자막 cue 목록으로 정규화한다.

    segments: [{"start","end","text"}, ...]
    반환: [{"source_id","start","end","text"}, ...]
    """
    out: list[dict] = []
    for seg in segments:
        cue = {
            "source_id": source_id,
            "start": float(seg["start"]),
            "end": float(seg["end"]),
            "text": (seg.get("text") or "").strip(),
        }
        out.extend(split_cue(cue, max_chars, max_duration))
    return out


def build_srt(captions: list[dict]) -> str:
    """최종 타임라인 자막을 SRT 문자열로. (디버그/미리보기용)"""
    blocks = []
    for i, cap in enumerate(captions, start=1):
        blocks.append(
            f"{i}\n"
            f"{format_timecode(cap['start'])} --> {format_timecode(cap['end'])}\n"
            f"{cap['text']}\n"
        )
    return "\n".join(blocks)


def transcribe(path: str, source_id: str, language: str | None = None,
               model_size: str = "base") -> list[dict]:
    """실제 음성인식(faster-whisper) → 자막 cue 목록.

    최초 호출 시 모델을 내려받아 캐시한다(오프라인 환경은 미리 캐시 필요).
    """
    cues, _words = transcribe_words(path, source_id, language=language,
                                    model_size=model_size)
    return cues


def transcribe_words(path: str, source_id: str, language: str | None = None,
                     model_size: str = "base",
                     progress_fn=None) -> tuple[list[dict], list[dict]]:
    """음성인식 → (자막 cue 목록, 단어 타임스탬프 목록).

    단어 목록은 대본-전사 정렬(align)에 쓰인다: [{"start","end","text"}].
    progress_fn: 0.0~1.0 진행률 콜백 (영상 내 전사 위치 기준).
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:  # pragma: no cover - 런타임 의존성
        raise RuntimeError(
            "faster-whisper가 설치되지 않았습니다. `pip install -r requirements.txt`"
        ) from e

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, info = model.transcribe(path, language=language,
                                      word_timestamps=True)
    total = float(getattr(info, "duration", 0) or 0)
    raw: list[dict] = []
    words: list[dict] = []
    for s in segments:
        raw.append({"start": s.start, "end": s.end, "text": s.text})
        for w in (s.words or []):
            words.append({"start": w.start, "end": w.end, "text": w.word})
        if progress_fn and total > 0:
            try:
                progress_fn(min(1.0, float(s.end) / total))
            except Exception:  # 진행률 콜백 실패가 전사를 막지 않게
                pass
    cues = cues_from_segments(raw, source_id)
    if not words:  # 모델이 단어 타임스탬프를 못 주면 cue를 쪼개 근사
        from .align import words_from_cues
        words = words_from_cues(cues)
    return cues, words
