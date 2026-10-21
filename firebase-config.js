// ===== Aurora 로깅 설정 =====
// 실험 차수·로그 대상은 이 파일 한 곳에서만 바꾼다.
// 웹 SDK 설정값은 브라우저에 노출되는 값이라 비밀이 아니다. 보안은 database.rules.json으로 지킨다.
// 서비스 계정 키(관리자 키)는 절대 이 파일이나 브라우저 코드에 넣지 않는다.
window.AURORA_CONFIG = {
  // 실험 차수 구분값 → /aurora_logs/{STUDY_KEY}/...
  // 데모(?demo=1)는 'demo', 부하 테스트(?sk=loadtest_YYYYMMDD)는 해당 키로 자동 분리된다.
  STUDY_KEY: '2026-11_replication',

  // 파일럿에서 유실률 0%를 확인할 때까지 Apps Script와 Firebase에 이중 기록한다.
  LOG_TO_APPS_SCRIPT: true,
  LOG_TO_FIREBASE: true,

  FIREBASE_SDK_VERSION: '12.8.0',
  firebase: {
    apiKey: "AIzaSyDhUg2Vi6h2o6zMYUzv2dRGbw79A0gUY1M",
    authDomain: "media-monopoly.firebaseapp.com",
    databaseURL: "https://media-monopoly-default-rtdb.europe-west1.firebasedatabase.app",
    projectId: "media-monopoly",
    storageBucket: "media-monopoly.firebasestorage.app",
    messagingSenderId: "861615661534",
    appId: "1:861615661534:web:b5e2a846443d9ae6fd3d4f"
  }
};
