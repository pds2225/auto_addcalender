<!-- BEGIN OPS HEADER: 실행 게이트. 본문보다 우선. -->

# TASK.md — 이 레포 실행 단일 기준

```text
REPO:   pds2225/auto_addcalender
REMOTE: https://github.com/pds2225/auto_addcalender.git
BASE:   main
```

## 0. STOP 게이트 (하나라도 실패 → 코드 수정 금지, 즉시 중단)

아래를 **맨 처음** 실행한다. 실패하면 구현하지 않는다.

1. `git fetch --all --prune`  
   - 실패 → **STOP**. 로컬에 있는 옛 TASK로 진행 금지.
2. `git remote get-url origin`  
   - 위 `REMOTE`와 **문자 완전 일치**가 아니면 **STOP**. (다른 레포/worktree 오실행 방지)
3. 실행 파일은 **이 `TASK.md`만**.  
   - `NEXT_TASK.md` / 다른 레포 TASK / 옛 채팅 / AGENTS 외 지시서로 구현 시작 → **STOP** 로그 남기고 중단.  
   - `NEXT_TASK.md`는 큐·참고다. TASK가 “읽어라”고 쓰지 않으면 열지 마라.
4. 허용 범위: 이 파일 + 이 파일이 지명한 코드/테스트/문서.  
   - 지명되지 않은 레포·폴더를 고치기 시작하면 **STOP**.
5. Must 순서: 아래 TRACK에 `depends_on`이 있으면 **선행 TRACK이 DONE일 때만** 후속 TRACK 착수.  
   - 선행 미완료인데 후속 파일을 열면 **STOP**.
6. DONE 금지 (하나라도 해당하면 FAIL, 머지 금지):  
   - 구현 코드 diff 없이 **테스트/픽스처만** 변경  
   - 지정 **smoke 산출물 파일** 없음  
   - 보고에 **커밋 SHA + 실행한 명령 + 테스트 요약 원문(10줄 이내)** 없음
7. `AGENTS.md`와 이 TASK가 충돌:  
   - 코드 수정 중단. `BLOCKED_WITH_EVIDENCE`만 남긴다.  
   - 사용자에게 선택지 3개만: `예외 승인` / `우회(다른 파일)` / `보류`. 선택 전 코드 금지.
8. 머지: 이 TASK 본문이 머지를 **명시**한 경우에만. 그래도 아래 아니면 merge 명령 실행 금지.  
   - GitHub Checks **초록**  
   - 필수 테스트 job 통과  
   - 6번 DONE 금지 항목 없음  
   - 충돌 미해결이면 머지 금지
9. 로컬 dirty / 다른 브랜치: 기본 브랜치(`BASE`)에서 직접 수정 금지. **새 브랜치**에서만 작업.
10. 시크릿: 값은 `D:\_secure\.env.shared`만. TASK에는 키 이름만.  
    시작 시 `D:\_secure\sync.ps1 check` (원격이 앞설 때만 pull). 키를 바꿨으면 `push`.

## 우선순위

1. 사용자 요청  
2. 그중 **가장 최신** 요청  
3. 데드라인 / 막힘 / 버그  

Must = 지금 안 하면 막히거나, 데드라인이거나, 버그이거나, **사용자 요청**인 것.

## 하다 만 작업

브랜치 유지 + 이 파일에 체크포인트 한 줄 (`어디까지 했는지`). 기본 브랜치에 미완성 커밋 금지.

## 최종 보고 최소 항목

```text
REPO: (origin URL)
SHA: (구현 커밋)
CMD: (테스트/smoke 명령)
SMOKE: (산출물 경로 또는 N/A 이유)
TEST: (요약 원문 10줄 이내 붙여넣기)
DIFF: (구현 파일 목록 — 테스트만이면 FAIL)
STATUS: DONE | BLOCKED_WITH_EVIDENCE | FAIL
```

<!-- END OPS HEADER -->

---

# CURRENT TASK

현재 등록된 과업 없음.



과업이 없으면 `NO_ACTIVE_TASK`만 보고하고 **즉시 중단**한다.
다른 레포 TASK/NEXT_TASK/채팅 과업을 가져오지 않는다.
기본 브랜치(`main`)에서 직접 개발·병합 금지. 이 TASK가 머지를 명시하지 않으면 push/PR까지만.
