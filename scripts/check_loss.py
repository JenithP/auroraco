"""로그 유실 검증: export_logs.py CSV (+ Qualtrics 원본 CSV).

    python scripts/check_loss.py logs.csv --survey qualtrics_export.csv
    python scripts/check_loss.py logs.csv --strict        # 부하 테스트: seq 누락이 있으면 종료 코드 1

지표
  - 참가자별 seq 누락 개수 (세션마다 0..마지막 seq 중 빠진 번호)
  - SESSION_END가 없는 참가자 비율
  - 설문 Prolific ID 중 로그에 없는 비율
  - 설문 주문 코드 중 로그 PAYMENT_ATTEMPT/PAYMENT_SUCCESS에 없는 비율
  - 위 지표를 조건(cond x errorType)별 표로
"""
import argparse
import csv
import re
import sys

import pandas as pd

PID_HEX = re.compile(r"^[a-f0-9]{24}$", re.I)
CODE_BODY = re.compile(r"^(?:AC-)?([A-Z0-9]{8}-[A-Z0-9]{4})$")
CODE_IN_TEXT = re.compile(r"AC-([A-Z0-9]{8}-[A-Z0-9]{4})(?![A-Z0-9])")
PAYMENT_TYPES = {"PAYMENT_ATTEMPT", "PAYMENT_SUCCESS"}
NO_LOG = "(로그 없음)"


def normalize_pid(raw):
    """index.html과 같은 규칙: 24자리 16진수는 소문자, 그 외는 특수문자를 _로 바꾸고 64자."""
    s = str(raw).strip()
    if not s:
        return ""
    return s.lower() if PID_HEX.match(s) else re.sub(r"[^A-Za-z0-9_-]", "_", s)[:64]


def normalize_code(raw):
    """공백·소문자·AC- 누락을 바로잡는다. 챗봇 문장을 통째로 붙여넣은 경우도 AC- 코드만 뽑는다. 아니면 None."""
    s = re.sub(r"\s+", "", str(raw)).upper()
    m = CODE_BODY.match(s) or CODE_IN_TEXT.search(s)
    return "AC-" + m.group(1) if m else None


def seq_missing(seqs):
    present = set(seqs)
    return (max(present) + 1 - len(present)) if present else 0


def load_participants(logs_csv):
    logs = pd.read_csv(logs_csv, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    logs["seq"] = pd.to_numeric(logs["seq"], errors="coerce")
    logs = logs.dropna(subset=["seq"])
    logs["seq"] = logs["seq"].astype(int)

    per_session = logs.groupby(["pid", "sessionId"])["seq"].apply(seq_missing).rename("seq_missing")
    part = per_session.groupby("pid").sum().to_frame()
    part["sessions"] = per_session.groupby("pid").size()
    part["events"] = logs.groupby("pid").size()
    part["has_session_end"] = logs.groupby("pid")["type"].apply(lambda t: (t == "SESSION_END").any())
    first = logs.sort_values("seq").groupby("pid").first()
    part["cond"] = first["cond"]
    part["errorType"] = first["errorType"]
    pay = logs[logs["type"].isin(PAYMENT_TYPES) & (logs["code"] != "")]
    part["pay_codes"] = pay.groupby("pid")["code"].apply(lambda c: " ".join(sorted(set(c))))
    part["pay_codes"] = part["pay_codes"].fillna("")
    part["group"] = part["cond"] + " x " + part["errorType"]
    return part.reset_index(), set(pay["code"])


def read_qualtrics(path):
    """Qualtrics 내보내기(1줄: 열 이름, 2줄: 문항 문구, 3줄: ImportId)를 읽는다."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    # 같은 열 이름이 두 번 나오는 경우가 있다(10월 설문의 Q5 = Prolific ID / 국적) — 뒤의 것에 .1, .2를 붙인다
    header, seen = [], {}
    for name in rows[0]:
        header.append(name if name not in seen else f"{name}.{seen[name]}")
        seen[name] = seen.get(name, 0) + 1
    body = rows[1:]
    labels = header
    if len(body) >= 2 and any(v.startswith('{"ImportId"') for v in body[1]):
        labels, body = body[0], body[2:]
    df = pd.DataFrame(body, columns=header)
    return df, dict(zip(header, labels))


def pick_columns(df, labels, pid_col, code_cols):
    if not pid_col:
        if "PROLIFIC_PID" in df.columns and (df["PROLIFIC_PID"].str.strip() != "").any():
            pid_col = "PROLIFIC_PID"
        else:
            pid_col = next((c for c in df.columns if "prolific id" in labels.get(c, "").lower()), None)
    if not code_cols:
        code_cols = [c for c in df.columns if "enter the code" in labels.get(c, "").lower()]
    if not pid_col or pid_col not in df.columns:
        sys.exit("Prolific ID 열을 찾지 못했다. --pid-col로 지정한다.")
    if not code_cols:
        sys.exit("주문 코드 열을 찾지 못했다. --code-col로 지정한다.")
    return pid_col, code_cols


def pct(n, d):
    return f"{n / d * 100:.1f}%" if d else "-"


def main():
    # Windows 콘솔(cp949)에서 표현 못 하는 문자가 있어도 멈추지 않도록
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("logs_csv", help="export_logs.py 결과 CSV")
    ap.add_argument("--survey", help="Qualtrics 원본 CSV")
    ap.add_argument("--pid-col", help="설문 Prolific ID 열 이름 (기본: 자동)")
    ap.add_argument("--code-col", action="append", help="설문 주문 코드 열 이름, 여러 번 가능 (기본: 자동)")
    ap.add_argument("--participants-out", help="참가자별 지표 CSV 저장 경로")
    ap.add_argument("--strict", action="store_true", help="seq 누락이 하나라도 있으면 종료 코드 1")
    args = ap.parse_args()

    part, log_codes = load_participants(args.logs_csv)
    part["seq_gap"] = part["seq_missing"] > 0
    log_pids = set(part["pid"])

    groups = part.groupby("group").agg(
        log_N=("pid", "size"),
        seq_gap_N=("seq_gap", "sum"),
        no_end_N=("has_session_end", lambda s: (~s).sum()),
    )
    groups["seq누락>=1"] = [pct(a, b) for a, b in zip(groups["seq_gap_N"], groups["log_N"])]
    groups["SESSION_END없음"] = [pct(a, b) for a, b in zip(groups["no_end_N"], groups["log_N"])]

    print(f"로그 참가자 {len(part)}명, 세션 {int(part['sessions'].sum())}개, 이벤트 {int(part['events'].sum())}건")
    print(f"seq 누락이 1개 이상인 참가자: {int(part['seq_gap'].sum())}명 ({pct(part['seq_gap'].sum(), len(part))}), "
          f"누락 이벤트 합계 {int(part['seq_missing'].sum())}건")
    print(f"SESSION_END 없는 참가자: {int((~part['has_session_end']).sum())}명 ({pct((~part['has_session_end']).sum(), len(part))})")

    if args.survey:
        df, labels = read_qualtrics(args.survey)
        pid_col, code_cols = pick_columns(df, labels, args.pid_col, args.code_col)
        print(f"\n설문 열: PID={pid_col} ({labels.get(pid_col, '')[:40]}), 코드={', '.join(code_cols)}")

        sv = pd.DataFrame({"pid": df[pid_col].map(normalize_pid)})
        raw_code = df[code_cols].apply(lambda r: next((v for v in r if str(v).strip()), ""), axis=1)
        sv["code_raw"] = raw_code
        sv["code"] = raw_code.map(normalize_code)
        no_pid = (sv["pid"] == "").sum()
        sv = sv[sv["pid"] != ""]
        sv["matched"] = sv["pid"].isin(log_pids)
        sv["has_code"] = sv["code_raw"].str.strip() != ""
        sv["code_bad_format"] = sv["has_code"] & sv["code"].isna()
        sv["code_missing"] = sv["code"].notna() & ~sv["code"].isin(log_codes)
        sv = sv.merge(part[["pid", "group"]], on="pid", how="left")
        sv["group"] = sv["group"].fillna(NO_LOG)

        sg = sv.groupby("group").agg(
            survey_N=("pid", "size"),
            matched_N=("matched", "sum"),
            code_N=("code", lambda c: c.notna().sum()),
            code_missing_N=("code_missing", "sum"),
        )
        groups = groups.join(sg, how="outer")
        groups[["log_N", "seq_gap_N", "no_end_N"]] = groups[["log_N", "seq_gap_N", "no_end_N"]].fillna(0).astype(int)
        groups[["seq누락>=1", "SESSION_END없음"]] = groups[["seq누락>=1", "SESSION_END없음"]].fillna("-")
        groups[["survey_N", "matched_N", "code_N", "code_missing_N"]] = \
            groups[["survey_N", "matched_N", "code_N", "code_missing_N"]].fillna(0).astype(int)
        groups["매칭률"] = [pct(a, b) for a, b in zip(groups["matched_N"], groups["survey_N"])]
        groups["코드누락"] = [pct(a, b) for a, b in zip(groups["code_missing_N"], groups["code_N"])]

        n, m = len(sv), int(sv["matched"].sum())
        n_code = int(sv["code"].notna().sum())
        print("\n===== 요약 =====")
        print(f"설문 {n} / 로그 매칭 {m} / 매칭률 {pct(m, n)}")
        print(f"seq 누락이 1개 이상인 참가자 비율 {pct(part['seq_gap'].sum(), len(part))}")
        print(f"결제 코드 누락 비율 {pct(int(sv['code_missing'].sum()), n_code)} "
              f"({int(sv['code_missing'].sum())}/{n_code})")
        print(f"(참고) PID 빈 응답 {no_pid}건, 코드 형식 오류 {int(sv['code_bad_format'].sum())}건 "
              f"- 예: {', '.join(sv.loc[sv['code_bad_format'], 'code_raw'].head(5))}")
        if args.participants_out:
            sv.to_csv(args.participants_out.rsplit(".", 1)[0] + "_survey.csv", index=False, encoding="utf-8-sig")

    print("\n===== 조건별 =====")
    print(groups.drop(columns=[c for c in groups.columns if c.endswith("_N") and c not in
                               ("log_N", "survey_N", "matched_N")]).to_string())

    if args.participants_out:
        part.to_csv(args.participants_out, index=False, encoding="utf-8-sig")

    if args.strict and part["seq_gap"].any():
        sys.exit(1)


if __name__ == "__main__":
    main()
