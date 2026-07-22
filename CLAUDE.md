# NOVELDESK — 소설 반복 표현 탐지 파이프라인

## 프로젝트 목적

장편소설 전체에 걸쳐 **반복되는 표현과 AI 글쓰기 패턴**을 자동으로 찾아내고,
Claude API를 통해 진단 및 대안을 제안받는 파이프라인이다.

단 하나의 챕터가 아니라 **책 전체에 걸쳐 반복되는 습관적 패턴**을 잡는 것이 목표다.
탐지는 코드가 하고, 고칠지 말지 판단은 항상 작가가 직접 한다.

---

## 폴더 구조

```
engine/      — 분석 코드 (step1~8, viewer 도구). 소설 이름이 박혀있지 않은 범용 코드.
projects/    — 소설별 데이터와 결과물. 소설마다 하나의 폴더.
  └ 우도/
      all_chapters/        — 전체 챕터 .txt
      sample_chapters/     — 테스트용 일부 챕터
      story_bible/         — characters.json, world.json 등 세계관 설정
      36화TOTAL.docx 등 원본/리포트 파일들
```

`engine/`의 모든 스크립트는 `--project <소설이름>` 인자를 받아서
`projects/<소설이름>/` 폴더를 기준으로 입력 챕터를 읽고 출력 리포트를 저장한다.
새 소설을 추가할 때 `engine/` 코드는 건드릴 필요가 없다 — 아래 "새 소설 시작하기" 참고.

---

## 파이프라인 구조와 실행 순서

모든 명령은 `engine/` 폴더 안에서 실행한다 (`cd engine`).

### Step 1 — 단일 챕터 빈도 분석 (`step1_frequency_check.py`)

단일 `.txt` 파일 하나를 받아서 6가지 반복 패턴을 출력한다.

- **[A]** 4~10어절 n-gram 반복 구문 (형태소 분석 없이 공백 기준으로 쪼갬)
- **[B]** AI 글쓰기 의심 종결어/단어 (`듯했다`, `것 같았다`, `문득`, `공허` 등)
- **[C]** 접속·대조 구조 (`지만`, `그러나`, `하지만` 등 — 단조로운 리듬의 주범)
- **[D]** 묘사 클리셰 (`텅 빈`, `공허한`, `짙은 어둠` 등 수식 조합)
- **[E]** 대화 서술동사 (`말했다`, `외쳤다`, `쏘아붙였다` 등)
- **[F]** 행동 묘사 클리셰 2~3어절 n-gram (`발길을 재촉했다` 류)

```
python step1_frequency_check.py --project 우도
# 또는 파일 경로를 직접 지정
python step1_frequency_check.py ../projects/우도/sample_chapters/제1화.txt
```

step1은 단독으로 빠르게 감을 잡을 때 쓴다. step2~4는 이 파일의 함수를 `import`해서 재사용한다.

---

### Step 2 — 챕터 간 비교 (`step2_cross_chapter.py`)

폴더 안의 모든 `.txt` 챕터에 step1 탐지 함수를 적용한 뒤,
**"1개 챕터에만 나온 표현"과 "2개 이상 챕터에 걸쳐 나온 표현"을 구분**해서 출력한다.
2개 이상 챕터에 걸친 표현이 진짜 책 전체의 습관성 패턴이다.

```
python step2_cross_chapter.py --project 우도
# 기본값: projects/<이름>/sample_chapters 폴더
```

---

### Step 3 — 문맥 리포트 생성 (`step3_context_report.py`)

숫자만으로는 고칠지 말지 판단할 수 없다.
2개 이상 챕터에서 발견된 표현 각각에 대해, **그 표현이 들어간 실제 문장을 챕터별로 모아서 마크다운으로 저장**한다.

```
python step3_context_report.py --project 우도
# 출력: projects/우도/context_report.md
```

---

### Step 4 — Claude API 자동 제안 (`step4_api_suggestions.py`) ← 핵심 단계

step1~3를 모두 통합한 최종 단계. **Claude API를 호출**해서 각 반복 표현에 대해 진단과 대안을 자동 생성하고 마크다운 리포트로 저장한다.

동작 방식:
- 챕터 수에 비례해 기준을 자동 조정 (챕터 수 // 9 이상의 챕터에 등장한 것만 채택)
- 짧은 n-gram이 긴 n-gram에 포함되면 중복 제거
- 표현 + 등장 문장을 한 번에 묶어서 API로 전송 (맥락 없이 문장 하나씩 보내지 않음)
- 결과: `projects/<이름>/api_suggestions_report.md`

```
python step4_api_suggestions.py --project 우도
```

---

## 실행 전 준비

### 패키지 설치

```
pip install anthropic python-dotenv
```

### API 키 설정 (`.env` 파일)

프로젝트 루트(`NOVELDESK/`)의 `.env` 파일에 다음 한 줄만 작성한다:

```
ANTHROPIC_API_KEY=sk-ant-여기에본인키
```

**주의사항:**
- API 키를 `.py` 코드 안에 직접 쓰지 않는다. 키가 GitHub 등에 올라가면 즉시 노출된다.
- `.env` 파일은 `.gitignore`에 이미 등록되어 있어 git에서 자동 제외된다.
- Windows 메모장으로 `.env` 저장 시 UTF-8 BOM 문제가 생길 수 있다. VS Code나 Notepad++로 저장하거나, 이미 step4가 BOM 자동 제거를 처리하므로 대부분 자동 해결된다.
- 키 앞뒤 공백이나 따옴표가 들어가지 않도록 주의한다.

---

### Step 5 — 계급 진급 체크 (`step5_consistency_check.py`)

step1~4와 독립적으로 실행하는 일관성 검사 도구. **API 호출 없음.**

배경 규칙:
- "성씨+계급" 형태로 인물을 지칭하는 소설에서, 계급 순서가 챕터 진행상 역행하는지 본다 (예: `편일경`, `마수경`).
- 계급 순서 자체은 소설마다 다르므로 코드에 하드코딩하지 않고, **`projects/<이름>/story_bible/world.json`의 `rank_system.order`**에서 읽어온다.
  - 예: `"rank_system": { "order": ["이경", "일경", "상경", "수경"] }`
- `world.json`에 `rank_system`이 없으면(계급 체계가 없는 소설) 이 체크는 자동으로 건너뛴다.
- 챕터 번호 = 시간 순서 (1화가 가장 과거)

동작 방식:
- 전체 챕터에서 `성씨+계급` 패턴을 정규식으로 자동 추출
- 성씨별 계급 타임라인 구성
- 챕터 순서상 계급이 역행하는 후보를 "검토 필요"로 표시
- 동일 챕터 내 복수 계급(진급 장면 또는 오류)도 별도 목록 제공

```
python step5_consistency_check.py --project 우도
# 출력: projects/우도/rank_check_report.md
```

출력 구조:
1. **검토 필요 — 계급 역행 후보**: 앞 챕터보다 낮은 계급이 뒤에 등장한 사례 + 해당 문장
2. **인물별 계급 타임라인**: 전체 흐름을 화수 순으로 한눈에
3. **참고 — 동일 챕터 내 복수 계급**: 진급 장면이거나 오류일 수 있는 경우

---

### Step 6 — 전반부 떡밥 탐지 (`step6_foreshadowing_check.py`)

전반부(기본 1~18화)를 한 번에 Claude API에 보내서, 나중에 회수될 것 같은 설정/암시/약속(떡밥) 목록을 뽑는다.
실행 전 예상 토큰/비용을 보여주고 `y/n` 확인을 받는다.

```
python step6_foreshadowing_check.py --project 우도
python step6_foreshadowing_check.py --project 우도 --start 1 --end 18 --yes
# 출력: projects/우도/foreshadowing_part1_1-18.md
```

---

### Step 7 — 떡밥 회수 체크 (`step7_foreshadowing_resolution.py`)

step6이 찾은 떡밥 목록을 후반부(기본 19~36화) 본문과 함께 API에 보내서, 실제로 회수됐는지 판정받는다.

```
python step7_foreshadowing_resolution.py --project 우도
# 출력: projects/우도/foreshadowing_unresolved.md
```

---

### Step 7 — 페이싱(속도감) 체크 (`step7_pacing_check.py`)

step1~6와 독립적으로 실행하는 일관성 검사 도구. **API 호출 없음.**
(`step7_foreshadowing_resolution.py`와는 별개의 도구이며, 둘 다 "step7"이라는 번호를 쓰고 있어 헷갈리지 않게 파일명으로 구분한다.)

측정 지표 4가지 (챕터별):
- 글자수(공백 제외)
- 문장 평균 길이 + 표준편차
- 대화 비중 (큰따옴표 안 글자수 / 전체 글자수)
- 장면 전환 횟수 (`____` 구분선 개수)

각 지표가 전체 평균의 1.5배 이상이거나 0.67배 이하면 ⚠️로 표시한다.
표시는 "다시 읽어볼 만한 챕터" 힌트일 뿐, 늘어지는지 의도된 리듬인지는 작가가 판단한다.

```
python step7_pacing_check.py --project 우도
# 출력: projects/우도/pacing_report.md, pacing_chart.png (4개 지표 그래프)
```

---

### Step 8 — 페이싱 이상 챕터에 대한 Claude 판단 (`step8_pacing_api_check.py`)

step7이 숫자로 골라낸 ⚠️ 챕터에 대해서만 Claude API로 판단을 한 번 더 받는다.

비용 절감 설계:
- 전체 챕터가 아니라 step7에서 ⚠️ 표시된 챕터만 API로 전송 (step7 함수 재사용, 계산 중복 없음)
- 실행 전 "몇 개 챕터, API 호출 몇 번 예상"을 보여주고 `y/n` 확인을 받은 뒤 진행
- `--yes`로 확인 생략, 숫자 인자로 이상 신호가 가장 뚜렷한 N개만 먼저 테스트 가능

```
python step8_pacing_api_check.py --project 우도
# 출력: projects/우도/pacing_api_report.md (확인 후 진행)

# 가장 뚜렷한 3개 챕터만 먼저 테스트
python step8_pacing_api_check.py --project 우도 3
# 출력: projects/우도/pacing_api_report_sample3.md

# 확인 없이 바로 실행
python step8_pacing_api_check.py --project 우도 --yes
```

챕터마다 "기계적 신호 → Claude 판단 → 구체적 제안" 순으로 리포트에 정리된다.
Claude는 해당 챕터가 실제로 늘어지는지 / 의도된 장면(회상, 정보 전달 등)인지 진단하고,
늘어진다면 구체적으로 어느 부분을 줄이거나 어떤 장면을 추가할지 제안한다.

---

## 보조 도구 — 반복 표현 리포트 뷰어 (`viewer_build_data.py`, `viewer_render_html.py`)

분석 파이프라인의 "다음 단계"가 아니라, **step4 결과물(`api_suggestions_report.md`)을
검색·필터 가능한 HTML로 바꿔주는 별도 도구**다 (그래서 step 번호가 없다).

```
python viewer_build_data.py --project 우도     # api_suggestions_report.md → report_data.json
python viewer_render_html.py --project 우도    # report_data.json → report_viewer.html
```

`report_viewer.html`은 인터넷 연결 없이 더블클릭으로 열리는 단일 파일이며,
표현 검색, 펼치기/접기, 원문→대안 클립보드 복사 기능을 제공한다.

---

## 새 소설 시작하기

새 소설을 분석하려면 **`engine/` 코드는 손대지 않고, `projects/` 안에 새 폴더만 만들면 된다.**

1. `projects/<새소설이름>/` 폴더를 만든다.
2. 그 안에 `all_chapters/` 폴더를 만들고 챕터 `.txt` 파일을 넣는다 (파일명은 `제N화`라는 표시만 들어가면 형식 무관, 예: `제1화.txt`, `소설명_제1화.txt` 모두 가능).
3. (선택) 일부 챕터로만 빠르게 테스트하고 싶으면 `sample_chapters/` 폴더도 만든다.
4. (선택) 계급/직급처럼 순서가 있는 호칭 체계가 있으면 `story_bible/world.json`을 만들고 `rank_system.order`에 순서대로 적는다. 없으면 step5는 자동으로 건너뛴다.
5. `engine/` 폴더에서 `--project <새소설이름>`을 붙여 원하는 step을 실행한다:

```
cd engine
python step4_api_suggestions.py --project 새소설이름
```

모든 입력은 `projects/<새소설이름>/`에서 읽고, 모든 출력도 그 폴더 안에 쌓인다.

---

## 탐지 패턴 커스터마이징

`engine/step1_frequency_check.py` 안의 패턴 목록을 직접 수정하면 된다:

- `find_repeated_endings()` — AI 의심 종결어 목록
- `find_descriptive_cliches()` — 묘사 클리셰 목록
- `find_narration_verbs()` — 대화 서술동사 목록

이 패턴들은 모든 소설에 공통으로 적용된다. 특정 소설에서만 자주 쓰는 표현이 있으면
여기 추가하기보다, 해당 프로젝트에서 결과를 보고 따로 메모해두는 쪽을 권한다.
