// ===== Firebase Realtime Database 쓰기 모듈 =====
// index.html의 추적 스크립트가 페이지 load 이후 동적 import로 불러온다
// (SDK 다운로드가 load 이벤트·웰컴 팝업 타이밍을 늦추지 않도록).
// 큐·재시도·sendBeacon은 index.html 쪽에서 처리하고, 이 모듈은 실제 쓰기만 맡는다.
const CFG = window.AURORA_CONFIG;
const SDK = 'https://www.gstatic.com/firebasejs/' + CFG.FIREBASE_SDK_VERSION;

const { initializeApp } = await import(SDK + '/firebase-app.js');
const { getDatabase, ref, push, set, update } = await import(SDK + '/firebase-database.js');

const db = getDatabase(initializeApp(CFG.firebase));

export function connect(basePath) {
  return {
    // key가 있으면 재시도 — 같은 push 키에 다시 쓴다(첫 쓰기가 거부된 경우에만 재시도하므로 중복 없음)
    writeEvent(ev, key) {
      const r = key ? ref(db, basePath + '/events/' + key) : push(ref(db, basePath + '/events'));
      return { key: r.key, done: set(r, ev) };
    },
    writeMeta(fields) {
      return update(ref(db, basePath + '/meta'), fields);
    }
  };
}
