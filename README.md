# Aurora 쇼핑몰 (연구용)

> **Prolific·Qualtrics 담당자는 [PROLIFIC_SETUP.md](PROLIFIC_SETUP.md)만 보면 된다.**

Prolific 참가자 대상 연구용 쇼핑몰. 정적 HTML(`index.html`)이고 GitHub `main`에 push하면 Netlify(auroraco.netlify.app)에 바로 배포된다. **main push = 진행 중인 실험에 즉시 반영**이므로 작업은 브랜치에서 한다.

## 접속 URL

```
https://auroraco.netlify.app/?c=se&a=sm&PROLIFIC_PID={{%PROLIFIC_PID%}}&STUDY_ID={{%STUDY_ID%}}&SESSION_ID={{%SESSION_ID%}}
```

| 파라미터 | 값 | 의미 |
|---|---|---|
| `c` | `nm` / `se` / `dl` | errorType: normal / sumerror / delay (없으면 normal) |
| `a` | `ne` / `sm` / `em` | 아바타: neutral / smile / empathic (없으면 ne) |
| `PROLIFIC_PID`, `STUDY_ID`, `SESSION_ID` | Prolific 값 | 모든 로그에 붙는다. 새로고침해도 sessionStorage로 유지 |
| `demo=1` | | 데모 세션. Firebase `studyKey`가 `demo`로 분리됨 |
| `sk=loadtest_YYYYMMDD` | | 부하 테스트용 `studyKey` |

## 로깅

`pushLog(type, detail)` 한 곳에서 두 군데로 보낸다. 설정은 [`firebase-config.js`](firebase-config.js) 한 곳에서 바꾼다.

- `STUDY_KEY`: 실험 차수 (`/aurora_logs/{STUDY_KEY}/...`)
- `LOG_TO_APPS_SCRIPT`: 기존 Google Sheets 기록. 파일럿에서 Firebase 유실률 0%를 확인한 뒤 `false`로 끈다.
- `LOG_TO_FIREBASE`: Firebase Realtime Database 기록

Firebase 데이터 구조:

```
/aurora_logs/{studyKey}/{pid}/meta             조건·세션·UA (필드별 1회만 기록)
/aurora_logs/{studyKey}/{pid}/events/{pushId}  이벤트 1건
/aurora_logs/{studyKey}/{pid}/beacon/{pushId}  페이지 이탈 시 sendBeacon으로 보낸 미확인 이벤트 배열
```

- 이벤트마다 `seq`(세션 내 0부터 증가)가 붙는다. 번호가 비면 그 사이 이벤트가 유실된 것이다.
- 쓰기 실패 시 지수 백오프로 최대 5회 재시도한다.
- `PAYMENT_ATTEMPT`/`PAYMENT_SUCCESS`/`CHATBOT_ISSUE_RESOLVED`는 저장 확인 후(최대 3초) 주문 코드를 보여준다.
- `pagehide`/`visibilitychange(hidden)` 시 아직 확인 못 받은 이벤트를 `beacon`으로 보내고, 페이지를 떠날 때 `SESSION_END`를 남긴다.
- `events`와 `beacon`에 같은 이벤트가 둘 다 있을 수 있으니 분석 시 `(pid, sessionId, seq)`로 중복을 제거한다.
- 이벤트 타입 허용 목록은 `index.html`의 `ALLOWED_TYPES`와 `database.rules.json` 두 곳에 있다. 바꿀 때는 둘 다 바꾼다.

## Qualtrics 연결 체크리스트 (사람이 할 일)

9·10월 설문은 Prolific ID를 텍스트 문항(Q5 "What is your prolific ID?")으로 받았고, 쇼핑몰 링크에는 ID가 없었다. 이번부터는 URL로 자동 전달한다.

- [ ] **Survey Flow 맨 위에 Embedded Data**로 `PROLIFIC_PID`, `STUDY_ID`, `SESSION_ID`를 추가한다(값은 비워 두면 Prolific 링크의 URL 파라미터에서 자동으로 채워진다).
- [ ] Prolific 스터디 URL이 `?PROLIFIC_PID={{%PROLIFIC_PID%}}&STUDY_ID={{%STUDY_ID%}}&SESSION_ID={{%SESSION_ID%}}`를 포함하는지 확인한다.
- [ ] Qualtrics에서 Aurora로 보내는 링크에 ID를 붙인다. 기존 조건 파라미터(`c`, `a`)는 그대로 둔다.
  ```
  https://auroraco.netlify.app/?c=se&a=sm&PROLIFIC_PID=${e://Field/PROLIFIC_PID}&STUDY_ID=${e://Field/STUDY_ID}&SESSION_ID=${e://Field/SESSION_ID}
  ```
- [ ] 미리보기로 링크를 열어 보고, Firebase `meta`의 `pidStatus`가 `valid`인지 확인한다(`missing`이면 Embedded Data가 비어 있는 것).
- [ ] 주문 코드 입력 문항(조건별 Q54/Q89/Q95/Q66 등)에 **Validation → Custom → Matches Regex**를 건다.
  ```
  ^\s*(AC-)?M[A-Z0-9]{7}-[A-Z0-9]{4}\s*$
  ```
  > 코드 가운데 부분은 생성 시각(`Date.now()`의 36진수)이라 **2027년 2월 중순부터 첫 글자가 `M`에서 `N`으로 바뀐다.** 그 이후까지 수집한다면 `^\s*(AC-)?[A-Z0-9]{8}-[A-Z0-9]{4}\s*$`를 쓴다.
- [ ] 기존 문항 **뒤에**(revenge·NWOM 문항보다 뒤, 기존 데이터와 비교할 수 있도록) 다음 문항을 추가한다. 척도는 기존 챗봇 문항과 같은 것을 쓴다.
  - The chatbot did not seem to take my problem seriously.
  - The chatbot's facial expression was inappropriate for the situation.
  - The chatbot's expression seemed insincere.
  - The chatbot seemed competent.
- [ ] Q5(Prolific ID 텍스트 문항)는 비교를 위해 남겨 두되, 분석은 Embedded Data `PROLIFIC_PID`를 기준으로 한다.

## 로그 내보내기·유실 검증

```bash
pip install -r requirements.txt
export GOOGLE_APPLICATION_CREDENTIALS=~/.secrets/aurora-sa.json

# 1) Firebase → CSV (이벤트 1행 = 1줄, events/beacon 중복 제거)
python scripts/export_logs.py --study-key 2026-11_replication --out logs.csv

# 2) 로그 CSV + Qualtrics 원본 CSV → 유실 지표
python scripts/check_loss.py logs.csv --survey "qualtrics_export.csv"
```

- `export_logs.py`는 `--from-json`으로 Firebase 콘솔에서 받은 JSON 파일을 읽을 수도 있다(서비스 계정 키 없이).
- `check_loss.py`는 Qualtrics 3줄 헤더 형식을 그대로 읽는다. Prolific ID 열은 `PROLIFIC_PID`(Embedded Data) → "prolific id" 문항 순으로, 주문 코드 열은 "enter the code" 문항 전체를 자동으로 찾는다. 다르면 `--pid-col`, `--code-col`(여러 번 가능)로 지정한다.
- 설문 코드는 앞뒤 공백·소문자·`AC-` 누락을 바로잡은 뒤 비교한다.
- `--survey` 없이 실행하면 로그 쪽 지표(seq 누락, `SESSION_END` 누락)만 본다. `--strict`를 주면 seq 누락이 하나라도 있을 때 종료 코드 1로 끝난다(부하 테스트용).

## 보안 규칙 배포 (사람이 할 일)

규칙은 [`database.rules.json`](database.rules.json): 읽기 전부 금지, `events`/`beacon`에 새 항목 추가만 허용(수정·삭제 금지), 타입·길이·조건값 검증.

```bash
npm install -g firebase-tools
firebase login
firebase deploy --only database
```

> 2026-10-21 배포 완료. 규칙을 바꾸면 위 명령으로 다시 배포한다(이 저장소 폴더에서 실행해야 `database.rules.json`이 올라간다).
> 현재 적용된 규칙 확인: `firebase database:get /.settings/rules` (Git Bash에서는 앞에 `MSYS_NO_PATHCONV=1`)

## 서비스 계정 키

- 서비스 계정 키(JSON)는 DB 전체를 읽고 지울 수 있는 관리자 키다. **저장소에 두지 않는다**(`.gitignore`로 막혀 있음).
- 저장소 밖(예: `~/.secrets/aurora-sa.json`)에 두고, 내보내기 스크립트는 환경변수로 경로를 받는다.

```bash
export GOOGLE_APPLICATION_CREDENTIALS=~/.secrets/aurora-sa.json
```

- 브라우저 코드에는 절대 넣지 않는다.

## 브라우저 API 키 제한 (사람이 할 일)

Google Cloud 콘솔 → API 및 서비스 → 사용자 인증 정보 → 브라우저 키(`AIzaSyDhUg2…`) → 애플리케이션 제한사항 → **HTTP 리퍼러** → `https://auroraco.netlify.app/*`(와 데모 도메인)만 허용.
