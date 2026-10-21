# Aurora 실험 진행 안내 (Prolific · Qualtrics 담당자용)

이 문서만 보고 파일럿과 본실험을 열 수 있도록 정리했다. 코드는 건드릴 필요가 없다.
막히는 곳이 있으면 마지막 **문제가 생기면** 절을 먼저 본다.

---

## 0. 한눈에 보기

```
Prolific  ──(PROLIFIC_PID 등 자동 전달)──▶  Qualtrics 설문
                                             │  쇼핑몰 링크 클릭 (PID를 링크에 붙여서)
                                             ▼
                                        Aurora 쇼핑몰  ── 행동 로그 자동 저장 (Firebase)
                                             │  결제 후 주문 코드(AC-…) 표시
                                             ▼
                                        Qualtrics로 돌아와 코드 입력 → 나머지 문항
                                             │
                                             ▼
                                        Prolific 완료 코드로 복귀
```

- 참가자 화면, 상품, 가격, 챗봇 대사, 아바타는 9·10월과 **똑같다.** 달라진 건 로그 저장 방식과 주문 코드 옆 **Copy** 버튼뿐이다.
- 로그는 **Prolific ID 기준**으로 설문과 1:1로 이어진다. 그래서 Prolific ID가 링크를 타고 쇼핑몰까지 전달되는 것이 이번 설정의 핵심이다.

## 1. 실험 조건과 쇼핑몰 링크

본실험 설계: **outcome failure(정상 / 결제 금액 10배 오류) × 챗봇 아바타(Neutral / Smile)**, 4개 집단.

| 집단 | 결제 | 아바타 | 쇼핑몰 링크 (Qualtrics에 넣는 그대로) |
|---|---|---|---|
| A | 정상 | Neutral | `https://auroraco.netlify.app/?c=nm&a=ne&PROLIFIC_PID=${e://Field/PROLIFIC_PID}&STUDY_ID=${e://Field/STUDY_ID}&SESSION_ID=${e://Field/SESSION_ID}` |
| B | 정상 | Smile | `https://auroraco.netlify.app/?c=nm&a=sm&PROLIFIC_PID=${e://Field/PROLIFIC_PID}&STUDY_ID=${e://Field/STUDY_ID}&SESSION_ID=${e://Field/SESSION_ID}` |
| C | 10배 오류 | Neutral | `https://auroraco.netlify.app/?c=se&a=ne&PROLIFIC_PID=${e://Field/PROLIFIC_PID}&STUDY_ID=${e://Field/STUDY_ID}&SESSION_ID=${e://Field/SESSION_ID}` |
| D | 10배 오류 | Smile | `https://auroraco.netlify.app/?c=se&a=sm&PROLIFIC_PID=${e://Field/PROLIFIC_PID}&STUDY_ID=${e://Field/STUDY_ID}&SESSION_ID=${e://Field/SESSION_ID}` |

- `c`는 결제 조건(`nm` 정상, `se` 10배 오류), `a`는 아바타(`ne` Neutral, `sm` Smile)다. **이 두 값은 바꾸지 않는다.**
- `${e://Field/…}` 부분은 Qualtrics가 참가자마다 실제 값으로 바꿔 넣는다. 글자 그대로 복사해 넣는다.

## 2. Prolific 설정

1. **Study URL**에 Qualtrics 설문 링크를 넣는다.
2. *How do you want to record Prolific IDs?* → **I'll use URL parameters** 를 고른다.
   저장 후 Study URL 끝에 아래가 붙어 있는지 확인한다(Prolific이 자동으로 붙인다).
   ```
   ?PROLIFIC_PID={{%PROLIFIC_PID%}}&STUDY_ID={{%STUDY_ID%}}&SESSION_ID={{%SESSION_ID%}}
   ```
3. **완료 코드**: 기존과 같이 Qualtrics 마지막 화면에서 Prolific 완료 URL로 돌아가게 둔다.
4. **9·10월 참가자 제외**: *Participants → Screeners → Previous studies* 에서 9월·10월 Aurora 스터디를 **Exclude**로 건다.
5. 기기·국가 등 나머지 조건은 9·10월 스터디와 똑같이 맞춘다(재현 실험이라 중요하다).

## 3. Qualtrics 설정

### 3-1. Prolific ID 받기 (가장 중요)
**Survey Flow** 맨 위(첫 블록보다 위)에 **Embedded Data** 요소를 추가하고 필드 세 개를 만든다. 값은 비워 둔다.

```
PROLIFIC_PID
STUDY_ID
SESSION_ID
```

값을 비워 두면 Prolific 링크의 URL 파라미터에서 자동으로 채워진다. 철자·대소문자가 정확히 같아야 한다.

### 3-2. 쇼핑몰 링크
- 집단 배정은 기존처럼 **Randomizer**(Evenly Present Elements)로 한다.
- 각 집단 블록의 쇼핑몰 링크를 **1절 표의 링크로 교체**한다. 기존 링크에는 Prolific ID가 없어서, 9·10월에는 로그와 설문을 이을 수 없었다.
- 링크는 기존과 같이 새 탭으로 열리게 둔다(참가자가 설문 탭으로 돌아와 코드를 입력해야 한다).

### 3-3. 주문 코드 문항
주문 코드 입력 문항(집단별로 하나씩) 모두에 **Add Validation → Custom Validation → Matches Regex**:

```
^\s*(AC-)?M[A-Z0-9]{7}-[A-Z0-9]{4}\s*$
```

오류 메시지 예: `Please paste the order code shown by the chatbot (e.g. AC-MXXXXXXX-XXXX).`
9·10월에는 `NOCODE`, `0000`, 챗봇 문장 전체를 붙여넣은 응답이 많았다. 이번엔 쇼핑몰에 **Copy** 버튼이 있으니 안내 문구에 "Copy 버튼을 눌러 붙여넣으세요"를 넣으면 좋다.

> 이 정규식은 **2027년 2월 중순 이후** 생성되는 코드는 거부한다(코드 첫 글자가 M → N으로 바뀜). 그 이후에도 모집한다면 `^\s*(AC-)?[A-Z0-9]{8}-[A-Z0-9]{4}\s*$`로 바꾼다.

### 3-4. 추가 문항
기존 문항 **뒤**, revenge·NWOM 문항보다 **뒤**에 아래 4문항을 추가한다(기존 데이터와 비교하기 위해 순서가 중요하다). 척도는 기존 챗봇 문항과 같은 것을 쓴다.

- The chatbot did not seem to take my problem seriously.
- The chatbot's facial expression was inappropriate for the situation.
- The chatbot's expression seemed insincere.
- The chatbot seemed competent.

기존 Q5("What is your prolific ID?")는 지우지 말고 둔다(비교용).

## 4. 공개 전 직접 테스트 (10분)

1. Qualtrics **Preview**로 설문을 열되, 주소 끝에 가짜 ID를 붙인다.
   ```
   <Qualtrics 설문 링크>?PROLIFIC_PID=test_본인이름&STUDY_ID=test&SESSION_ID=test
   ```
   `test_`로 시작하는 ID는 분석에서 자동으로 걸러진다.
2. 쇼핑몰 링크를 눌렀을 때 주소창에 `PROLIFIC_PID=test_본인이름`이 보이는지 확인한다.
   → `PROLIFIC_PID=` 뒤가 비어 있으면 3-1(Embedded Data) 설정이 잘못된 것이다.
3. 상품을 담고 결제 → 챗봇 → 코드 확인까지 진행하고, **Copy** 버튼으로 코드를 복사해 설문에 붙여넣는다.
4. 집단 4개를 모두 한 번씩 확인한다(Randomizer 때문에 여러 번 열어야 할 수 있다).
   - 10배 오류 집단(C·D): 결제 후 금액이 10배로 빠지고, 챗봇이 뜨고, "Okay, understood"를 누르면 코드가 나온다.
   - 정상 집단(A·B): 결제 직후 챗봇이 코드를 보여준다.
5. 테스트에 쓴 `test_…` ID를 연구자에게 알려 로그가 들어왔는지 확인받는다.

## 5. 파일럿 → 본실험

1. **파일럿**: 30명을 **한 번에** 공개한다(동시 접속에서 유실이 없는지 보는 게 목적이다).
2. 연구자가 로그와 설문을 대조한다(`scripts/check_loss.py`). 기준: **로그 매칭률 100%, seq 누락 0, 결제 코드 누락 0**.
3. 기준을 통과하면 **본실험**: 집단당 약 200명. 하루에 몰지 말고 며칠에 나눠 연다.
4. 파일럿과 본실험 사이에 쇼핑몰 쪽 설정(로그 이중 기록 끄기)을 연구자가 바꿀 수 있다. 링크와 설문은 그대로 쓴다.

## 6. 문제가 생기면

| 증상 | 확인할 것 |
|---|---|
| 쇼핑몰 주소에 `PROLIFIC_PID=`가 비어 있음 | Survey Flow 맨 위 Embedded Data 철자, Prolific Study URL에 파라미터가 붙어 있는지 |
| 주소에 `${e://Field/PROLIFIC_PID}`가 글자 그대로 보임 | Qualtrics 링크를 HTML/Rich Content가 아닌 일반 텍스트 편집기에서 넣었는지, 필드 이름 철자 |
| 참가자가 "코드가 안 나와요" | 10배 오류 집단은 챗봇에서 **Okay, understood**까지 눌러야 코드가 나온다 |
| 참가자가 새로고침함 | 괜찮다. 같은 탭이면 ID·세션이 유지된다(장바구니는 비워진다) |
| 코드 입력이 계속 거부됨 | 3-3 정규식 오타, 참가자가 공백·문장 전체를 넣었는지 (Copy 버튼 안내) |

연구자 연락 시 **참가자 Prolific ID와 대략의 시각**을 함께 알려주면 로그를 바로 찾을 수 있다.
