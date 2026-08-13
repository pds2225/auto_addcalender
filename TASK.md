<!-- BEGIN OPS HEADER: 실행 게이트. 본문보다 우선. -->
# TASK.md — 이 레포 실행 단일 기준
```text
REPO: pds2225/auto_addcalender
BASE: main
```
## 0. STOP 게이트
- `git fetch --all --prune`, origin URL, branch, dirty 상태 확인.
- 이 `TASK.md`만 실행. 다른 레포/NEXT_TASK/옛 채팅 과업 사용 금지.
- 기본 브랜치 직접 개발, destructive git, force push, secret/.env 수정 금지.
- 명시 없으면 기본 브랜치 병합 금지.
<!-- END OPS HEADER -->

# TASK — auto_addcalender
## 목표
현재 등록된 과업 없음. 새 과업이 명시되기 전에는 구현하지 않는다.
## 현재상태
- 기본 브랜치: `main`
- CURRENT TASK: 없음
## 구현범위
- 없음
## 금지사항
- 임의 기능 개발·리팩터링·다른 레포 작업 금지.
- 테스트 삭제/skip으로 성공 처리 금지.
## 입력검증
- 저장소와 origin이 `pds2225/auto_addcalender`인지 확인하고 원격 `main` 최신화 후 CURRENT TASK를 확인한다.
## 빈상태
- 과업 없음 → `NO_ACTIVE_TASK` 보고 후 즉시 종료.
## 로딩상태
- 향후 UI/비동기 과업에서는 loading 상태 필수.
## 오류상태
- 오류를 숨기지 말고 증거와 함께 `BLOCKED`/`FAIL` 보고.
## 테스트
- 과업 시 targeted test + 필요한 전체 테스트 실행.
## 회귀검증
- 기존 정상 기능 회귀 확인.
## 문서동기화
- README/TASKS/관련 문서가 구현과 불일치할 때 필요한 범위만 갱신.
## Git 규칙
- 독립 작업은 별도 branch/worktree 병렬 가능.
- 별도 지시 없으면 구현→테스트→commit→push까지만, `main` 병합 금지.
## DONE/BLOCKED
- DONE: 구현·필수 테스트·회귀검증·필요 문서동기화 전부 통과.
- BLOCKED: 요구 불명확/의존성 없음/환경·테스트 실패/사용자 결정 필요.
## 최종보고
```text
REPO:
BRANCH:
COMMIT:
PUSH:
CHANGED:
TEST:
REGRESSION:
STATUS: DONE | BLOCKED | FAIL | NO_ACTIVE_TASK
```
## 실행지시
원격 `main` 최신화 후 이 `TASK.md`를 처음부터 끝까지 읽고 여기에 적힌 과업만 수행한다.
