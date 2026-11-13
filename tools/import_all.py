#!/usr/bin/env python3
"""quiz-jobs.json に書いたクイズを、まとめてアプリに取り込む。

  py -3 tools/import_all.py

ジョブ1件ごとに次を行う:
  1. 元データ(raw JSON)が手元に無ければ、NotebookLM から同じ題名のクイズをダウンロード
     (--generate を付けると、NotebookLM にも無い場合は「範囲」を指定して生成する)
  2. 元データが前回の取り込みより新しければ、アプリ用に変換して docs/quizzes/ に書く
  3. 変換結果を機械的に検査し、人が見直すべき点を [要確認] として表示

すでに取り込み済みで元データが変わっていないジョブは何もしない。何度実行してもよい。

quiz-jobs.json のジョブの書き方:
  { "id": "shakai-koumin-04",         教科-単元-連番。教科と単元はここから決まる
    "title": "7月社会_公民クイズ",     アプリの表示名。NotebookLM 上のクイズ名も同じにする
    "month": "2026-07",                出題月
    "range": "…",                      (--generate 用) プロンプトの【範囲】に入る単元名
    "raw": "data/raw/….json" }         省略時は data/raw/<id>.json
新しい教科・単元を足すときは、"names" に表示名も足す (例 "rika": "理科", "rika/kishou": "気象")。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from normalize_quiz import check_questions, import_quiz  # noqa: E402

ID_RE = re.compile(r"([A-Za-z0-9_]+)-([A-Za-z0-9_-]+)-(\d+)")
MONTH_RE = re.compile(r"\d{4}-(?:0[1-9]|1[0-2])")
# NotebookLM に接続できない(ログイン切れ等)ときに CLI が出す文言。以後のジョブでは呼ばない
AUTH_HINTS = ("authentication", "csrf", "login", "expired", "unauthorized")


class NotebookLMError(Exception):
    pass


def cli_command() -> list[str]:
    """notebooklm CLI の起動方法を決める。NOTEBOOKLM_CMD > pipx の Python > PATH の順。
    (pipx の notebooklm.exe は Windows のアプリ制御でブロックされることがあるため、
     同じ環境の python -m notebooklm を優先する)"""
    if os.environ.get("NOTEBOOKLM_CMD"):
        return os.environ["NOTEBOOKLM_CMD"].split()
    pipx_py = Path.home() / "pipx" / "venvs" / "notebooklm-py" / "Scripts" / "python.exe"
    if pipx_py.exists():
        return [str(pipx_py), "-m", "notebooklm"]
    exe = shutil.which("notebooklm")
    if exe:
        return [exe]
    raise NotebookLMError("notebooklm CLI が見つかりません (pipx install \"notebooklm-py[browser]\")")


def nlm(args: list[str], *, stdin: str | None = None) -> str:
    """notebooklm を実行して stdout を返す。失敗したら NotebookLMError。"""
    cp = subprocess.run(
        [*cli_command(), *args], input=stdin, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},  # Windows の cp932 クラッシュ回避
    )
    if cp.returncode != 0 or '"error": true' in cp.stdout:
        msg = (cp.stdout + cp.stderr).strip()
        raise NotebookLMError(msg[-600:] or f"exit {cp.returncode}")
    return cp.stdout


def is_auth_error(e: Exception) -> bool:
    return any(h in str(e).lower() for h in AUTH_HINTS)


def download(notebook: str, title: str, raw: Path) -> None:
    raw.parent.mkdir(parents=True, exist_ok=True)
    nlm(["download", "quiz", str(raw), "-n", notebook, "--name", title])
    if not raw.exists():
        raise NotebookLMError(f"「{title}」という名前のクイズが NotebookLM にありません")


def generate(notebook: str, job: dict, prompt: str, raw: Path) -> None:
    """NotebookLM でクイズを生成し、題名を付けてダウンロードする。"""
    out = nlm(["generate", "quiz", "--prompt-file", "-", "-n", notebook,
               "--quantity", job.get("quantity", "standard"),
               "--difficulty", job.get("difficulty", "medium"),
               "--wait", "--timeout", "900", "--retry", "2", "--json"],
              stdin=prompt.replace("【範囲】", f"【{job['range']}】"))
    data = json.loads(out)
    data = data.get("artifact", data) if isinstance(data, dict) else {}
    artifact_id = next((str(data[k]) for k in ("artifact_id", "id", "task_id") if data.get(k)), None)
    if not artifact_id:
        raise NotebookLMError(f"生成結果からクイズの ID を読み取れませんでした: {out[:300]}")
    nlm(["artifact", "rename", artifact_id, job["title"], "-n", notebook])
    raw.parent.mkdir(parents=True, exist_ok=True)
    nlm(["download", "quiz", str(raw), "-n", notebook, "-a", artifact_id])


def main() -> None:
    p = argparse.ArgumentParser(description="quiz-jobs.json のクイズをまとめて取り込む")
    p.add_argument("--jobs", default="quiz-jobs.json", help="ジョブ表 (既定 quiz-jobs.json)")
    p.add_argument("--docs", default="docs", help="公開サイトのルート (既定 docs)")
    p.add_argument("--only", action="append", metavar="ID", help="この ID のジョブだけ処理 (複数指定可)")
    p.add_argument("--force", action="store_true", help="元データが変わっていなくても取り込み直す")
    p.add_argument("--generate", action="store_true",
                   help="NotebookLM にクイズが無いジョブは、range を使って生成する")
    args = p.parse_args()

    conf = json.loads(Path(args.jobs).read_text(encoding="utf-8"))
    names = conf.get("names", {})
    prompt = "\n".join(conf.get("prompt", []))
    jobs = conf["jobs"]

    ids = [j.get("id") for j in jobs]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        sys.exit(f"{args.jobs}: id が重複しています: {sorted(dup)}")
    if args.only:
        unknown = set(args.only) - set(ids)
        if unknown:
            sys.exit(f"--only の ID が {args.jobs} にありません: {sorted(unknown)}")
        jobs = [j for j in jobs if j["id"] in args.only]

    results = []        # (id, 状態, 補足)
    nlm_down = None     # NotebookLM に接続できないと分かったら、その理由を入れる
    failed = False

    for job in jobs:
        jid = job.get("id", "")
        m = ID_RE.fullmatch(jid)
        if not m or not job.get("title") or not MONTH_RE.fullmatch(job.get("month", "")):
            results.append((jid or "?", "設定ミス", "id は 教科-単元-連番、title と month(YYYY-MM) が必須"))
            failed = True
            continue
        subject, section = m.group(1), m.group(2)
        raw = Path(job.get("raw") or f"data/raw/{jid}.json")
        out = Path(args.docs) / "quizzes" / subject / section / f"{jid}.json"

        # 1. 元データが無ければ NotebookLM から取ってくる
        if not raw.exists():
            if nlm_down:
                results.append((jid, "未取得", "NotebookLM に接続できないため見送り"))
                continue
            try:
                try:
                    download(conf["notebook"], job["title"], raw)
                    print(f"{jid}: NotebookLM からダウンロード → {raw}", flush=True)
                except NotebookLMError as e:
                    if is_auth_error(e) or not (args.generate and job.get("range")):
                        raise
                    print(f"{jid}: NotebookLM で生成中 (数分〜15分かかります)…", flush=True)
                    generate(conf["notebook"], job, prompt, raw)
                    print(f"{jid}: 生成してダウンロード → {raw}", flush=True)
            except NotebookLMError as e:
                if is_auth_error(e):
                    nlm_down = str(e)
                    results.append((jid, "未取得", "NotebookLM に接続できません"))
                else:
                    hint = "" if args.generate else " (--generate で生成できます)"
                    results.append((jid, "未取得", f"{str(e).splitlines()[-1][:120]}{hint}"))
                failed = True
                continue

        # 2. 取り込み済みで元データが変わっていなければ何もしない
        if out.exists() and raw.stat().st_mtime <= out.stat().st_mtime and not args.force:
            results.append((jid, "変更なし", ""))
            continue

        # 3. 変換して検査
        try:
            _, _, questions = import_quiz(
                raw, subject=subject, section=section, title=job["title"], month=job["month"],
                quiz_id=jid, subject_name=names.get(subject, ""),
                section_name=names.get(f"{subject}/{section}", ""), docs=args.docs)
        except SystemExit as e:
            results.append((jid, "変換失敗", str(e).splitlines()[0]))
            print(f"{jid}: 変換失敗\n{e}", file=sys.stderr)
            failed = True
            continue
        warns = check_questions(questions)
        results.append((jid, "取り込み", f"{len(questions)} 問" + (f"、要確認 {len(warns)} 件" if warns else "")))
        for w in warns:
            print(f"[要確認] {jid} {w}")

    print("\n== 結果 ==")
    for jid, state, note in results:
        print(f"  {jid:<24} {state}" + (f"  {note}" if note else ""))
    if nlm_down:
        detail = next((ln for ln in nlm_down.splitlines() if any(h in ln.lower() for h in AUTH_HINTS)), "")
        print("\nNotebookLM に接続できませんでした。別のターミナルで `notebooklm login` を実行して"
              "ログインし直してから、もう一度実行してください。\n"
              "それでも直らなければ CLI が古い可能性があります: `pipx upgrade notebooklm-py`\n"
              "  詳細: " + detail.strip()[:200])
    if any(s == "取り込み" for _, s, _ in results):
        print("\n確認: py -3 -m http.server 8000 --directory docs → http://localhost:8000")
        print("公開: git add docs && git commit && git push (GitHub Pages に反映)")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
