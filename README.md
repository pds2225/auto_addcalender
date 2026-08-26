# AI 일정 자동 등록

복사한 안내문, 문자, 공지글을 붙여넣으면 AI가 일정을 찾아서 캘린더에 등록할 수 있게 정리해 주는 웹 앱입니다.

GitHub 저장소: https://github.com/pds2225/auto_addcalender

## 지금 가능한 기능

### 1. 안내문에서 일정 자동 추출

긴 안내문을 그대로 붙여넣으면 AI가 아래 정보를 찾아냅니다.

- 일정 제목
- 시작 날짜와 시간
- 종료 날짜와 시간
- 장소
- 참석자에게 필요한 메모
- 캘린더에 넣기 좋은 짧은 메모

예시로 교육 안내문, 행사 공지, 지원사업 일정, 회의 안내문 같은 텍스트를 넣을 수 있습니다.

### 2. 구글 캘린더 바로 등록

추출된 일정마다 `구글 등록` 버튼이 표시됩니다.

버튼을 누르면 구글 캘린더 등록 화면이 열리고, 일정 제목/시간/장소/메모가 자동으로 들어갑니다.

현재는 모바일에서도 기본 캘린더인 `내 캘린더`에 등록되도록 `calid=primary` 방식을 사용합니다.

### 3. 카카오 캘린더용 파일 다운로드

구글 캘린더 대신 카카오 캘린더에 넣고 싶을 때 `.ics` 파일을 받을 수 있습니다.

사용 방법:

1. 캘린더 선택에서 `카카오 캘린더(.ics)`를 선택합니다.
2. 일정별 `카카오 등록(.ics)` 버튼을 누릅니다.
3. 내려받은 `.ics` 파일을 카카오 캘린더 또는 휴대폰 캘린더 앱에서 가져옵니다.

### 4. 여러 날짜 일정 자동 분리

2일 이상 이어지는 일정은 날짜별 일정으로 나누어 보여줍니다.

예시:

```text
2026-05-01 09:00 ~ 2026-05-03 18:00 교육
```

처리 결과:

```text
2026-05-01 교육
2026-05-02 교육
2026-05-03 교육
```

이렇게 분리되면 캘린더에서 날짜별로 확인하기 쉽습니다.

### 5. 날짜 범위 자동 보정

사람이 자주 쓰는 짧은 날짜 표기도 AI가 이해하기 쉽게 보정합니다.

예시:

```text
05-01~03
```

보정 결과:

```text
05-01~05-03
```

### 6. 일정 공유 문구 만들기

추출된 일정 중 공유할 항목을 체크한 뒤 `카카오톡 공유하기`를 누르면 공유용 문구가 만들어집니다.

브라우저에서 바로 공유가 안 되는 경우에는 자동으로 복사 모드로 전환됩니다.

## 실행 전 준비

- Python 3.11 이상이 설치되어 있어야 합니다.
- OpenAI API Key가 필요합니다.
- Windows PowerShell 기준으로 실행하면 됩니다.

## 설치 방법

PowerShell에서 프로젝트 폴더로 이동합니다.

```powershell
cd D:\auto_addcalender
```

필요한 라이브러리를 설치합니다.

```powershell
pip install -r requirements.txt
```

## OpenAI API Key 설정

Streamlit Cloud에서는 `.streamlit/secrets.toml`에 아래처럼 저장합니다.

```toml
OPENAI_API_KEY = "sk-..."
```

로컬 실행에서도 Streamlit secrets 설정이 필요합니다.

## 실행 방법

```powershell
streamlit run app.py
```

실행 후 브라우저에서 아래 주소를 엽니다.

```text
http://localhost:8501
```

## 사용 방법

1. 앱 화면의 입력창에 일정 안내문을 붙여넣습니다.
2. `일정등록` 버튼을 누릅니다.
3. AI가 추출한 일정 목록을 확인합니다.
4. 구글 캘린더 또는 카카오 캘린더 방식을 선택합니다.
5. 일정이 여러 개면 원하는 일정만 체크한 뒤 `선택 일괄 열기`를 누릅니다. 구글 캘린더 탭은 브라우저가 멈추지 않도록 짧은 간격으로 순서대로 열립니다. 개별 등록도 가능합니다.
6. 필요하면 공유할 일정을 선택해 카카오톡 공유 문구를 복사합니다.

## 현재 파일 구성

```text
auto_addcalender/
├── app.py                  # Streamlit 메인 앱
├── bulk_open.py            # 선택 일괄 열기(구글 캘린더 탭) UI
├── date_utils.py           # 날짜 범위 보정 기능
├── requirements.txt        # 설치할 라이브러리 목록
├── README.md               # 비개발자용 사용 설명서
├── TASKS.md                # 작업 현황
├── AGENTS.md               # 자동 개발 에이전트 역할 정의
├── CLAUDE.md               # Claude 작업 규칙
└── .github/workflows/ci.yml # GitHub Actions 기본 검증
```

## 현재 검증된 내용

아래 검증은 로컬에서 통과했습니다.

```powershell
python -m py_compile app.py date_utils.py
```

```powershell
python -c "from date_utils import normalize_date_ranges; result=normalize_date_ranges('2026-05-01~03'); assert '2026-05-01' in result and '2026-05-03' in result; print(result)"
```

## 아직 확인이 필요한 내용

- Streamlit Cloud 배포 설정 확인
- 모바일에서 구글 캘린더 `내 캘린더` 등록 동작 실기기 확인
- 카카오 캘린더 `.ics` 파일의 한글 인코딩 확인
- 날짜 보정 기능의 추가 테스트 파일 작성

## 개발 메모

- 메인 브랜치: `main`
- 작업 브랜치 규칙: `main_auto_addcalender_MMDD`
- 저장소 주소: https://github.com/pds2225/auto_addcalender
