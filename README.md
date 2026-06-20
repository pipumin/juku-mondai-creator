# 受験クイズ (juku-mondai-creator)

子どもの受験勉強用に、教材テキストから **選択式クイズ** を作って Web で解いてもらうための最小アプリ。

- **生成**: NotebookLM にテキストを取り込み、クイズを生成 → JSON で取り出す(親 or Claude が事前に実行）。
- **アプリ**: 教科 → 単元 → クイズ を選んで解く静的Webサイト。即時採点・解説・間違い復習・進捗記録つき。

```
テキスト ─▶ NotebookLM ─▶ raw JSON ─▶ normalize_quiz.py ─▶ docs/quizzes/<教科>/<単元>/*.json ─▶ Webアプリ
         (generate_quiz.py)                              (+ manifest.json 自動更新）        (Cloudflare Pages)
```

---

## 1. セットアップ（最初の一度だけ）

```powershell
py -3 -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

NotebookLM へのログインは **対話入力が必要** なので、PowerShell/Windows Terminal を別に開いて実行する:

```powershell
notebooklm login   # ブラウザでGoogleログイン → 完了後にENTER
notebooklm status  # "Authenticated as: ..." を確認
```

> Windows では日本語出力の文字化け・クラッシュを防ぐため、`notebooklm` や Python スクリプトは
> 環境変数 `PYTHONIOENCODING=utf-8` を付けて実行する（`generate_quiz.py` は内部で付与済み）。
> PowerShell でコンソール表示も整えたいときは `,$env:PYTHONIOENCODING="utf-8"` を先に実行。

---

## 2. クイズを1本追加する（親の作業）

### a. 教材テキストを用意
`data/raw/edo-source.txt` のようにテキスト（または PDF / URL）を置く。

### b. NotebookLM でクイズ生成 → raw JSON 取得
```powershell
py -3 tools/generate_quiz.py `
  --text data/raw/edo-source.txt `
  --title "受験クイズ: 社会 江戸時代" `
  --out  data/raw/edo-quiz.json
```
> クイズ生成は Google 側で **5〜15分** かかり、レート制限で失敗することもある。
> 失敗時は時間を空けて再実行するか、NotebookLM の Web UI で生成して
> 「ダウンロード（JSON）」したものを `--out` の場所に置いてもよい。

### c. アプリ用に正規化（教科・単元を指定。manifest は自動更新）
```powershell
py -3 tools/normalize_quiz.py data/raw/edo-quiz.json `
  --subject shakai --subject-name "社会" `
  --section edo    --section-name "江戸時代" `
  --title "江戸時代の基礎"
```
→ `docs/quizzes/shakai/edo/shakai-edo-01.json` が作られ、`docs/quizzes/manifest.json` に
   教科・単元・クイズが自動で追記される（**手で manifest を編集しなくてよい**）。
   クイズIDは省略時 `<教科>-<単元>-連番` で自動採番。

> `generate_quiz.py` がうまく変換できないと言われた場合は、その raw JSON の構造に合わせて
> `tools/normalize_quiz.py` 先頭のキー候補（`Q_TEXT_KEYS` など）に実際のキー名を足す。

---

## 3. ローカルで確認

```powershell
py -3 -m http.server 8000 --directory docs
# ブラウザで http://localhost:8000 を開く
```
（`file://` で直接開くと JSON 読み込みがブロックされるので、必ずサーバ経由で開く）

---

## 4. ネットに公開（Cloudflare Pages）

```powershell
npx wrangler login                                   # 初回のみ（ブラウザ認証）
npx wrangler pages deploy docs --project-name juku-quiz
```
発行された `https://juku-quiz.pages.dev/` をタブレット/スマホで開く。
クイズを足したら `docs` を再度 deploy するだけ。

> **公開範囲・著作権**: 教科書本文そのままの公開は避け、学習用に要約・改変した自作問題にとどめる。
> URL は家族内のみで共有する。完全に非公開にしたい場合は Cloudflare の **Access**（無料）を有効化し、
> 家族のメールだけ許可するとサイト全体にログインがかかる（将来の「複数ユーザ／簡単ログイン」もこれで対応可能）。

---

## ディレクトリ構成

```
docs/                     公開する静的サイト（Cloudflare Pages のルート）
  index.html / app.js / styles.css
  quizzes/
    manifest.json         教科→単元→クイズ の一覧（自動生成）
    <教科>/<単元>/<id>.json  正規化済みクイズ
tools/
  generate_quiz.py        NotebookLM でクイズ生成 → raw JSON
  normalize_quiz.py       raw JSON → アプリ用JSON + manifest更新
data/raw/                 生成元テキスト・raw JSON（gitignore。公開しない）
```

## 進捗データについて
解答の進捗（前回スコア・続き・間違えた問題）は **ブラウザの localStorage** に保存される。
端末ごとに独立で、端末間では同期しない（MVPの割り切り）。
将来クラウド同期したい場合は Cloudflare Pages Functions + KV/D1 を `app.js` の
`loadProgress`/`saveProgress` 差し替えで追加できる。
