"""
daily_archive.py — Immutable daily audit archive.

Creates a timestamped ZIP for each trading day containing every file
needed to reconstruct what the system knew and decided.

Once written, the archive is never modified or overwritten.
If you ask "why did MoneyBot buy INFY on 2026-07-08?"
the answer is inside 2026-07-08_audit.zip.

Usage:
  python daily_archive.py              # archive today
  python daily_archive.py 2026-07-01   # archive a specific date
"""

import json
import sys
import os
import zipfile
import io
from datetime import date, datetime
from pathlib import Path

os.chdir(os.path.dirname(os.path.abspath(__file__)))

ARCHIVE_DIR = Path("audit_archives")


def _read_or_missing(path: Path) -> str:
    if not path.exists():
        return f"[NOT FOUND: {path}]"
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"[ERROR reading {path}: {e}]"


def create_archive(target: date = None) -> Path:
    target = target or date.today()
    ARCHIVE_DIR.mkdir(exist_ok=True)

    archive_path = ARCHIVE_DIR / f"{target}_audit.zip"

    if archive_path.exists():
        print(f"  Archive already exists: {archive_path}")
        print(f"  Immutable — not overwriting.")
        return archive_path

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
        prefix = str(target)

        # ── Manifest ────────────────────────────────────────────────────────
        manifest = {
            "date": str(target),
            "created_at": ts,
            "moneybot_version": "v1.2.0",
            "purpose": "Immutable audit archive. Never modify after creation.",
            "files": [],
        }

        def add(arcname: str, content: str):
            zf.writestr(f"{prefix}/{arcname}", content)
            manifest["files"].append(arcname)

        # ── Strategy fingerprint ─────────────────────────────────────────────
        try:
            from strategy_fingerprint import get_fingerprint, get_params
            fp_lines = [
                f"Strategy Fingerprint: {get_fingerprint()}",
                f"Generated: {ts}",
                f"Date: {target}",
                "",
                "Parameters:",
            ]
            for k, v in get_params().items():
                fp_lines.append(f"  {k:<16} = {v}")
            add("strategy_fingerprint.txt", "\n".join(fp_lines))
        except Exception as e:
            add("strategy_fingerprint.txt", f"[ERROR: {e}]")

        # ── Ops report ───────────────────────────────────────────────────────
        ops_path = Path(f"ops_log_{target}.json")
        add("daily_ops_report.json", _read_or_missing(ops_path))

        # ── Explainability report ────────────────────────────────────────────
        try:
            from daily_explain import explain, confidence_score
            import io as _io, sys as _sys
            buf = _io.StringIO()
            old_stdout = _sys.stdout
            _sys.stdout = buf
            explain(target)
            _sys.stdout = old_stdout
            explain_text = buf.getvalue()
        except Exception as e:
            explain_text = f"[ERROR generating explainability report: {e}]"
        add("explainability_report.txt", explain_text)

        # ── Invariants ───────────────────────────────────────────────────────
        try:
            from invariant_checker import check_all_invariants
            import io as _io, sys as _sys
            report = check_all_invariants()
            lines = [
                f"Invariant Check: {ts}",
                f"Checks run: {report.checks_run}",
                f"Violations: {len(report.violations)}",
                f"Must halt: {report.must_halt}",
                "",
            ]
            if report.violations:
                for v in report.violations:
                    lines.append(f"  [{v.severity}] {v.invariant}: {v.detail}")
            else:
                lines.append("  ALL INVARIANTS HOLD")
            inv_text = "\n".join(lines)
        except Exception as e:
            inv_text = f"[ERROR running invariants: {e}]"
        add("invariants.txt", inv_text)

        # ── Broker audit (latest entry) ──────────────────────────────────────
        audit_log = Path("broker_audit_log.json")
        if audit_log.exists():
            try:
                history = json.loads(audit_log.read_text(encoding="utf-8"))
                today_entries = [e for e in history if str(e.get("date", ""))[:10] == str(target)]
                broker_text = json.dumps(today_entries or history[-1:], indent=2, default=str)
            except Exception as e:
                broker_text = f"[ERROR: {e}]"
        else:
            broker_text = "[broker_audit_log.json not found]"
        add("broker_audit.json", broker_text)

        # ── Execution state snapshot ─────────────────────────────────────────
        add("execution_state.json", _read_or_missing(Path("execution_state.json")))

        # ── Trades ──────────────────────────────────────────────────────────
        journal = Path("trade_journal.csv")
        if journal.exists():
            try:
                import csv
                rows = []
                with open(journal, encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if str(row.get("date", ""))[:10] == str(target):
                            rows.append(row)
                if rows:
                    keys = list(rows[0].keys())
                    lines = [",".join(keys)]
                    for row in rows:
                        lines.append(",".join(str(row.get(k, "")) for k in keys))
                    trades_text = "\n".join(lines)
                else:
                    trades_text = "date,symbol,side,qty,price,pnl\n(no trades on this date)"
            except Exception as e:
                trades_text = f"[ERROR: {e}]"
        else:
            trades_text = "(trade_journal.csv not found)"
        add("trades.csv", trades_text)

        # ── Confidence report ────────────────────────────────────────────────
        try:
            from daily_explain import confidence_score
            score = confidence_score()
            lines = [
                f"Confidence Report: {ts}",
                f"Overall: {score['overall']}%",
                f"Safe to trade: {score['safe_to_trade']}",
                "",
                "Components:",
            ]
            for k, v in score["components"].items():
                note = score["reasons"].get(k, "")
                lines.append(f"  {k:<14} {v}%" + (f"  — {note}" if note else ""))
            conf_text = "\n".join(lines)
        except Exception as e:
            conf_text = f"[ERROR: {e}]"
        add("confidence_report.txt", conf_text)

        # ── Regime history (today's entry) ──────────────────────────────────
        try:
            from regime_history import load as rh_load
            history = rh_load()
            today_entry = next((e for e in history if e.get("date") == str(target)), None)
            rh_text = json.dumps(today_entry or {"date": str(target), "note": "not recorded"}, indent=2)
        except Exception as e:
            rh_text = f"[ERROR: {e}]"
        add("regime_entry.json", rh_text)

        # ── Log excerpt (today's lines from auto_daily.log) ──────────────────
        log_path = Path("auto_daily.log")
        if log_path.exists():
            try:
                today_str = str(target)
                log_lines = [l for l in log_path.read_text(encoding="utf-8", errors="replace").splitlines()
                             if today_str in l]
                log_excerpt = "\n".join(log_lines) or "(no log entries for this date)"
            except Exception as e:
                log_excerpt = f"[ERROR: {e}]"
        else:
            log_excerpt = "(auto_daily.log not found)"
        add("auto_daily_excerpt.log", log_excerpt)

        # ── Finalize manifest ────────────────────────────────────────────────
        zf.writestr(f"{prefix}/MANIFEST.json",
                    json.dumps(manifest, indent=2, default=str))

    size_kb = archive_path.stat().st_size // 1024
    print(f"  Archive created: {archive_path}  ({size_kb} KB, {len(manifest['files'])} files)")
    return archive_path


def list_archives():
    ARCHIVE_DIR.mkdir(exist_ok=True)
    archives = sorted(ARCHIVE_DIR.glob("*_audit.zip"))
    if not archives:
        print("  No audit archives yet.")
        return
    sep = "=" * 50
    print(f"\n{sep}")
    print(f"  AUDIT ARCHIVES ({len(archives)} days)")
    print(sep)
    total_kb = 0
    for a in archives:
        kb = a.stat().st_size // 1024
        total_kb += kb
        print(f"  {a.stem:<30} {kb:>5} KB")
    print(f"  {'─'*40}")
    print(f"  Total: {total_kb:,} KB  ({total_kb//1024} MB)")
    print(sep)


if __name__ == "__main__":
    if "--list" in sys.argv:
        list_archives()
    else:
        target = None
        for arg in sys.argv[1:]:
            if arg.startswith("20") and len(arg) == 10:
                try:
                    target = date.fromisoformat(arg)
                except ValueError:
                    pass
        create_archive(target)
