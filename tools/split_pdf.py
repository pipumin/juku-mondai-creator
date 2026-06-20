#!/usr/bin/env python3
"""PDF をページ範囲ごとに分割するシンプルなツール。

教科別に本誌 PDF を切り出して、NotebookLM に投入しやすくするためのもの。
ページ番号は 1 始まり・両端を含む。

使い方:
  py tools/split_pdf.py "data/raw/小６EXE４月_本誌.pdf" --out data/raw/split --prefix 小6EXE_4月 \
     --range 算数=1-26 --range 理科=27-52 --range 社会=53-79 --range 国語=80-116
  → data/raw/split/小6EXE_4月_算数.pdf などを出力
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pypdf import PdfReader, PdfWriter


def parse_range(spec: str) -> tuple[str, int, int]:
    # "算数=1-26" → ("算数", 1, 26)
    try:
        label, rng = spec.split("=", 1)
        a, b = rng.split("-", 1)
        return label, int(a), int(b)
    except Exception:
        sys.exit(f"--range の書式が不正です: {spec!r}（例: 算数=1-26）")


def main() -> None:
    p = argparse.ArgumentParser(description="PDF をページ範囲ごとに分割")
    p.add_argument("pdf", help="入力 PDF")
    p.add_argument("--out", default="data/raw/split", help="出力ディレクトリ")
    p.add_argument("--prefix", required=True, help="出力ファイル名の接頭辞（例 小6EXE_4月）")
    p.add_argument("--range", dest="ranges", action="append", required=True,
                   help="ラベル=開始-終了（1始まり・両端含む）。複数指定可")
    args = p.parse_args()

    reader = PdfReader(args.pdf)
    n = len(reader.pages)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    for spec in args.ranges:
        label, start, end = parse_range(spec)
        if not (1 <= start <= end <= n):
            sys.exit(f"範囲が不正です: {label}={start}-{end}（PDFは{n}ページ）")
        writer = PdfWriter()
        for i in range(start - 1, end):  # 0始まりへ変換
            writer.add_page(reader.pages[i])
        out_path = out_dir / f"{args.prefix}_{label}.pdf"
        with open(out_path, "wb") as f:
            writer.write(f)
        print(f"{out_path}  (p{start}-{end}, {end - start + 1}ページ)")


if __name__ == "__main__":
    main()
