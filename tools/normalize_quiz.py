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
import random
import re
import sys
from pathlib import Path

# 正規化先アプリスキーマ:
# { id, subject, section, title, createdAt, questions:[{id, question, choices[], answerIndex, explanation}] }

Q_LIST_KEYS = ("questions", "items", "quiz", "data", "cards")
Q_TEXT_KEYS = ("question", "prompt", "text", "stem", "title", "front")
# NotebookLM の実フォーマットは選択肢が "answerOptions"(各要素 text/isCorrect/rationale)
CHOICE_KEYS = ("answerOptions", "choices", "options", "answers", "candidates", "distractors")
CHOICE_TEXT_KEYS = ("text", "label", "option", "value", "content", "answer")
CHOICE_RATIONALE_KEYS = ("rationale", "explanation", "feedback", "reason", "why")
CORRECT_FLAG_KEYS = ("isCorrect", "correct", "is_correct", "is_answer")
ANSWER_KEYS = ("answerIndex", "answer_index", "correctIndex", "correct_index",
               "answer", "correct", "correct_answer", "correctAnswer", "solution", "key")
EXPLAIN_KEYS = ("explanation", "feedback", "why", "reason", "back", "note")


def first(d: dict, keys, default=None):
    for k in keys:
        if isinstance(d, dict) and d.get(k) not in (None, ""):
            return d[k]
    return default


def clean_text(s):
    """NotebookLM が付ける数式記法を読める文字に直す。
    - デリミタ $...$ を除去(例: "第 $25$ 条" → "第 25 条")
    - 分数 \\frac{2}{3} を「3分の2」に変換(アプリは数式を描画しないため)"""
    if not s:
        return s
    s = re.sub(r"\$\s*([^$]*?)\s*\$", r"\1", str(s))
    s = re.sub(r"\\[dt]?frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}", r"\2分の\1", s)
    return s.strip()


def to_bool(v: object) -> bool | None:
    """真偽値らしき値を bool に変換。文字列の "false"/"0"/"no" 等は偽として扱う。
    既知リスト外の文字列は None を返す(サイレントに True 化するのを防ぐ)。"""
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("false", "0", "no", "n", "incorrect", "×", "x", ""):
            return False
        if s in ("true", "1", "yes", "y", "correct", "○", "o"):
            return True
        return None  # 未知の文字列はフラグ無しとして扱う
    return bool(v)


def valid_slug(s: str) -> bool:
    """教科/単元/クイズID に使える安全な文字だけか(ディレクトリ名・URL・HTML属性になる)。"""
    return bool(re.fullmatch(r"[A-Za-z0-9_-]+", s or ""))


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
    """選択肢を (text, is_correct, rationale) に正規化。is_correct が無ければ None。"""
    if isinstance(c, str):
        return c, None, ""
    if isinstance(c, dict):
        text = first(c, CHOICE_TEXT_KEYS)
        if text is None:
            # 値が1つだけの dict なら、それを採用
            vals = [v for v in c.values() if isinstance(v, str)]
            text = vals[0] if vals else json.dumps(c, ensure_ascii=False)
        flag = first(c, CORRECT_FLAG_KEYS)
        is_correct = to_bool(flag) if flag is not None else None
        rationale = first(c, CHOICE_RATIONALE_KEYS, default="")
        return str(text), is_correct, str(rationale)
    return str(c), None, ""


def resolve_answer_index(q, choice_texts, correct_flags):
    # 1) 選択肢自体に correct フラグがある場合（ちょうど1つだけ true を要求）
    true_idxs = [i for i, f in enumerate(correct_flags) if f]
    if len(true_idxs) == 1:
        return true_idxs[0]
    if len(true_idxs) > 1:
        return None  # 複数が正解扱い＝曖昧。None を返してエラーにし、親に気づかせる
    # 2) フラグが無い場合は answer 系キーから判定
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
        text = clean_text(first(q, Q_TEXT_KEYS))
        raw_choices = first(q, CHOICE_KEYS, default=[])
        pairs = [normalize_choice(c) for c in raw_choices]
        choice_texts = [clean_text(p[0]) for p in pairs]
        correct_flags = [p[1] for p in pairs]
        rationales = [p[2] for p in pairs]
        ans_idx = resolve_answer_index(q, choice_texts, correct_flags)

        # 問題単位の explanation が無ければ、正解選択肢の rationale を解説に使う
        explanation = first(q, EXPLAIN_KEYS, default="")
        if not explanation and ans_idx is not None and 0 <= ans_idx < len(rationales):
            explanation = rationales[ans_idx]
        explanation = clean_text(explanation)

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
            # 選択肢ごとの「なぜ正解/不正解か」(choices と同じ並び)。誤答時の解説に使う
            "rationales": [clean_text(r) or "" for r in rationales],
            "hint": clean_text(first(q, ("hint",), default="")) or "",
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


# 教材が手元にないと解けない/意味が通らない表現 (例:「教材によると」「資料にないもの」)
SOURCE_WORDS = ("教材", "資料", "テキスト", "ソース", "本文", "練習問題")


def check_questions(questions: list[dict]) -> list[str]:
    """正規化後の問題を機械的に検査し、人が見直すべき点を文章のリストで返す。"""
    warns = []
    seen = {}
    for q in questions:
        qid = q["id"]
        texts = [q["question"], *q["choices"], q["explanation"], *q["rationales"], q["hint"]]
        joined = " ".join(texts)
        words = [w for w in SOURCE_WORDS if w in joined]
        if words:
            warns.append(f"{qid}: 教材を前提にした表現があります ({'・'.join(words)}): {q['question'][:40]}")
        if "\\" in joined or "$" in joined:
            warns.append(f"{qid}: 数式記法が残っています (\\ や $): {q['question'][:40]}")
        if len(q["choices"]) != 4:
            warns.append(f"{qid}: 選択肢が {len(q['choices'])} 個です (4個を想定)")
        if len(set(q["choices"])) != len(q["choices"]):
            warns.append(f"{qid}: 同じ文言の選択肢があります")
        if not q["explanation"]:
            warns.append(f"{qid}: 解説がありません")
        key = re.sub(r"\W", "", q["question"])
        if key in seen:
            warns.append(f"{qid}: {seen[key]} と問題文が同じです")
        seen[key] = qid
    return warns


def import_quiz(raw_path, *, subject, section, title, month, quiz_id=None,
                subject_name="", section_name="", docs="docs"):
    """raw JSON 1本を正規化して docs/quizzes/ に書き、manifest.json を更新する。
    戻り値は (出力パス, クイズID, 問題リスト)。変換できない場合は SystemExit。"""
    raw = json.loads(Path(raw_path).read_text(encoding="utf-8"))
    questions = normalize(raw)
    # NotebookLM は正解を先頭に並べるため、選択肢をシャッフルして answerIndex を再計算
    # (choices と rationales は同じ並びで動かす)
    for q in questions:
        order = list(range(len(q["choices"])))
        random.shuffle(order)
        q["choices"] = [q["choices"][i] for i in order]
        q["rationales"] = [q["rationales"][i] for i in order]
        q["answerIndex"] = order.index(q["answerIndex"])

    docs = Path(docs)
    manifest_path = docs / "quizzes" / "manifest.json"

    # ID 採番のため、まず既存マニフェストの該当セクションを読む
    existing = {"quizzes": []}
    if manifest_path.exists():
        m = json.loads(manifest_path.read_text(encoding="utf-8"))
        subj = next((s for s in m.get("subjects", []) if s["id"] == subject), None)
        if subj:
            existing = next((x for x in subj["sections"] if x["id"] == section), existing)
    quiz_id = quiz_id or next_quiz_id(existing, subject, section)

    rel_path = f"{subject}/{section}/{quiz_id}.json"
    out_path = docs / "quizzes" / rel_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 同じ ID の再取り込みでは、最初の作成日を引き継ぐ
    created_at = dt.date.today().isoformat()
    if out_path.exists():
        created_at = json.loads(out_path.read_text(encoding="utf-8")).get("createdAt", created_at)

    quiz_obj = {
        "id": quiz_id,
        "subject": subject,
        "section": section,
        "title": title,
        "createdAt": created_at,
        "questions": questions,
    }
    out_path.write_text(json.dumps(quiz_obj, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")

    quiz_entry = {
        "id": quiz_id,
        "title": title,
        "count": len(questions),
        "month": month,
        "createdAt": created_at,
        "path": rel_path,
    }
    update_manifest(manifest_path, subject_id=subject, subject_name=subject_name,
                    section_id=section, section_name=section_name,
                    quiz_entry=quiz_entry)
    return out_path, quiz_id, questions


def main() -> None:
    p = argparse.ArgumentParser(description="NotebookLM クイズ raw JSON をアプリ用に正規化")
    p.add_argument("raw", help="NotebookLM からダウンロードした raw quiz JSON")
    p.add_argument("--subject", required=True, help="教科スラッグ (例 shakai)")
    p.add_argument("--subject-name", default="", help="教科の表示名 (例 社会)")
    p.add_argument("--section", required=True, help="単元スラッグ (例 edo)")
    p.add_argument("--section-name", default="", help="単元の表示名 (例 江戸時代)")
    p.add_argument("--title", required=True, help="クイズの表示名")
    p.add_argument("--month", help="出題月 YYYY-MM (省略時は今月)")
    p.add_argument("--id", help="クイズ ID(省略時は <教科>-<節>-連番 を自動採番)")
    p.add_argument("--docs", default="docs", help="公開サイトのルート(既定 docs)")
    args = p.parse_args()

    # スラッグ検証(ディレクトリ名・URL・HTML属性に使うため安全な文字に限定)
    for label, val in (("--subject", args.subject), ("--section", args.section)):
        if not valid_slug(val):
            sys.exit(f"{label} は英数字・ハイフン・アンダースコアのみ使えます: {val!r}")
    if args.id and not valid_slug(args.id):
        sys.exit(f"--id は英数字・ハイフン・アンダースコアのみ使えます: {args.id!r}")

    # 出題月の正規化・検証 (YYYY-MM)
    if args.month:
        month_val = args.month
        if not re.fullmatch(r"\d{4}-(?:0[1-9]|1[0-2])", month_val):
            sys.exit(f"--month は YYYY-MM 形式で指定してください (例: 2026-06): {month_val!r}")
    else:
        month_val = dt.date.today().strftime("%Y-%m")
        print(f"[警告] --month が省略されました。今月 {month_val} を使います"
              f"（再取り込み時は --month を明示してください）。", file=sys.stderr)

    out_path, quiz_id, questions = import_quiz(
        args.raw, subject=args.subject, subject_name=args.subject_name,
        section=args.section, section_name=args.section_name,
        title=args.title, month=month_val, quiz_id=args.id, docs=args.docs)

    print(f"作成: {out_path}  ({len(questions)} 問)")
    print(f"クイズ ID: {quiz_id}")
    for w in check_questions(questions):
        print(f"[要確認] {w}")


if __name__ == "__main__":
    main()
