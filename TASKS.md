# TASKS.md — Auto Dev Queue

> **deprecated — 실행 기준은 `origin/main:TASK.md` 하나다. 이 파일은 과거 기록이며 실행하지 않는다(삭제하지 않음).**

## 상태 범례

| 심볼 | 상태 |
|------|------|
| `[ ]` | 대기 |
| `[~]` | 진행 중 |
| `[x]` | 완료 |
| `[!]` | 블로킹 |

---

## 완료된 작업

- [x] TASK-001: GitHub 저장소 clone 및 로컬-원격 동기화 확인 (2026-05-10)
- [x] TASK-002: README.md 생성 — 프로젝트 설명·설치·실행법·브랜치 규칙 (2026-05-11, PR #12)
- [x] TASK-003: CLAUDE.md (RULES) 생성 — Claude Code 작업 가이드·금지 사항 (2026-05-11, PR #12)
- [x] TASK-004: AGENTS.md 생성 — 5개 에이전트 역할 정의 및 표준 워크플로 (2026-05-11, PR #12)
- [x] TASK-005: GitHub Actions CI workflow 생성 — ruff lint + date_utils 스모크 테스트 (2026-05-11, PR #12)
- [x] TASK-006: PR #19 — 저장소에 해당 PR 존재하지 않음 (확인일: 2026-05-11, not found)
- [x] TASK-007: TASKS.md 동기화 + app.py 수정 (2026-05-11)
  - TASK-002~005 DONE 처리
  - TASK-006 PR #19 not found 기록
  - build_calendar_url(): /r/eventedit + calid=primary 로 내 캘린더 등록 수정
  - split_multiday_events(): 다일 일정 날짜별 분리 추가

---

## 대기 중인 작업

- [ ] TASK-008: [기획보류] 업무 일정 우선 히스토리 분류 기반 추출 고도화 (Issue #17, 로컬/자체서버 전용)
  - category 키워드 판단 → event_history.json 저장 → 같은 category 최대 3개 프롬프트 삽입
  - work 입력 시 personal 히스토리 제외, 중복 검증 금지
  - 구현 프롬프트: Issue #17 본문 참고

- [ ] Streamlit Cloud 배포 설정 확인 및 문서화
- [ ] `date_utils.py` 엣지케이스 단위 테스트 추가 (`tests/test_date_utils.py`)
- [ ] OpenAI 프롬프트 버전 관리 분리 (별도 파일 또는 상수)
- [ ] `.env.example` 파일 추가 (로컬 개발 환경 설정 가이드)
- [ ] 카카오 캘린더 `.ics` 인코딩 이슈 검증 (한글 파일명)
- [ ] 모바일에서 calid=primary 실제 동작 검증 (구글 캘린더 앱 vs 모바일 웹)

---

## 작업 추가 방법

새 작업은 아래 형식으로 "대기 중인 작업" 섹션에 추가:

```
- [ ] TASK-NNN: 작업 내용 (담당: AGENT명, 기한: YYYY-MM-DD)
```
