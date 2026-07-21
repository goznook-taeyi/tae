# 자막 오타 검수 보조 도구 — Hugging Face Spaces (Docker SDK) 규격
#
# HF Spaces는 컨테이너를 UID 1000 비루트로 실행하고 포트 7860을 노출한다.
# 무료 티어는 재시작 시 디스크가 초기화되므로, PaddleOCR 한국어 모델을
# 빌드 단계에서 미리 내려받아 이미지에 굽는다(콜드스타트 수 분 → 수 초).

FROM python:3.11-slim

# opencv-python-headless 런타임 의존성
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# HF 규격: UID 1000 비루트 사용자
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

COPY --chown=user app/ ./app/
COPY --chown=user frontend/ ./frontend/
COPY --chown=user hanspell/ ./hanspell/

# 한국어 OCR 모델을 이미지에 베이킹 (렌더한 한글 이미지로 전체 파이프라인 워밍)
RUN python -c "\
import numpy as np; \
from app.ocr import PaddleOCREngine; \
eng = PaddleOCREngine(lang='korean'); \
img = np.full((80, 320, 3), 255, dtype=np.uint8); \
eng.read_boxes(img); \
print('PaddleOCR Korean models baked into image')"

EXPOSE 7860
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
