from app.vote import OcrRead, majority_vote, normalize_text


def test_normalize_collapses_whitespace():
    assert normalize_text("  안녕   하세요 ") == "안녕 하세요"


def test_unanimous_reads():
    reads = [OcrRead("안녕하세요", 0.9) for _ in range(5)]
    r = majority_vote(reads)
    assert r.text == "안녕하세요"
    assert r.agreement == 1.0
    assert abs(r.confidence - 0.9) < 1e-6


def test_majority_overrides_single_ocr_error():
    # 5개 중 4개 정답, 1개 오독 → 다수결이 정답 복원
    reads = [
        OcrRead("좋네요", 0.9),
        OcrRead("좋네요", 0.9),
        OcrRead("좋네요", 0.9),
        OcrRead("좋내요", 0.8),  # OCR 오독
        OcrRead("좋네요", 0.9),
    ]
    r = majority_vote(reads)
    assert r.text == "좋네요"
    assert r.agreement > 0.7


def test_low_agreement_when_reads_disagree():
    reads = [
        OcrRead("가나다", 0.5),
        OcrRead("라마바", 0.5),
        OcrRead("사아자", 0.5),
    ]
    r = majority_vote(reads)
    # 위치별 다수결 일치도가 낮아야 함
    assert r.agreement < 0.7


def test_empty_reads():
    r = majority_vote([OcrRead("", 0.0), OcrRead("  ", 0.0)])
    assert r.text == ""
    assert r.agreement == 0.0
