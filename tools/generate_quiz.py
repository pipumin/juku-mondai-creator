#!/usr/bin/env python3
"""NotebookLM でテキストからクイズを生成し、raw JSON を保存する薄いラッパ。

親が「テキスト 1 本 → クイズ JSON」を 1 コマンドで作れるようにするためのもの。
クイズの中身の構造には依存せず、notebooklm CLI を順に呼ぶだけ。

使い方:
  py tools/generate_quiz.py --text data/raw/edo-source.txt \
      --title "受験クイズ: 社会 江戸時代" --out data/raw/edo-quiz.json

前提:
  - notebooklm CLI がインストール済み & ログイン済み(`notebooklm login` は別ターミナルで)。
  - Windows では cp932 クラッシュ回避のため PYTHONIOENCODING=utf-8 を内部で付与する。
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

# CLI 呼び出し時に必ず付与する環境変数(Windows の Shift_JIS クラッシュ回避)
ENV_EXTRA = {"PYTHONIOENCODING": "utf-8"}


def _cli() -> str:
    exe = shutil.which("notebooklm")
    if not exe:
        sys.exit("notebooklm CLI が見つかりません。`pip install notebooklm-py` を実行してください。")
    return exe


def run(args: list[str], *, capture: bool = True) -> str:
    """notebooklm を実行して stdout を返す。失敗時は中身を表示して終了。"""
    import os

    env = {**os.environ, **ENV_EXTRA}
    # 子プロセスは UTF-8 で出力する(ENV_EXTRA)。親側も UTF-8 で復号する
    # (Windows 既定の cp932 で復号すると UnicodeDecodeError になるため)。
    cp = subprocess.run(
        [_cli(), *args],
        capture_output=capture,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    if cp.returncode != 0:
        sys.stderr.write(cp.stdout or "")
        sys.stderr.write(cp.stderr or "")
        sys.exit(f"`notebooklm {' '.join(args)}` が失敗しました (exit {cp.returncode})")
    return cp.stdout or ""


def jrun(args: list[str]) -> dict:
    """--json を付けて実行し、JSON をパースして返す。"""
    return json.loads(run([*args, "--json"]))


def first_id(d: dict, *keys: str) -> str | None:
    for k in keys:
        if d.get(k):
            return str(d[k])
    return None


def wait_source_ready(nb: str, source_id: str, timeout: int = 600) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        sources = jrun(["source", "list", "--notebook", nb]).get("sources", [])
        for s in sources:
            if str(s.get("id", "")).startswith(source_id[:8]):
                status = str(s.get("status", "")).lower()
                if status == "ready":
                    return
                if status == "error":
                    sys.exit("ソースの処理に失敗しました (status=error)")
        print("  ...ソース処理待ち", flush=True)
        time.sleep(15)
    sys.exit("ソース処理がタイムアウトしました")


def wait_artifact_done(nb: str, artifact_id: str | None, timeout: int = 900) -> str:
    """クイズ artifact が completed になるまで待ち、その artifact id を返す。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        arts = jrun(["artifact", "list", "--notebook", nb]).get("artifacts", [])
        # id 一致を優先。なければ type に Quiz を含む最新を見る。
        cands = [a for a in arts if artifact_id and str(a.get("id", "")).startswith(artifact_id[:8])]
        if not cands:
            cands = [a for a in arts if "quiz" in str(a.get("type", "")).lower()]
        for a in cands:
            if str(a.get("status", "")).lower() == "completed":
                return str(a["id"])
        print("  ...クイズ生成待ち", flush=True)
        time.sleep(20)
    sys.exit("クイズ生成がタイムアウトしました(レート制限の可能性。時間を空けて再実行 or Web UI で生成)")


def main() -> None:
    p = argparse.ArgumentParser(description="NotebookLM でテキストからクイズ raw JSON を生成")
    p.add_argument("--text", required=True, help="教材テキスト/PDF のパス、または URL")
    p.add_argument("--title", required=True, help="作成する NotebookLM ノートブックのタイトル")
    p.add_argument("--out", required=True, help="クイズ raw JSON の保存先パス")
    p.add_argument("--difficulty", default="medium", choices=["easy", "medium", "hard"])
    p.add_argument("--quantity", default="standard", choices=["fewer", "standard", "more"])
    p.add_argument("--notebook", help="既存ノートブック ID を使う(省略時は新規作成)")
    args = p.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    # 出力言語を日本語に(グローバル設定)
    run(["language", "set", "ja"])

    if args.notebook:
        nb = args.notebook
        print(f"既存ノートブックを使用: {nb}", flush=True)
    else:
        nb = first_id(jrun(["create", args.title]), "id", "notebook_id")
        if not nb:
            sys.exit("ノートブックの作成に失敗しました")
        print(f"ノートブック作成: {nb}", flush=True)

    add = jrun(["source", "add", args.text, "--notebook", nb])
    source_id = first_id(add, "source_id", "id")
    print(f"ソース追加: {source_id}", flush=True)
    if source_id:
        wait_source_ready(nb, source_id)

    gen = jrun(["generate", "quiz", "--notebook", nb,
                "--difficulty", args.difficulty, "--quantity", args.quantity])
    artifact_id = first_id(gen, "artifact_id", "task_id", "id")
    print(f"クイズ生成開始: artifact={artifact_id}", flush=True)
    artifact_id = wait_artifact_done(nb, artifact_id)

    run(["download", "quiz", str(out), "-n", nb, "-a", artifact_id])
    print(f"\n完了: {out}", flush=True)
    print(f"次:  py tools/normalize_quiz.py {out} --subject <id> --section <id> --title <表示名>", flush=True)


if __name__ == "__main__":
    main()
