# CLAUDE.md — auto_addcalender 작업 가이드

## 테스트·우선순위 (2026-11-23 다솜 규칙 · 기존 테스트 규칙보다 우선)
- 회귀테스트 하지 않는다. 테스트는 최소화한다(새 테스트 추가·단계별 테스트 실행 안 함).
- 작업마다 직접 써 보고 1가지만 확인한다. 통합 테스트는 모든 작업을 마친 뒤 마지막에 1번만 한다.
- 실제 사용 기준을 최우선으로 한다.
- 안정성·보안은 최소한만 본다(바로 깨지는 것·비밀값 노출만).
- 확장성은 고려하지 않는다.
- 이 저장소의 기존 테스트·검증 규칙과 부딪히면 이 규칙을 따른다. 기존 문장은 지우지 않는다.

## 답변 언어 (2026-11-23 다솜 규칙)
- 다솜에게 하는 답변·보고·질문은 **한국어**로 한다. 다솜이 따로 요청할 때만 영어로 쓴다(코드·명령어·고유명사는 원문 그대로).

## 세션 시작 (TASK.md는 통째로 읽지 않는다)
- `git fetch origin --prune` 후 `git show origin/main:TASK.md | sed -n '1,/^# 1\./p'`로 LIST만 본다. `NO_ACTIVE_TASK`면 개발하지 않고 보고 후 끝낸다.
- `[ ]`/`[~]` TASK가 있을 때만 `# 8. TASK DETAILS`의 그 TASK와 필요한 규칙 절만 읽는다.
- Git·검증 규칙(.env·워크플로 무단 수정 금지, 비밀값 출력 금지 등)은 `AGENTS.md` §2·§4·§5를 따른다.

## 프로젝트 개요

- **앱명**: AI 일정 자동 등록 (Omni-Sync Mobile)
- **스택**: Python 3.11, Streamlit, OpenAI GPT-4o
- **진입점**: `app.py`, 유틸리티: `date_utils.py`, 일괄 열기 `bulk_open.py`, 붙여넣기 도구 `clipboard_paste/`

## 브랜치 규칙

| 규칙 | 내용 |
|------|------|
| 메인 브랜치 | `main` |
| 작업 브랜치 형식 | `main_auto_addcalender_MMDD` |
| `main` 직접 커밋 | **금지** |
| `reset --hard` | **금지** |
| `clean -fd` | **금지** |

## 작업 순서

1. `main`에서 작업 브랜치 생성
2. 프로젝트 구조 점검 후 변경 범위 보고
3. 기존 기능 보존하며 수정
4. 커밋 후 PR 생성

## 금지 사항

- `main` 브랜치에 직접 push/commit
- 기존 일정 추출 로직(`process_text`, `build_calendar_url`, `build_ics_content`) 임의 변경
- OpenAI 프롬프트 무단 수정
- 전체 테스트 불필요 실행 (문서·설정 변경 시 테스트 생략 가능)

## 환경 변수

- `OPENAI_API_KEY`: Streamlit secrets 또는 `.env` (`.gitignore` 적용됨)

## 커밋 보고 형식

```
- commit hash:
- 수정 파일:
- 테스트 결과:
- PR 링크:
```

## Auto Dev Queue 파일

| 파일 | 역할 |
|------|------|
| `TASK.md` (origin/main) | 유일한 작업 SSOT |
| `TASKS.md` | deprecated 과거 기록(실행 금지, 삭제 안 함) |
| `AGENTS.md` | 에이전트별 역할 정의 |
| `.github/workflows/ci.yml` | CI 파이프라인 |
