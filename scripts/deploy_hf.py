"""Hugging Face Spaces 원커맨드 배포 스크립트.

사용법 (내 PC에서):
    pip install huggingface_hub
    huggingface-cli login          # 또는 환경변수 HF_TOKEN=hf_xxx
    python scripts/deploy_hf.py --space <HF계정명>/subtitle-checker --password <팀공유비밀번호>

하는 일:
    1. Docker SDK Space 생성 (이미 있으면 재사용 = 업데이트 배포)
    2. 앱 파일 업로드 (app/, frontend/, Dockerfile, requirements.txt, Space README)
    3. APP_PASSWORD를 Space Secret으로 설정
    4. Space URL 출력 → 팀에 URL + 비밀번호 공유

재실행하면 같은 Space에 최신 코드가 다시 올라갑니다(업데이트 배포).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# (로컬 경로, Space 내 경로)
UPLOAD_ITEMS = [
    ("app", "app"),
    ("frontend", "frontend"),
    ("Dockerfile", "Dockerfile"),
    ("requirements.txt", "requirements.txt"),
    ("deploy/README_SPACE.md", "README.md"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="HF Spaces 배포")
    parser.add_argument("--space", required=True, help="예: myaccount/subtitle-checker")
    parser.add_argument("--password", required=True, help="팀 공유 비밀번호(APP_PASSWORD)")
    parser.add_argument("--private", action="store_true", help="Space를 비공개로 생성(HF 계정 있는 팀원만)")
    args = parser.parse_args()

    try:
        from huggingface_hub import HfApi
    except ImportError:
        print("huggingface_hub가 없습니다:  pip install huggingface_hub")
        return 1

    api = HfApi()
    try:
        who = api.whoami()
        print(f"HF 로그인 확인: {who['name']}")
    except Exception:
        print("HF 토큰이 없습니다. `huggingface-cli login` 또는 HF_TOKEN 환경변수를 설정하세요.")
        print("토큰 발급: https://huggingface.co/settings/tokens (write 권한)")
        return 1

    print(f"Space 생성/확인: {args.space}")
    api.create_repo(
        repo_id=args.space,
        repo_type="space",
        space_sdk="docker",
        private=args.private,
        exist_ok=True,
    )

    print("파일 업로드 중...")
    for local, remote in UPLOAD_ITEMS:
        path = REPO_ROOT / local
        if not path.exists():
            print(f"  건너뜀(없음): {local}")
            continue
        if path.is_dir():
            api.upload_folder(
                repo_id=args.space,
                repo_type="space",
                folder_path=str(path),
                path_in_repo=remote,
                ignore_patterns=["__pycache__", "*.pyc"],
            )
        else:
            api.upload_file(
                repo_id=args.space,
                repo_type="space",
                path_or_fileobj=str(path),
                path_in_repo=remote,
            )
        print(f"  업로드: {local} -> {remote}")

    print("비밀번호(Secret) 설정...")
    api.add_space_secret(repo_id=args.space, key="APP_PASSWORD", value=args.password)

    url = f"https://huggingface.co/spaces/{args.space}"
    print()
    print("=" * 60)
    print("배포 요청 완료! 빌드는 10~20분 걸립니다 (OCR 모델 베이킹).")
    print(f"빌드 로그/앱 확인: {url}")
    print()
    print("빌드가 끝나면 팀원들에게 공유하세요:")
    print(f"  주소: {url}")
    print(f"  비밀번호: (설정하신 값)")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
