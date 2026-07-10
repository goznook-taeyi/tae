"""숏폼 오토에디터 진입점.

    python main.py

세로(9:16) 숏폼 영상을 후킹→유지→Main→CTA 구조로 컷편집하고 자막을 자동 생성해
CapCut(Windows) draft 프로젝트로 만들어 준다.
"""

from shortform_editor.gui import main

if __name__ == "__main__":
    main()
