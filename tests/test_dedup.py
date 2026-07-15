from app.dedup import merge_adjacent
from app.models import SubtitleSegment


def seg(id, start, end, text, conf=0.9, frames=3):
    return SubtitleSegment(
        id=id, start_s=start, end_s=end, text=text, ocr_confidence=conf, frame_count=frames
    )


def test_merge_adjacent_similar():
    segs = [
        seg("a", 0, 3, "안녕하세요 반갑습니다"),
        seg("b", 3, 4, "안녕하세요 반갑습니다"),  # 동일 → 병합
        seg("c", 4, 7, "완전히 다른 자막"),
    ]
    out = merge_adjacent(segs)
    assert len(out) == 2
    assert out[0].start_s == 0
    assert out[0].end_s == 4
    assert out[0].frame_count == 6


def test_no_merge_when_different():
    segs = [seg("a", 0, 3, "가나다"), seg("b", 3, 6, "라마바사아자")]
    out = merge_adjacent(segs)
    assert len(out) == 2


def test_merge_keeps_higher_confidence_text():
    segs = [
        seg("a", 0, 3, "안녕하세요", conf=0.6),
        seg("b", 3, 6, "안녕하세요!", conf=0.95),
    ]
    out = merge_adjacent(segs)
    assert len(out) == 1
    assert out[0].ocr_confidence == 0.95
