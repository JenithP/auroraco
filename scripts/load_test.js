// Aurora 로컬 부하 테스트: 동시 N세션이 쇼핑 → 결제 → 챗봇 → 코드 확인까지 진행한다.
//
//   cd scripts && npm install && npx playwright install chromium
//   (저장소 루트에서) python -m http.server 8765
//   node scripts/load_test.js                      # 기본 50세션, http://localhost:8765
//   SESSIONS=50 BASE_URL=http://localhost:8765 node scripts/load_test.js
//   STUDY_KEY=loadtest_20261021_run2 node scripts/load_test.js   # 같은 날 다시 돌릴 때
//
// - 각 세션은 가짜 PID(test_ + 랜덤)를 쓰고, studyKey는 loadtest_YYYYMMDD로 실험 데이터와 분리된다.
//   세션 ID는 LT_ 접두사가 붙어 Apps Script 시트에서도 구분된다.
// - 화면 클릭 대신 버튼의 onclick이 부르는 함수(openModal, addToCart, confirmPayment, handleQuick …)를
//   같은 순서로 호출한다. 로깅 경로는 실제 클릭과 같다.
// - 5세션 중 1세션은 결제 버튼을 누르자마자 탭을 닫는다(sendBeacon 경로 검증).
// - 결과: scripts/loadtest_out/<studyKey>_sessions.csv (PROLIFIC_PID, code …) — check_loss.py --survey로 넣는다.
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const BASE_URL = process.env.BASE_URL || 'http://localhost:8765';
const SESSIONS = Number(process.env.SESSIONS || 50);
const d = new Date();
const STUDY_KEY = process.env.STUDY_KEY ||
  `loadtest_${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`;
// 본실험 설계: outcome failure(normal/sumerror) × 아바타(Neutral/Smile)
const CONDS = [['nm', 'ne'], ['nm', 'sm'], ['se', 'ne'], ['se', 'sm']];
const ERROR_TYPE = { nm: 'normal', se: 'sumerror' };

const rand = (a, b) => a + Math.floor(Math.random() * (b - a + 1));
const randHex = n => Array.from({ length: n }, () => rand(0, 15).toString(16)).join('');

async function runSession(browser, i) {
  const [c, a] = CONDS[i % CONDS.length];
  const pid = 'test_' + randHex(12);
  // 결제 직후 탭 닫기 / 정상 종료 후 탭 닫기 / 정상 종료 후 설문으로 이동
  const exit = i % 5 === 4 ? 'close_after_pay_click' : (i % 2 ? 'close_tab' : 'go_to_survey');
  const result = { PROLIFIC_PID: pid, code: '', cond: a, errorType: ERROR_TYPE[c], exit, error: '' };

  const ctx = await browser.newContext();
  // 상품 이미지·GIF는 로깅과 무관하고 용량이 커서 막는다 (아바타 비디오는 그대로)
  await ctx.route(/\.(png|jpe?g|gif)$/i, r => r.abort());
  const page = await ctx.newPage();
  const wait = ms => page.waitForTimeout(ms);
  try {
    await wait(rand(0, 3000));  // 접속 시각을 조금씩 흩뜨린다
    await page.goto(`${BASE_URL}/?c=${c}&a=${a}&sk=${STUDY_KEY}&PROLIFIC_PID=${pid}&STUDY_ID=loadtest&SESSION_ID=lt${i}`);
    await wait(rand(2500, 4000));
    await page.evaluate(() => handleQuick('Start Shopping'));
    await wait(rand(800, 1500));

    // 쇼핑: 상품 2~4개 보기·담기, 찜 1번, 장바구니 열고 수량 변경
    const ids = Array.from({ length: rand(2, 4) }, () => rand(1, 18));
    for (const id of ids) {
      await page.evaluate(id => openModal(id), id);
      await wait(rand(500, 1500));
      await page.evaluate(() => addToCartFromModal());
      await wait(rand(300, 900));
    }
    await page.evaluate(id => toggleLike(id), ids[0]);
    await wait(rand(300, 800));
    await page.evaluate(() => togglePanel('cartPanel'));
    await wait(rand(500, 1200));
    await page.evaluate(id => changeQty(id, 1), ids[0]);
    await wait(rand(400, 900));
    await page.evaluate(() => openPayment());
    await wait(rand(600, 1500));

    if (exit === 'close_after_pay_click') {
      // 결제 로그는 confirmPayment 안에서 동기적으로 pushLog된다 — 저장 확인을 기다리지 않고 바로 닫는다
      result.code = await page.evaluate(() => {
        confirmPayment();
        return (logBuffer[logBuffer.length - 1].detail.match(/AC-[A-Z0-9]+-[A-Z0-9]{4}/) || [''])[0];
      });
      await page.close({ runBeforeUnload: true });
    } else {
      await page.evaluate(() => confirmPayment());
      if (c === 'se') {
        await wait(6500);   // 결제 5초 후 챗봇 자동 팝업
        await page.evaluate(() => handleQuick('Sum error (wrong total)'));
        await wait(4500);
        if (Math.random() < 0.5) {
          await page.evaluate(() => handleQuick('Will I get a refund?'));
          await wait(1500);
        }
        await page.evaluate(() => handleQuick('Okay, understood'));
        await wait(2500);
      } else {
        await wait(3500);
      }
      result.code = await page.evaluate(() => {
        const m = [...document.querySelectorAll('#chatMessages .msg.bot')].map(e => e.textContent).join(' ')
          .match(/AC-[A-Z0-9]+-[A-Z0-9]{4}/);
        return m ? m[0] : '';
      });
      await wait(rand(1000, 3000));   // 코드 확인
      if (exit === 'close_tab') await page.close({ runBeforeUnload: true });
      else await page.goto('about:blank');
    }
    await new Promise(r => setTimeout(r, 2000));   // sendBeacon이 나갈 시간
  } catch (err) {
    result.error = String(err.message || err).split('\n')[0];
  } finally {
    await ctx.close();
  }
  return result;
}

(async () => {
  console.log(`studyKey=${STUDY_KEY}  sessions=${SESSIONS}  base=${BASE_URL}`);
  const browser = await chromium.launch();
  const t0 = Date.now();
  const results = await Promise.all(Array.from({ length: SESSIONS }, (_, i) => runSession(browser, i)));
  await browser.close();

  const outDir = path.join(__dirname, 'loadtest_out');
  fs.mkdirSync(outDir, { recursive: true });
  const out = path.join(outDir, `${STUDY_KEY}_sessions.csv`);
  const cols = Object.keys(results[0]);
  fs.writeFileSync(out, [cols.join(','), ...results.map(r => cols.map(k => `"${String(r[k]).replace(/"/g, '""')}"`).join(','))].join('\n'));

  const failed = results.filter(r => r.error);
  console.log(`done in ${((Date.now() - t0) / 1000).toFixed(0)}s: ${results.length - failed.length} ok, ${failed.length} errors, ` +
    `${results.filter(r => r.code).length} codes -> ${out}`);
  failed.forEach(r => console.log('  ERROR', r.PROLIFIC_PID, r.error));
  console.log(`\nnext:\n  python scripts/export_logs.py --study-key ${STUDY_KEY} --out ${STUDY_KEY}.csv` +
    `\n  python scripts/check_loss.py ${STUDY_KEY}.csv --survey "${out}" --pid-col PROLIFIC_PID --code-col code --include-test --strict`);
})();
