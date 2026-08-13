# TASK.md — 이 레포 실행 단일 기준
```text
REPO: pds2225/auto_addcalender
BASE: main
```
## 0. Git 동기화·STOP 게이트
1. `git fetch --all --prune`
2. origin/branch/dirty 확인.
3. `git rev-list --left-right --count HEAD...origin/main`으로 ahead/behind/diverged 확인.
4. `main` clean + ahead=0 + behind>0일 때만 `git merge --ff-only origin/main`으로 최신화.
5. dirty/ahead/diverged/다른 브랜치 로컬 변경은 보존. 자동 reset/삭제/덮어쓰기 금지.
6. `git reset --hard`, force push, `git clean -fd`, 임의 stash/drop 금지.
7. 로컬 변경이 있으면 최신 `origin/main` 기준 별도 branch/worktree 생성. 안전 분리 불가 시 `BLOCKED`.
8. 이 `TASK.md`만 실행. 다른 레포 TASK/NEXT_TASK/옛 채팅 과업 금지.
9. 과업 후 테스트·commit·push. 명시 없으면 `main` 병합 금지.
## 목표
현재 등록된 과업 없음. 새 과업이 명시되기 전에는 구현하지 않는다.
## 현재상태
- 기본 브랜치: `main`
- CURRENT TASK: 없음
## 구현범위
- 없음
## 금지사항
- 임의 개발·리팩터링·다른 레포 작업, 테스트 삭제/skip 금지.
## 입력검증
- 저장소/origin 확인 후 최신 원격 기준 확보.
## 빈상태
- 과업 없음 → `NO_ACTIVE_TASK` 후 즉시 종료.
## 로딩상태
- 향후 UI/비동기 과업은 loading 상태 필수.
## 오류상태
- 오류를 숨기지 말고 증거와 함께 `BLOCKED`/`FAIL` 보고.
## 테스트
- 과업 시 targeted test + 필요한 전체 테스트.
## 회귀검증
- 기존 정상 기능 회귀 확인.
## 문서동기화
- README/TASKS/관련 문서가 구현과 불일치할 때 필요한 범위만 갱신.
## Git 규칙
- 독립 작업은 별도 branch/worktree 병렬 가능. 최신 `origin/main` 기준으로 작업→테스트→commit→push. 별도 지시 없으면 병합 금지.
## DONE/BLOCKED
- DONE: 구현·필수 테스트·회귀검증·문서동기화 통과.
- BLOCKED: 요구 불명확/의존성 없음/sync·충돌·환경·테스트 실패/사용자 결정 필요.
## 최종보고
```text
REPO:
BASE_SYNC: CLEAN_CURRENT | FAST_FORWARDED | LOCAL_CHANGES_PRESERVED | DIVERGED | BLOCKED
BRANCH:
COMMIT:
PUSH:
CHANGED:
TEST:
REGRESSION:
STATUS: DONE | BLOCKED | FAIL | NO_ACTIVE_TASK
```
## 실행지시
원격 상태를 안전하게 확인·동기화한 뒤 이 `TASK.md`를 처음부터 끝까지 읽고 여기에 적힌 과업만 수행한다.
