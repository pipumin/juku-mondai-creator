#!/usr/bin/env python3
"""NotebookLM のクイズ raw JSON を、アプリ用の正規化スキーマに変換するスクリプト。

- 出力: docs/quizzes/<subject>/<section>/<quizid>.json
- 同時に docs/quizzes/manifest.json を自動更新(教科/節が無ければ作成、クイズを追記)。
  → 親は manifest.json を手で編集しなくてよい。

使い方:
  py tools/normalize_quiz.py data/raw/edo-quiz.json \
      --subject shakai --subject-name "社会" \
      --section edo --section-name "江戸時代" \
      --title "江戸時代の基礎"

NotebookLM の raw JSON 構造はバージョンで変わりうるため、代表的なキー名を
広めに拾う。判別できない場合は中身を表示して終了するので、その JSON を見て
EXTRACT 部分のキー候補を足せばよい。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

# 正規化先アプリスキーマ:
# { id, subject, section, title, createdAt, questions:[{id, question, choices[], answerIndex, explanation}] }

Q_LIST_KEYS = ("questions", "items", "quiz", "data", "cards")
Q_TEXT_KEYS = ("question", "prompt", "text", "stem", "title", "front")
CHOICE_KEYS = ("choices", "options", "answers", "candidates", "distractors")
CHOICE_TEXT_KEYS = ("text", "label", "option", "value", "content", "answer")
CORRECT_FLAG_KEYS = ("correct", "is_correct", "isCorrect", "correctAnswer", "is_answer")
ANSWER_KEYS = ("answerIndex", "answer_index", "correctIndex", "correct_index",
               "answer", "correct", "correct_answer", "correctAnswer", "solution", "key")
EXPLAIN_KEYS = ("explanation", "rationale", "feedback", "why", "reason", "back", "note")


def first(d: dict, keys, default=None):
    for k in keys:
        if isinstance(d, dict) and d.get(k) not in (None, ""):
            return d[k]
    return default


def find_questions(raw):
    """raw のどこかにある質問リストを返す。"""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for k in Q_LIST_KEYS:
            v = raw.get(k)
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v
            if isinstance(v, dict):  # {"quiz": {"questions": [...]}} のような入れ子
                inner = find_questions(v)
                if inner:
                    return inner
        # 最後の手段: dict 値の中で「質問らしいリスト」を探す
        for v in raw.values():
            if isinstance(v, (list, dict)):
                inner = find_questions(v)
                if inner:
                    return inner
    return None


def normalize_choice(c):
    """選択肢を (text, is_correct) に正規化。is_correct が無ければ None。"""
    if isinstance(c, str):
        return c, None
    if isinstance(c, dict):
        text = first(c, CHOICE_TEXT_KEYS)
        if text is None:
            # 値が1つだけの dict なら、それを採用
            vals = [v for v in c.values() if isinstance(v, str)]
            text = vals[0] if vals else json.dumps(c, ensure_ascii=False)
        flag = first(c, CORRECT_FLAG_KEYS)
        is_correct = bool(flag) if flag is not None else None
        return str(text), is_correct
    return str(c), None


def resolve_answer_index(q, choice_texts, correct_flags):
    # 1) 選択肢自体に correct フラグがある場合
    for i, f in enumerate(correct_flags):
        if f:
            return i
    # 2) answer 系キーから判定
    ans = first(q, ANSWER_KEYS)
    if ans is None:
        return None
    if isinstance(ans, bool):
        return None
    if isinstance(ans, int):
        return ans if 0 <= ans < len(choice_texts) else None
    if isinstance(ans, dict):
        ans = first(ans, CHOICE_TEXT_KEYS, default=first(ans, ("index", "value")))
    s = str(ans).strip()
    # "A"/"B"... や "1"
    if re.fullmatch(r"[A-Za-z]", s):
        idx = ord(s.upper()) - ord("A")
        return idx if 0 <= idx < len(choice_texts) else None
    if re.fullmatch(r"\d+", s):
        idx = int(s)
        # 1始まりの可能性も考慮
        if 0 <= idx < len(choice_texts):
            return idx
        if 1 <= idx <= len(choice_texts):
            return idx - 1
    # 選択肢テキストと一致
    for i, t in enumerate(choice_texts):
        if t.strip() == s:
            return i
    return None


def normalize(raw) -> list[dict]:
    qs = find_questions(raw)
    if not qs:
        sys.exit("質問リストが見つかりませんでした。raw JSON の構造を確認してください。\n"
                 f"トップレベルのキー: {list(raw)[:20] if isinstance(raw, dict) else type(raw)}")
    out = []
    for n, q in enumerate(qs, 1):
        if not isinstance(q, dict):
            continue
        text = first(q, Q_TEXT_KEYS)
        raw_choices = first(q, CHOICE_KEYS, default=[])
        pairs = [normalize_choice(c) for c in raw_choices]
        choice_texts = [p[0] for p in pairs]
        correct_flags = [p[1] for p in pairs]
        ans_idx = resolve_answer_index(q, choice_texts, correct_flags)
        explanation = first(q, EXPLAIN_KEYS, default="")

        if not text or len(choice_texts) < 2 or ans_idx is None:
            sys.exit(
                f"第{n}問をうまく変換できませんでした(問題文/選択肢/正解のいずれかが不明)。\n"
                f"この問題の生データ:\n{json.dumps(q, ensure_ascii=False, indent=2)[:1500]}\n"
                "→ normalize_quiz.py のキー候補(Q_TEXT_KEYS 等)に実際のキー名を追加してください。")

        out.append({
            "id": f"q{n}",
            "question": str(text).strip(),
            "choices": choice_texts,
            "answerIndex": ans_idx,
            "explanation": str(explanation).strip(),
        })
    return out


def slugify(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s or "x"


def next_quiz_id(section: dict, subject_id: str, section_id: str) -> str:
    nums = []
    for q in section.get("quizzes", []):
        m = re.search(r"-(\d+)$", q.get("id", ""))
        if m:
            nums.append(int(m.group(1)))
    n = (max(nums) + 1) if nums else 1
    return f"{subject_id}-{section_id}-{n:02d}"


def update_manifest(manifest_path: Path, *, subject_id, subject_name,
                    section_id, section_name, quiz_entry):
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {"subjects": []}

    subj = next((s for s in manifest["subjects"] if s["id"] == subject_id), None)
    if not subj:
        subj = {"id": subject_id, "name": subject_name, "sections": []}
        manifest["subjects"].append(subj)
    elif subject_name:
        subj["name"] = subject_name

    sec = next((x for x in subj["sections"] if x["id"] == section_id), None)
    if not sec:
        sec = {"id": section_id, "name": section_name, "quizzes": []}
        subj["sections"].append(sec)
    elif section_name:
        sec["name"] = section_name

    # 同じ id があれば置き換え、無ければ追記
    sec["quizzes"] = [q for q in sec["quizzes"] if q["id"] != quiz_entry["id"]]
    sec["quizzes"].append(quiz_entry)

    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
    return sec


def main() -> None:
    p = argparse.ArgumentParser(description="NotebookLM クイズ raw JSON をアプリ用に正規化")
    p.add_argument("raw", help="NotebookLM からダウンロードした raw quiz JSON")
    p.add_argument("--subject", required=True, help="教科スラッグ (例 shakai)")
    p.add_argument("--subject-name", default="", help="教科の表示名 (例 社会)")
    p.add_argument("--section", required=True, help="単元スラッグ (例 edo)")
    p.add_argument("--section-name", default="", help="単元の表示名 (例 江戸時代)")
    p.add_argument("--title", required=True, help="クイズの表示名")
    p.add_argument("--id", help="クイズ ID(省略時は <教科>-<節>-連番 を自動採番)")
    p.add_argument("--docs", default="docs", help="公開サイトのルート(既定 docs)")
    args = p.parse_args()

    raw = json.loads(Path(args.raw).read_text(encoding="utf-8"))
    questions = normalize(raw)

    docs = Path(args.docs)
    manifest_path = docs / "quizzes" / "manifest.json"

    # ID 採番のため、まず既存マニフェストの該当セクションを読む
    existing = {"quizzes": []}
    if manifest_path.exists():
        m = json.loads(manifest_path.read_text(encoding="utf-8"))
        subj = next((s for s in m.get("subjects", []) if s["id"] == args.subject), None)
        if subj:
            existing = next((x for x in subj["sections"] if x["id"] == args.section), existing)
    quiz_id = args.id or next_quiz_id(existing, args.subject, args.section)

    rel_path = f"{args.subject}/{args.section}/{quiz_id}.json"
    out_path = docs / "quizzes" / rel_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    quiz_obj = {
        "id": quiz_id,
        "subject": args.subject,
        "section": args.section,
        "title": args.title,
        "createdAt": dt.date.today().isoformat(),
        "questions": questions,
    }
    out_path.write_text(json.dumps(quiz_obj, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")

    quiz_entry = {
        "id": quiz_id,
        "title": args.title,
        "count": len(questions),
        "createdAt": quiz_obj["createdAt"],
        "path": rel_path,
    }
    update_manifest(manifest_path, subject_id=args.subject, subject_name=args.subject_name,
                    section_id=args.section, section_name=args.section_name,
                    quiz_entry=quiz_entry)

    print(f"作成: {out_path}  ({len(questions)} 問)")
    print(f"更新: {manifest_path}")
    print(f"クイズ ID: {quiz_id}")


if __name__ == "__main__":
    main()
