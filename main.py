"""CapCut 편집 스튜디오 진입점.

    python main.py

캡컷이 만든 프로젝트를 골라 자동 가편집(무음·NG 컷, 구조 배치, 자막, 타이틀)하고,
요청사항이 있으면 Claude가 이어서 다듬는다. 통합 창 = shortform_editor/studio.py.
(구버전 단일 창은 shortform_editor/gui.py로 남아 있음)
"""

from shortform_editor.studio import main

if __name__ == "__main__":
    main()
