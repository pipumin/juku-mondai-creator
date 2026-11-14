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
   { "id": "shakai-rekishi-01", "title": "4月社会_歴史クイズ", "month": "2026-04",
     "source": "小6EXE_4月_社会.pdf", "range": "鎌倉時代（歴史）" }
   ```
   - `source` は生成に使う教材（NotebookLM 上のソース名）、`range` はその中の単元。
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
   - 問題数を増やしたいなど、NotebookLM で作り直すときは、ジョブに `"quantity": "more"` を書いて
     `py -3 tools/import_all.py --regenerate --only <id>`。前の元データは `data/raw/_original/` に退避される。
     「多め」でも1回に作られるのは25〜30問ほど。さらに増やすときは、すでに出した答えを `range` に
     「これらは出題済みなので避ける」と書いて別に生成し、元データを合わせる（3月号の社会はこの方法で計81問にした）。

Web 画面で作ったクイズも、NotebookLM 上の名前を `title` と同じにしておけば同じコマンドで取り込める。
1本だけ手で変換したい場合は `tools/normalize_quiz.py`（`--help` 参照）。

### 毎月の流れ（社会の例）

新しい月号の PDF をもらってから公開するまで。社会だけなら 20〜30 分（大半は NotebookLM の生成待ち）。

| | やること | コマンド・場所 |
|---|---|---|
| 1 | 月号の PDF を `data/raw/` に置く | 例 `data/raw/小６EXE７月_本誌.pdf` |
| 2 | 社会のページ範囲を調べて切り出す | `py -3 tools/split_pdf.py "data/raw/小６EXE７月_本誌.pdf" --prefix 小6EXE_7月 --range 社会=53-79` |
| 3 | 切り出した PDF を NotebookLM に入れる | `notebooklm source add "data/raw/split/小6EXE_7月_社会.pdf" --notebook 48ef6af9-2c78-4cda-826d-5568e8144d93` |
| 4 | PDF の「要点のまとめ」を見て、単元ごとにジョブを書く | `quiz-jobs.json`（下の例） |
| 5 | 生成して取り込む | `py -3 tools/import_all.py --generate` |
| 6 | `[要確認]` を直し、ローカルで解いてみる | 「3. ローカルで確認」 |
| 7 | 公開する | 「4. ネットに公開」 |

手順 4 の例。7月号の社会に「近畿地方（地理）」と「室町時代（歴史）」の2単元があった場合:

```json
{ "id": "shakai-chiri-02",   "title": "7月社会_地理クイズ", "month": "2026-07",
  "source": "小6EXE_7月_社会.pdf", "range": "近畿地方" },
{ "id": "shakai-rekishi-02", "title": "7月社会_歴史クイズ", "month": "2026-07",
  "source": "小6EXE_7月_社会.pdf", "range": "室町時代" }
```

`notebooklm` と打って「アプリケーション制御ポリシーによってブロック」と出る PC では、
`& "$HOME\pipx\venvs\notebooklm-py\Scripts\python.exe" -m notebooklm …` と打つ（`import_all.py` は自動でこちらを使う）。

### PDF を置くだけでは動かない（人が決めること）

`data/raw/` に PDF を置いただけでは何も起きない。次の3つは人が決めて、手順 2 と 4 で指定する。

- **社会が何ページから何ページか。** 月号は4教科が1冊になっていて、目次の情報が PDF に入っていない。
- **地理・歴史・公民のどれか（`id` の真ん中）。** アプリの「教科 → 単元」のメニューがこれで決まる。
  `chiri`=地理 / `rekishi`=歴史 / `koumin`=公民。指定は必須で、自動では判別しない。
- **単元名（`range`）。** 1冊の社会に複数の単元が入っているので、単元ごとに1ジョブに分ける。
  分けずに作ると問題が浅く広くなる。実際に載っている単元名を書くこと
  （載っていない単元を書くと、関連する数問しか作られない。4月の歴史が5問なのはこのため）。

Claude Code に「7月号を `data/raw/` に置いたので社会を取り込んで」と頼めば、ページ範囲と単元の確認から
手順 2〜6 までを任せられる（NotebookLM へのログインが切れているときだけ `notebooklm login` が必要）。

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

## クイズの中断と再開
- 出題中の右上の **「中断する」** を押すと、そこまでの回答を保存してクイズ一覧に戻る。
- 中断したクイズは、最初の画面の **「とちゅうのクイズ」** と、クイズ一覧の **「続きから」** から、
  同じ問題・同じ選択肢の並びで再開できる。期限はなく、最後まで解くか「最初から」を選ぶまで残る。
- 「最初から」を選ぶと、確認のうえでとちゅうの記録を消してやり直す。
- 回答のたびに自動保存しているので、「中断する」を押さずにブラウザを閉じても同じように再開できる。
- 中断中でも「間違いだけ復習」はでき、復習を終えても中断の記録は消えない。
- クイズの中身を作り直した場合（問題数や選択肢の数が変わった場合）は、古い中断の記録は使わず最初からになる。

## 複数人で使うとき

**解く人が複数いる場合**
- はじめて開いたときに名前を聞く。右上の **「👤 なまえ」** を押すと、使う人の切り替え・追加・削除ができる。
  前回スコア・中断・間違えた問題は、人ごとに別々に記録される。
- 名前を選ぶだけで、パスワードもサーバー（DB）も無い。名前と記録は **その端末のそのブラウザの中だけ** にある。
  - 自分の端末で使う友達は、最初に一度名前を入れるだけ。次からは自動でその人のまま開く。
  - 1台を2人で使うときは、右上の名前を押して切り替える。
- 端末を替えると記録は引き継がれない（同じ名前を入れても別の記録になる）。ブラウザの閲覧データを消すと記録も消える。
- 親がほかの人の進み具合を自分の端末から見ることはできない。これらが必要になったら、
  記録をサーバーに置く仕組み（ログイン + DB）が要る。`app.js` の `loadProgress`/`saveProgress` と
  「利用者」の関数を差し替える形で追加できる。

**クイズを作る人が複数いる場合**
- NotebookLM のノートブックは作成者の Google アカウントのもの。別の人が `import_all.py --generate` を使うには、
  その人のアカウントにノートブックを共有するか、自分のノートブックを作って `quiz-jobs.json` の `notebook` を書き換える。
- 2人が同じ時期にクイズを足すと、`quiz-jobs.json` と `docs/quizzes/manifest.json` の同じ場所を書き換えるので、
  `git push` でぶつかる。**作業の前に `git pull`、終わったらすぐ `git push`** を守り、同時には作業しない。
- `id` の連番（`shakai-koumin-04` など）は手で決めるので、同じ番号を2人が使わないこと
  （同じ `id` で取り込むと、後から取り込んだほうで上書きされる）。
- `data/raw/`（教材 PDF と元データ）は git に入らない。別の PC で作業する人には、ファイルを別途渡す必要がある。

## 進捗データについて
解答の進捗（前回スコア・続き・間違えた問題）は **ブラウザの localStorage** に、利用者ごとに保存される
（キーは `progress:<利用者ID>:<クイズID>`。利用者の一覧は `profiles`、いまの利用者は `currentProfile`）。
端末ごとに独立で、端末間では同期しない。
