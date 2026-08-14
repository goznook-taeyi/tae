# Skill Observation Log

Observations captured during task-oriented work. Each entry identifies a
potential skill improvement or new skill opportunity.

**Status key:** OPEN = not yet actioned | ACTIONED = skill updated/created |
DECLINED = user decided not to pursue

---

### Observation 1: 한국 사이트 팩트체크 시 WebFetch 403 우회 경로

**Status:** OPEN
**Date:** 2026-07-19
**Session context:** 한국 의료광고 규제(의료법 56조 등) 전자책 팩트체크 리서치
**Skill:** New skill candidate: kr-factcheck-research
**Type:** open-source
**Phase/Area:** 웹 리서치 도구 선택

**Issue:** law.go.kr, mohw.go.kr, korea.kr, casenote.kr 등 한국 정부/법령/언론 사이트가 에이전트 프록시 환경에서 WebFetch 시 일관되게 403을 반환함. 반면 WebSearch(요약 포함)와 Naver Search MCP(뉴스 검색)는 정상 동작하여, 법령 조문·보도자료 내용을 다중 출처 교차검증 방식으로 확보함.

**Suggested improvement:** 한국어 팩트체크 리서치 스킬을 만든다면 "정부/법령 사이트는 직접 fetch 대신 WebSearch 요약 + Naver 뉴스 MCP 교차검증을 1차 경로로, 원문 fetch는 보조로" 하는 순서를 명시할 것.

**Principle:** 특정 국가/도메인군이 프록시에서 차단될 때는 반복 fetch 재시도보다 검색 요약의 다중 출처 교차검증으로 전환하는 것이 빠르고, 최종 산출물에 "원문 직접 확인 불가" 사실을 확신도에 반영해야 한다.
