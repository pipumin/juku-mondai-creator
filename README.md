# 受験クイズ (juku-mondai-creator)

子どもの受験勉強用に、教材テキストから **選択式クイズ** を作って Web で解いてもらうための最小アプリ。

- **生成**: NotebookLM にテキストを取り込み、クイズを生成 → JSON で取り出す(親 or Claude が事前に実行）。
- **アプリ**: 教科 → 単元 → クイズ を選んで解く静的Webサイト。即時採点・解説・間違い復習・進捗記録つき。

```
教材PDF ─▶ NotebookLM ─▶ raw JSON ─▶ import_all.py ─▶ docs/quizzes/<教科>/<単元>/*.json ─▶ Webアプリ
 (split_pdf.py で教科別に分割)        (quiz-jobs.json を見て一括取り込み)              (GitHub Pages)
```

---

## 1. セットアップ（最初の一度だけ）

```powershell
pipx install "notebooklm-py[browser]"   # NotebookLM を操作する CLI
py -3 -m pip install -r requirements.txt  # PDF 分割用
```

NotebookLM へのログインは **対話入力が必要** なので、PowerShell/Windows Terminal を別に開いて実行する:

```powershell
notebooklm login   # ブラウザでGoogleログイン → 完了後にENTER
```

---

## 2. クイズを追加する（親の作業）

1. **教材を NotebookLM に入れる。** `tools/split_pdf.py` で教科別に分けた PDF を「塾問題」ノートブックに追加する
   （単元の一覧は [notebooklm-jobs.md](notebooklm-jobs.md)）。
2. **`quiz-jobs.json` にジョブを1つ足す。**
   ```json
   { "id": "shakai-rekishi-01", "title": "4月社会_歴史クイズ", "month": "2026-04", "range": "鎌倉時代（歴史）" }
   ```
   - `id` は `教科-単元-連番`。教科と単元はここから決まる。
   - 新しい教科・単元なら `names` に表示名も足す（例 `"shakai/rekishi": "歴史"`）。
3. **1コマンドで取り込む。**
   ```powershell
   py -3 tools/import_all.py --generate
   ```
   - NotebookLM に `title` と同じ名前のクイズがあればそれをダウンロードし、無ければ `range` の範囲で生成する
     （生成は Google 側で数分〜15分。`--generate` を外すと生成はせず、ダウンロードと取り込みだけ行う）。
   - 取り込み済みで元データが変わっていないジョブは何もしないので、何度実行してもよい。
   - `[要確認]` と出た問題は、教材が手元にないと解けない表現や数式記法が残っている。
     `data/raw/` の該当 JSON を直して、もう一度実行する。
   - やり直したいときは `--force`、1本だけなら `--only <id>`。

Web 画面で作ったクイズも、NotebookLM 上の名前を `title` と同じにしておけば同じコマンドで取り込める。
1本だけ手で変換したい場合は `tools/normalize_quiz.py`（`--help` 参照）。

---

## 3. ローカルで確認

```powershell
py -3 -m http.server 8000 --directory docs
# ブラウザで http://localhost:8000 を開く
```
（`file://` で直接開くと JSON 読み込みがブロックされるので、必ずサーバ経由で開く）

---

## 4. ネットに公開（GitHub Pages）

`master` の `docs/` がそのまま https://pipumin.github.io/juku-mondai-creator/ に公開される。

```powershell
git add docs quiz-jobs.json
git commit -m "feat: クイズを追加"
git push
```
`app.js` / `styles.css` を変えたときは、`index.html` の `?v=` の番号も上げる（端末に古いファイルが残るため）。

> **公開範囲・著作権**: リポジトリも GitHub Pages も公開で、URL を知っていれば誰でも見られる。
> 教科書本文そのままの公開は避け、学習用に要約・改変した自作問題にとどめる。
> `data/raw/`（教材 PDF と NotebookLM の元データ）は gitignore 済みで公開されない。

---

## ディレクトリ構成

```
quiz-jobs.json            取り込むクイズの一覧（import_all.py が読む）
docs/                     公開する静的サイト（GitHub Pages のルート）
  index.html / app.js / styles.css
  quizzes/
    manifest.json         教科→単元→クイズ の一覧（自動生成）
    <教科>/<単元>/<id>.json  正規化済みクイズ
tools/
  import_all.py           quiz-jobs.json のクイズを一括で生成・ダウンロード・取り込み
  normalize_quiz.py       raw JSON 1本 → アプリ用JSON + manifest更新（import_all が内部で使う）
  split_pdf.py            教材 PDF をページ範囲で教科別に分割
data/raw/                 教材 PDF・raw JSON（gitignore。公開しない）
```

## 進捗データについて
解答の進捗（前回スコア・続き・間違えた問題）は **ブラウザの localStorage** に保存される。
端末ごとに独立で、端末間では同期しない（MVPの割り切り）。
将来クラウド同期したい場合は、`app.js` の `loadProgress`/`saveProgress` を差し替えて追加できる。
