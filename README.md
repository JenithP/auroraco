# Aurora 쇼핑몰 (연구용)

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

## 보안 규칙 배포 (사람이 할 일)

규칙은 [`database.rules.json`](database.rules.json): 읽기 전부 금지, `events`/`beacon`에 새 항목 추가만 허용(수정·삭제 금지), 타입·길이·조건값 검증.

```bash
npm install -g firebase-tools
firebase login
firebase deploy --only database
```

> ⚠️ 2026-10-21 확인 시점에 DB가 **누구나 읽을 수 있는 상태**(테스트 모드)였다. 파일럿 전에 반드시 위 명령으로 규칙을 배포한다.

## 서비스 계정 키

- 서비스 계정 키(JSON)는 DB 전체를 읽고 지울 수 있는 관리자 키다. **저장소에 두지 않는다**(`.gitignore`로 막혀 있음).
- 저장소 밖(예: `~/.secrets/aurora-sa.json`)에 두고, 내보내기 스크립트는 환경변수로 경로를 받는다.

```bash
export GOOGLE_APPLICATION_CREDENTIALS=~/.secrets/aurora-sa.json
```

- 브라우저 코드에는 절대 넣지 않는다.

## 브라우저 API 키 제한 (사람이 할 일)

Google Cloud 콘솔 → API 및 서비스 → 사용자 인증 정보 → 브라우저 키(`AIzaSyDhUg2…`) → 애플리케이션 제한사항 → **HTTP 리퍼러** → `https://auroraco.netlify.app/*`(와 데모 도메인)만 허용.
