# AGENTS.md — 에이전트 역할 정의

## Auto Dev Queue 에이전트 구성

---

### AGENT-01: sync-checker

**역할**: Git 동기화 점검  
**트리거**: 작업 시작 전, PR 생성 전  
**수행 작업**:
- `git fetch --prune origin`
- `HEAD` vs `origin/main` 비교
- `git status --short` 확인
- 결과를 12줄 이내 보고

**금지**: commit, push, pull, reset, clean

---

### AGENT-02: branch-manager

**역할**: 작업 브랜치 생성 및 관리  
**트리거**: 새 작업 시작  
**수행 작업**:
- `main_프로젝트명_MMDD` 형식 브랜치 생성
- 브랜치 존재 여부 확인 후 중복 방지
- 작업 완료 후 PR 생성 보조

**브랜치 규칙**: `main_auto_addcalender_MMDD`

---

### AGENT-03: structure-auditor

**역할**: 프로젝트 구조 점검 및 Auto Dev Queue 적용 가능 여부 평가  
**트리거**: 신규 저장소 연결 시, 주요 작업 시작 전  
**수행 작업**:
- 파일 목록 및 변경 범위 보고
- README, TASKS, AGENTS, workflow, scripts 존재 여부 확인
- 파일 본문 분석은 필요 최소한으로 제한

---

### AGENT-04: doc-writer

**역할**: 문서 파일 생성 및 유지  
**트리거**: 문서 파일 부재 감지 시  
**수행 작업**:
- `README.md`, `CLAUDE.md`, `TASKS.md`, `AGENTS.md` 생성/갱신
- 기존 코드 기능에 영향 없는 순수 문서 작업
- 테스트 생략 가능

---

### AGENT-05: ci-configurator

**역할**: GitHub Actions CI/CD 파이프라인 설정  
**트리거**: `.github/workflows/` 부재 시  
**수행 작업**:
- `ci.yml` 생성 (lint, 의존성 설치 검증)
- Streamlit 앱 구동 가능 여부 기본 확인
- secrets 설정 가이드 제공

---

## 에이전트 실행 순서 (표준 워크플로)

```
sync-checker → branch-manager → structure-auditor → doc-writer → ci-configurator
```

## 보고 형식 (모든 에이전트 공통)

```
- commit hash:
- 수정 파일:
- 테스트 결과:
- PR 링크:
```

## 프로젝트별 한 줄 지침

- GitHub 저장소는 `pds2225/auto_addcalender` 기준으로 보고한다.
- 핵심 동작 파일은 `app.py`이므로 일정 추출, 공유 문구, `.ics` 생성 변경 시 먼저 확인한다.
- 공유 문구는 기본적으로 `제목 / 일시 / 장소` 중심으로 짧게 유지한다.
## 프로젝트별 작업 지침

### 1. 프로젝트 목적

- 이 프로젝트는 텍스트에서 일정 정보를 추출하고 공유/캘린더 등록을 돕는 앱 저장소다.
- AI는 GitHub 저장소를 `pds2225/auto_addcalender` 기준으로 보고한다.
- 요구사항이 애매하면 새 기능을 만들지 말고, `app.py`의 현재 일정 추출/공유 흐름을 깨지 않는 최소 수정으로 처리한다.

### 2. 절대 수정 금지

- `.env`, `.env.*` 파일은 절대 수정하거나 내용을 출력하지 않는다.
- `.github/workflows/*`는 사용자가 명시적으로 요청하지 않으면 수정하지 않는다.
- API Key, Token, 비밀번호, 쿠키 값은 답변이나 로그에 출력하지 않는다.
- 사용자 변경사항은 임의로 되돌리지 않는다.

### 3. 수정 허용 범위

- 요청과 직접 관련된 파일만 수정한다.
- 일정 추출, 공유 문구, `.ics` 생성 변경은 먼저 `app.py`에서 현재 동작을 확인한다.
- 공유 문구는 기본적으로 `제목 / 일시 / 장소` 중심으로 짧게 유지한다.
- 단순 버그 수정에서 전면 리팩토링을 하지 않는다.

### 4. 실행/검증 기준

```powershell
cd D:\auto_addcalender
python -m py_compile app.py
python -m pytest -q
```

- 테스트가 없거나 실행이 막히면 그 이유를 짧게 보고한다.
- 실행 확인을 못 했으면 "미검증"이라고 명확히 말한다.

### 5. Git 규칙

- 사용자가 요청하지 않으면 커밋하지 않는다.
- 사용자가 요청하지 않으면 push하지 않는다.
- 커밋 전에는 `git status --short`로 포함 파일을 확인한다.
- 런타임 데이터, 캐시, 로그, `.env`, 개인 설정 파일은 커밋하지 않는다.

### 6. 보고 형식

```text
상태: 정상 실행 확인됨 / 수정만 완료 / 미검증 / 실행 막힘

수정 파일:
- D:\path\file.py: 수정 이유

검증:
- 실행 명령어:
- 결과:

주의:
- 남은 리스크 또는 사람이 확인할 항목
```

### 7. 자주 하는 실수 방지

- 메모/연도/상세정보를 공유 문구에 다시 길게 넣지 않는다.
- Google Calendar 링크, 텍스트 공유, `.ics` 다운로드를 서로 다른 기능으로 구분한다.
- Windows에서는 Bash 명령어 대신 PowerShell 명령어를 쓴다.
- 포트가 열렸다는 것과 앱이 정상 동작한다는 것을 구분한다.

