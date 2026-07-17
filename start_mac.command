#!/bin/bash
# macOS: 이 파일을 더블클릭하면 앱이 실행됩니다.
# (처음 실행 시 "확인되지 않은 개발자" 경고가 뜨면: 우클릭 → 열기)
cd "$(dirname "$0")"
echo
echo "  자막 오타 검수 보조 도구를 시작합니다..."
echo

if command -v python3 >/dev/null 2>&1; then
  python3 scripts/run_local.py
else
  echo "  [오류] Python이 없습니다. https://www.python.org/downloads/ 에서 설치 후 다시 실행하세요."
fi

read -p "종료하려면 Enter를 누르세요..."
