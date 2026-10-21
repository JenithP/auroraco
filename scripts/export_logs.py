"""Firebase /aurora_logs/{studyKey} → 이벤트 1행 = 1줄 CSV.

events와 beacon(이탈 시 sendBeacon)에 같은 이벤트가 둘 다 있으면
(pid, sessionId, seq) 기준으로 하나만 남긴다(events 우선).

인증은 GOOGLE_APPLICATION_CREDENTIALS 환경변수의 서비스 계정 키로 한다.

    python scripts/export_logs.py --study-key 2026-11_replication --out logs.csv
    python scripts/export_logs.py --from-json firebase-export.json --out logs.csv
"""
import argparse
import csv
import json
import sys

DATABASE_URL = "https://media-monopoly-default-rtdb.europe-west1.firebasedatabase.app"
COLUMNS = ["pid", "sessionId", "seq", "ts", "serverTs", "elapsed", "type", "detail",
           "cond", "errorType", "code", "source"]
META_COLUMNS = ["pid", "cond", "errorType", "sessionId", "startedAt", "pidStatus", "pidRaw",
                "prolificStudyId", "prolificSessionId", "code", "userAgent"]


def fetch_study(study_key):
    import firebase_admin
    from firebase_admin import credentials, db

    firebase_admin.initialize_app(credentials.ApplicationDefault(), {"databaseURL": DATABASE_URL})
    return db.reference(f"aurora_logs/{study_key}").get() or {}


def _values(node):
    """Firebase는 0..n 키를 리스트로 돌려줄 때가 있다 — dict/list 모두 값 목록으로."""
    if node is None:
        return []
    if isinstance(node, list):
        return [v for v in node if v is not None]
    return list(node.values())


def flatten(study):
    rows, metas = {}, []
    for pid, node in sorted(study.items()):
        if not isinstance(node, dict):
            continue
        meta = node.get("meta") or {}
        metas.append({"pid": pid, **{k: meta.get(k, "") for k in META_COLUMNS if k != "pid"}})

        sources = [("events", ev) for ev in _values(node.get("events"))]
        sources += [("beacon", ev) for batch in _values(node.get("beacon")) for ev in _values(batch)]
        for source, ev in sources:
            if not isinstance(ev, dict):
                continue
            key = (pid, ev.get("sessionId", ""), ev.get("seq"))
            if key in rows and rows[key]["source"] == "events":
                continue
            rows[key] = {"pid": pid, "source": source, **{c: ev.get(c, "") for c in COLUMNS[1:-1]}}

    ordered = sorted(rows.values(), key=lambda r: (r["pid"], str(r["sessionId"]), r["seq"] if isinstance(r["seq"], int) else -1))
    return ordered, metas


def write_csv(path, columns, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        w.writerows(rows)


def main():
    # Windows 콘솔(cp949)에서 표현 못 하는 문자가 있어도 멈추지 않도록
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--study-key", default="2026-11_replication", help="/aurora_logs/ 아래 실험 차수 키")
    ap.add_argument("--from-json", help="Firebase에서 받은 JSON 파일(studyKey 노드 또는 DB 전체)")
    ap.add_argument("--out", default="logs.csv")
    ap.add_argument("--meta-out", help="참가자별 meta CSV (기본: <out>_meta.csv)")
    args = ap.parse_args()

    if args.from_json:
        with open(args.from_json, encoding="utf-8") as f:
            study = json.load(f) or {}
        # DB 전체를 받은 파일이면 studyKey 노드까지 내려간다
        study = study.get("aurora_logs", {}).get(args.study_key, study) if "aurora_logs" in study else study
    else:
        study = fetch_study(args.study_key)

    rows, metas = flatten(study)
    write_csv(args.out, COLUMNS, rows)
    meta_out = args.meta_out or args.out.rsplit(".", 1)[0] + "_meta.csv"
    write_csv(meta_out, META_COLUMNS, metas)

    n_beacon_only = sum(r["source"] == "beacon" for r in rows)
    print(f"{len(metas)} participants, {len(rows)} events "
          f"({n_beacon_only} recovered only via beacon) -> {args.out}, {meta_out}", file=sys.stderr)


if __name__ == "__main__":
    main()
