# NotebookLM 投入ファイルとプロンプト一覧（小6 EXE 4〜6月）

`data/raw/split/` に教科ごとに分割した PDF を置いてあります。これを NotebookLM に入れ、
**単元ごとに1本ずつ**クイズを作るのが高精度のコツです。

## 共通の流れ
1. notebooklm.google.com の「塾問題」ノートブックを開く（または CLI: `notebooklm source add "data/raw/split/<ファイル>" --notebook 48ef6af9-2c78-4cda-826d-5568e8144d93`）。
2. Studio →「クイズ」→「カスタマイズ」欄に下の**共通プロンプト**（【範囲】を単元名に差し替え）を貼って生成。
3. JSON で取得：
   ```powershell
   $NB="48ef6af9-2c78-4cda-826d-5568e8144d93"
   notebooklm artifact list --notebook $NB     # 今作った Quiz の id を確認
   notebooklm download quiz "data/raw/<単元>-quiz.json" -n $NB -a <artifact_id>
   ```
4. アプリへ取り込み（各単元の `normalize` 行を実行）。
5. `http://localhost:8000` で確認 → `npx wrangler pages deploy docs` で公開。

> 投入は **1ファイル=1教科**。クイズ生成は **1単元ずつ**（プロンプトの【範囲】で絞る）。混ぜると精度が落ちます。

## 共通プロンプト（雛形）
```
あなたは中学受験(小6)の作問者です。アップロードした教材のうち【範囲】の内容だけを使って、4択クイズを10問作成してください。
条件:
- 教材に書かれている事実だけを使い、教材外の知識や推測は使わない
- 各問の選択肢は4つ、正解は1つだけ。誤答は受験生がやりがちな誤りにする
- 各選択肢に「なぜ正解/なぜ不正解か」を1〜2文で必ず付ける
- 難易度は標準（基礎〜入試標準）。用語・しくみ・分類の理解を中心に
- 1問ずつ「問題文／4つの選択肢／正解／各選択肢の解説」がそろう形式で出力
```

## 教科別のコツ
- **算数**: 4択は「計算結果を選ぶ」「切断面の形・展開図・図形の性質を選ぶ」など選択式向きの問い方に。プロンプト末尾に「計算問題は最終的な数値を4択で問う」を足すと安定。
- **国語**: 知識系（ことわざ・四字熟語・敬語・品詞・漢字）が4択に最適。**読解（物語・論説）は本文依存で4択化が難しい**ので優先度低め。やるなら「本文中の語句の意味」「指示語の指す内容」に限定。
- **理科**: 用語・分類・実験の考察が4択向き。
- **社会**: 用語・制度・人物・地名。地理/歴史/公民に分けて出題。

## 教科スラッグ早見表
- 算数=`sansu` / 理科=`rika` / 社会=`shakai`（節は 地理`chiri`・歴史`rekishi`・公民`koumin`）/ 国語=`kokugo`（節は 語句`goku`・文法`bunpou`・読解`dokkai`）

---

# 4月号

### data/raw/split/小6EXE_4月_算数.pdf → 算数(sansu)
| 単元(=【範囲】) | section | normalize 例 |
|---|---|---|
| 仕事算・のべ算 | shigotozan | `--subject sansu --subject-name 算数 --section shigotozan --section-name 仕事算 --title "仕事算"` |
| 素数と素因数分解 | sosuu-bunkai | `--section sosuu-bunkai --section-name 素因数分解 --title "素数と素因数分解"` |
| 立方体と直方体の切断 | setsudan | `--section setsudan --section-name 立体の切断 --title "立方体と直方体の切断"` |

### data/raw/split/小6EXE_4月_理科.pdf → 理科(rika)
| 単元(=【範囲】) | section |
|---|---|
| 光・音 | hikari-oto |
| 燃焼・熱 | nensho-netsu |
| 動物（昆虫・恒温/変温動物） | doubutsu |

### data/raw/split/小6EXE_4月_社会.pdf → 社会(shakai)
| 単元(=【範囲】) | section |
|---|---|
| 日本の地方・農業（地理） | chiri |
| 鎌倉時代（歴史） | rekishi |
| 日本国憲法・基本的人権・国会（公民） | koumin |

### data/raw/split/小6EXE_4月_国語.pdf → 国語(kokugo)
| 単元(=【範囲】) | section |
|---|---|
| ことわざ・慣用句・四字熟語 | goku |
| 読解（物語・論説）※任意・優先度低 | dokkai |

---

# 5月号

### data/raw/split/小6EXE_5月_算数.pdf → 算数(sansu)
| 単元(=【範囲】) | section |
|---|---|
| いろいろな立体の見方（投影図） | rittai-mikata |
| 立体図形（展開図・回転体） | rittai-zukei |

### data/raw/split/小6EXE_5月_理科.pdf → 理科(rika)
| 単元(=【範囲】) | section |
|---|---|
| 地層・火山・地震 | chisou |
| 運動・てこ | undou-teko |
| 気体・金属 | kitai-kinzoku |
| 人体（誕生と成長・血液循環・消化） | jintai |

### data/raw/split/小6EXE_5月_社会.pdf → 社会(shakai)
| 単元(=【範囲】) | section |
|---|---|
| 政治のしくみ（内閣・裁判所・三権分立・地方自治）（公民） | koumin |

### data/raw/split/小6EXE_5月_国語.pdf → 国語(kokugo)
| 単元(=【範囲】) | section |
|---|---|
| 主語・述語・修飾語／品詞 | bunpou |
| 漢字の知識・和語漢語外来語・重要なことば | goku |
| 読解 ※任意・優先度低 | dokkai |

---

# 6月号

### data/raw/split/小6EXE_6月_算数.pdf → 算数(sansu)
| 単元(=【範囲】) | section |
|---|---|
| 容器と水量 | suiryou |
| 速さ1（速さと比・通過算） | hayasa1 |
| 速さ2（旅人算・時計算） | hayasa2 |
| 速さ3（流水算・動く歩道） | hayasa3 |

### data/raw/split/小6EXE_6月_理科.pdf → 理科(rika)
| 単元(=【範囲】) | section |
|---|---|
| 気象（天気・台風・熱中症） | kishou |
| 滑車・ばね・浮力 | kassha-bane |
| 生物総合 | seibutsu |
| 化学総合（水溶液・中和・気体） | kagaku |

### data/raw/split/小6EXE_6月_社会.pdf → 社会(shakai)
| 単元(=【範囲】) | section | 備考 |
|---|---|---|
| 社会保障・財政と税・金融・貿易・国際（公民） | koumin | ※既存の「公民クイズ(shakai-koumin-01)」はここ由来。続きを足す形 |

### data/raw/split/小6EXE_6月_国語.pdf → 国語(kokugo)
| 単元(=【範囲】) | section |
|---|---|
| 敬語（尊敬・謙譲・丁寧）／品詞 | bunpou |
| 読解 ※任意・優先度低 | dokkai |

---

## ⚠ EXE3月①.pdf / EXE3月②.pdf について
この2冊は **全ページ画像スキャン（テキスト層なし）かつ目次（しおり）なし**でした。
- 教科の自動判別ができないため、今回は分割していません。
- NotebookLM は画像PDFをOCRして読める場合がありますが、精度は本誌（4〜6月）より落ちます。
- 対応案: ①どのページが何の教科か教えてもらえれば `split_pdf.py` で分割できます／②可能ならテキスト付きPDFで再書き出し／③重要度が低ければ後回し。

## normalize コマンドの形（共通）
```powershell
py -3 tools/normalize_quiz.py "data/raw/<ダウンロードした>.json" `
  --subject <教科slug> --subject-name <教科名> `
  --section <節slug>   --section-name <節名> `
  --title "<クイズ表示名>"
```
教科・節は無ければ自動作成、クイズIDは `<教科>-<節>-連番` で自動採番、`manifest.json` も自動更新されます。
