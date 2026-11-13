"use strict";

/* 受験クイズ アプリ本体。
   画面: ホーム(教科) → 節 → クイズ一覧 → 出題 → 結果。ハッシュルータで切替。
   進捗は localStorage に保存。MVP では profile は固定 "default"。
   将来ログインで profile を切り替え、保存先をクラウドへ差し替えられるよう
   進捗の読み書きは loadProgress/saveProgress に集約している。 */

const app = document.getElementById("app");
const whoBtn = document.getElementById("who");

let profile = null;           // いま使っている人 {id, name}。下記「利用者」参照

let manifest = null;          // quizzes/manifest.json の中身
let session = null;           // 出題中の状態。下記 startQuiz 参照

/* ---------------- utils ---------------- */

function esc(s) {
  return String(s).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

async function fetchJSON(url) {
  const res = await fetch(url, { cache: "no-cache" });
  if (!res.ok) throw new Error(`${url} の取得に失敗 (${res.status})`);
  return res.json();
}

/* --- 利用者 (localStorage) ---
   名前を選ぶだけの切り替え。パスワードもサーバーも無く、名前と進捗はこのブラウザの中だけにある。
   最初に登録した人の id は "default" にして、利用者機能が無かった頃の進捗を引き継ぐ。 */
function loadProfiles() {
  try {
    const list = JSON.parse(localStorage.getItem("profiles"));
    return Array.isArray(list) ? list : [];
  } catch { return []; }
}
function selectProfile(id) {
  localStorage.setItem("currentProfile", id);
  profile = loadProfiles().find((p) => p.id === id) || null;
}
function addProfile(name) {
  const list = loadProfiles();
  const id = list.length === 0 ? "default" : "u" + Date.now().toString(36);
  list.push({ id, name });
  localStorage.setItem("profiles", JSON.stringify(list));
  selectProfile(id);
}
function deleteProfile(id) {
  // その人の進捗もまとめて消す
  Object.keys(localStorage)
    .filter((k) => k.startsWith(`progress:${id}:`))
    .forEach((k) => localStorage.removeItem(k));
  const list = loadProfiles().filter((p) => p.id !== id);
  localStorage.setItem("profiles", JSON.stringify(list));
  if (profile && profile.id === id) {
    if (list.length) selectProfile(list[0].id);
    else { localStorage.removeItem("currentProfile"); profile = null; }
  }
}

/* --- 進捗 (localStorage) --- */
function progKey(quizId) { return `progress:${profile.id}:${quizId}`; }
function loadProgress(quizId) {
  try { return JSON.parse(localStorage.getItem(progKey(quizId))) || {}; }
  catch { return {}; }
}
function saveProgress(quizId, obj) {
  localStorage.setItem(progKey(quizId), JSON.stringify(obj));
}

/* --- マニフェスト探索 --- */
function findSubject(id) { return manifest.subjects.find((s) => s.id === id); }
function findSection(subj, id) { return subj && subj.sections.find((x) => x.id === id); }
function findQuizEntry(quizId) {
  for (const s of manifest.subjects)
    for (const sec of s.sections)
      for (const q of sec.quizzes)
        if (q.id === quizId) return { subject: s, section: sec, quiz: q };
  return null;
}

function crumbs(parts) {
  // parts: [{label, href?}] 末尾はリンク無し(現在地)
  const html = parts.map((p, i) => {
    const sep = i > 0 ? '<span class="sep">/</span>' : "";
    return sep + (p.href ? `<a href="${esc(p.href)}">${esc(p.label)}</a>` : `<span>${esc(p.label)}</span>`);
  }).join(" ");
  return `<nav class="crumbs">${html}</nav>`;
}

/* ---------------- 利用者の選択 ---------------- */

// 最初の1回(まだ誰も登録していない)と、ヘッダーの名前を押したときに出す画面
function renderWho() {
  const list = loadProfiles();
  const cards = list.map((p) => {
    const current = profile && profile.id === p.id;
    return `<div class="who${current ? " who--current" : ""}">
      <button class="who__pick" data-pick="${esc(p.id)}">
        <span class="who__name">👤 ${esc(p.name)}</span>
        ${current ? '<span class="badge">いま使っている人</span>' : ""}
      </button>
      <button class="who__del" data-del="${esc(p.id)}" aria-label="${esc(p.name)} を消す">消す</button>
    </div>`;
  }).join("");

  app.innerHTML = `<h1 class="page-title">${list.length ? "だれが使う?" : "なまえを教えてね"}</h1>
    ${list.length ? `<div class="grid">${cards}</div><h2 class="section-head who__addhead">新しい人を追加</h2>` : ""}
    <form class="who__form" id="whoform">
      <input id="whoname" class="who__input" maxlength="12" placeholder="なまえ (12文字まで)" autocomplete="off" />
      <button class="btn" type="submit">${list.length ? "追加" : "はじめる"}</button>
    </form>
    <p class="who__err" id="whoerr"></p>
    <p class="who__note">なまえと記録は、この端末のこのブラウザの中だけに保存されます。パスワードはありません。</p>`;

  const goHome = () => { if (location.hash === "#/" || location.hash === "") route(); else location.hash = "#/"; };

  app.querySelectorAll("[data-pick]").forEach((b) => {
    b.addEventListener("click", () => { selectProfile(b.dataset.pick); goHome(); });
  });
  app.querySelectorAll("[data-del]").forEach((b) => {
    b.addEventListener("click", () => {
      const p = list.find((x) => x.id === b.dataset.del);
      if (!confirm(`「${p.name}」と、その記録をぜんぶ消しますか? 元にはもどせません。`)) return;
      deleteProfile(p.id);
      updateWhoButton();
      renderWho();
    });
  });
  document.getElementById("whoform").addEventListener("submit", (e) => {
    e.preventDefault();
    const name = document.getElementById("whoname").value.trim();
    const err = document.getElementById("whoerr");
    if (!name) { err.textContent = "なまえを入れてください。"; return; }
    if (list.some((p) => p.name === name)) { err.textContent = "同じなまえの人がもういます。"; return; }
    addProfile(name);
    goHome();
  });
}

function updateWhoButton() {
  whoBtn.hidden = !profile;
  whoBtn.textContent = profile ? `👤 ${profile.name}` : "";
}

/* ---------------- 一覧系の描画 ---------------- */

function renderHome() {
  const cards = manifest.subjects.map((s) => {
    const nQuiz = s.sections.reduce((a, sec) => a + sec.quizzes.length, 0);
    return `<a class="card" href="#/s/${esc(s.id)}">
      <div class="card__title">${esc(s.name)}</div>
      <div class="card__meta">${s.sections.length} 単元 ・ ${nQuiz} クイズ</div>
    </a>`;
  }).join("");

  // 中断したクイズは、教科をたどらなくてもここからすぐ再開できる
  const paused = [];
  for (const s of manifest.subjects)
    for (const sec of s.sections)
      for (const q of sec.quizzes)
        if (resumable(loadProgress(q.id), q.count)) paused.push(quizRow(q, `${s.name} / ${sec.name}`));
  const pausedHtml = paused.length
    ? `<h2 class="section-head">とちゅうのクイズ</h2><div class="grid paused">${paused.join("")}</div>`
    : "";

  app.innerHTML = pausedHtml
    + `<h1 class="page-title">教科をえらぶ</h1>
    <div class="grid cols2">${cards || '<p class="empty">クイズがまだありません。</p>'}</div>`;
  bindQuizButtons();
}

// 一覧用: 中断中で再開できそうか (manifest の問題数で分かる範囲の確認。厳密な検証は startQuiz で行う)
function resumable(p, count) {
  const ip = p.inProgress;
  return !!ip && Array.isArray(ip.answers) && ip.answers.length === count
    && Array.isArray(ip.perms) && ip.perms.length === count
    && Number.isInteger(ip.index) && ip.index >= 0 && ip.index < count;
}

// クイズ1件ぶんの行 (題名・前回の結果・はじめる/続きから/復習のボタン)
function quizRow(q, where) {
  const p = loadProgress(q.id);
  const meta = (where ? `${esc(where)} ・ ` : "") + `全 ${q.count} 問`
    + (p.lastAttempt ? ` ・ 前回 ${esc(p.lastAttempt.score)}/${esc(p.lastAttempt.total)}` : "");
  const buttons = [];
  if (resumable(p, q.count)) {
    const done = p.inProgress.answers.filter((a) => a !== null && a !== undefined).length;
    buttons.push(`<button class="btn" data-act="resume" data-id="${esc(q.id)}">続きから (${done}/${q.count}問 回答ずみ)</button>`);
    buttons.push(`<button class="btn ghost" data-act="restart" data-confirm="1" data-id="${esc(q.id)}">最初から</button>`);
  } else {
    buttons.push(`<button class="btn" data-act="restart" data-id="${esc(q.id)}">はじめる</button>`);
  }
  if (p.wrongIds && p.wrongIds.length) {
    buttons.push(`<button class="btn secondary" data-act="review" data-id="${esc(q.id)}">間違いだけ復習 (${p.wrongIds.length})</button>`);
  }
  return `<div class="quizrow">
    <div class="quizrow__title">${esc(q.title)}</div>
    <div class="quizrow__meta">${meta}</div>
    <div class="btnrow">${buttons.join("")}</div>
  </div>`;
}

function bindQuizButtons() {
  app.querySelectorAll("button[data-act]").forEach((b) => {
    b.addEventListener("click", () => {
      const id = b.dataset.id;
      if (b.dataset.act === "restart") {
        // 中断中のクイズを最初からやり直すと、とちゅうの記録は消える
        if (b.dataset.confirm && !confirm("とちゅうまでの記録を消して、最初からはじめますか?")) return;
        const p = loadProgress(id); delete p.inProgress; saveProgress(id, p);
        location.hash = `#/play/${id}`;
      } else if (b.dataset.act === "resume") {
        location.hash = `#/play/${id}`;
      } else if (b.dataset.act === "review") {
        location.hash = `#/play/${id}/review`;
      }
    });
  });
}

function renderSubject(subjectId) {
  const subj = findSubject(subjectId);
  if (!subj) return renderHome();
  const cards = subj.sections.map((sec) => {
    const badge = bestBadge(sec.quizzes);
    return `<a class="card" href="#/s/${esc(subj.id)}/${esc(sec.id)}">
      <div class="card__title">${esc(sec.name)}</div>
      <div class="card__meta">${sec.quizzes.length} クイズ</div>
      ${badge}
    </a>`;
  }).join("");
  app.innerHTML = crumbs([{ label: "教科", href: "#/" }, { label: subj.name }])
    + `<h1 class="page-title">${esc(subj.name)}</h1>`
    + `<div class="grid cols2">${cards || '<p class="empty">単元がありません。</p>'}</div>`;
}

// 節カードに「前回の最高/最新結果あり」バッジを出す
function bestBadge(quizzes) {
  const done = quizzes.some((q) => loadProgress(q.id).lastAttempt);
  return done ? '<span class="badge">挑戦ずみ</span>' : "";
}

function monthLabel(ym) {
  // "2026-06" → "6月"
  return parseInt(ym.split("-")[1], 10) + "月";
}

function renderSection(subjectId, sectionId, monthFilter) {
  const subj = findSubject(subjectId);
  const sec = findSection(subj, sectionId);
  if (!sec) return renderSubject(subjectId);

  const months = [...new Set(sec.quizzes.map((q) => q.month).filter(Boolean))].sort();
  const activeMonth = (monthFilter && months.includes(monthFilter)) ? monthFilter : null;
  const filtered = activeMonth ? sec.quizzes.filter((q) => q.month === activeMonth) : sec.quizzes;

  let pillsHtml = "";
  if (months.length > 1 || activeMonth) {
    const base = `#/s/${esc(subj.id)}/${esc(sec.id)}`;
    const pills = [
      `<a class="pill${!activeMonth ? " pill--active" : ""}" href="${base}">全て</a>`,
      ...months.map((m) =>
        `<a class="pill${activeMonth === m ? " pill--active" : ""}" href="${base}/${esc(m)}">${monthLabel(m)}</a>`
      ),
    ].join("");
    pillsHtml = `<div class="filter-pills">${pills}</div>`;
  }

  const rows = filtered.map((q) => quizRow(q)).join("");

  app.innerHTML = crumbs([
    { label: "教科", href: "#/" },
    { label: subj.name, href: `#/s/${subj.id}` },
    { label: sec.name },
  ])
    + `<h1 class="page-title">${esc(sec.name)}</h1>`
    + pillsHtml
    + `<div class="grid">${rows || '<p class="empty">クイズがありません。</p>'}</div>`;

  bindQuizButtons();
}

/* ---------------- 出題 ---------------- */

async function startQuiz(quizId, mode) {
  const found = findQuizEntry(quizId);
  if (!found) return renderHome();
  let quiz;
  try {
    quiz = await fetchJSON(`quizzes/${found.quiz.path}`);
  } catch (e) {
    app.innerHTML = `<p class="empty">クイズの読み込みに失敗しました。<br>${esc(e.message)}</p>`;
    return;
  }

  const prog = loadProgress(quizId);
  let order, pos = 0, answers = [];

  // 「続きから」は、保存済み進捗が現在のクイズと整合する場合のみ使う
  // (クイズを作り直して問題数・選択肢数が変わると古い進捗で crash しうるため)
  const ip = prog.inProgress;
  const resume = mode !== "review" && ip
    && validPerms(ip.perms, quiz.questions)
    && Number.isInteger(ip.index)
    && Array.isArray(ip.answers) && ip.answers.length === quiz.questions.length
    && ip.index >= 0 && ip.index < quiz.questions.length;

  // 選択肢の並び順(perms)。新規は毎回シャッフルし、再開時は中断したときの並びを復元する
  const perms = resume ? ip.perms : quiz.questions.map((q) => shuffledIndexes(q.choices.length));
  quiz.questions = quiz.questions.map((q, i) => {
    const perm = perms[i];
    const notes = q.rationales || [];
    return {
      ...q,
      choices: perm.map((k) => q.choices[k]),
      rationales: perm.map((k) => notes[k] || ""),
      answerIndex: perm.indexOf(q.answerIndex),
    };
  });

  if (mode === "review") {
    const wrong = new Set(prog.wrongIds || []);
    order = quiz.questions.map((q, i) => (wrong.has(q.id) ? i : -1)).filter((i) => i >= 0);
    if (!order.length) { location.hash = `#/s/${found.subject.id}/${found.section.id}`; return; }
    answers = new Array(order.length).fill(null);
  } else {
    order = quiz.questions.map((_, i) => i);
    if (resume) {
      pos = ip.index;
      answers = ip.answers.slice();
    } else {
      if (ip) { delete prog.inProgress; saveProgress(quizId, prog); } // 壊れた/古い進捗は破棄
      answers = new Array(order.length).fill(null);
    }
  }

  session = { quizId, quiz, found, mode, order, pos, answers, perms, hintShown: false };
  renderQuestion();
}

// 0..n-1 をランダムに並べた配列 (Fisher–Yates)
function shuffledIndexes(n) {
  const a = Array.from({ length: n }, (_, i) => i);
  for (let i = n - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

// 保存されていた並び順が、現在の各問題の選択肢数に合う順列かを確かめる
function validPerms(perms, questions) {
  return Array.isArray(perms) && perms.length === questions.length
    && perms.every((p, i) => Array.isArray(p) && p.length === questions[i].choices.length
      && [...p].sort((x, y) => x - y).every((v, k) => v === k));
}

function saveInProgress() {
  const s = session;
  const p = loadProgress(s.quizId);
  p.inProgress = { index: s.pos, answers: s.answers, perms: s.perms };
  saveProgress(s.quizId, p);
}

function renderQuestion() {
  const s = session;
  const qIndex = s.order[s.pos];
  const q = s.quiz.questions[qIndex];
  const answered = s.answers[s.pos] !== null && s.answers[s.pos] !== undefined;
  const pct = Math.round((s.pos / s.order.length) * 100);

  const choices = q.choices.map((c, i) => {
    let cls = "choice";
    let mark = "";
    if (answered) {
      if (i === q.answerIndex) { cls += " correct"; mark = '<span class="mark">○</span>'; }
      else if (i === s.answers[s.pos]) { cls += " wrong"; mark = '<span class="mark">×</span>'; }
    }
    return `<button class="${cls}" data-i="${i}" ${answered ? "disabled" : ""}>${esc(c)}${mark}</button>`;
  }).join("");

  // ヒントは答える前だけ。押すまでは隠しておく
  let hint = "";
  if (!answered && q.hint) {
    hint = s.hintShown
      ? `<div class="hint">💡 ${esc(q.hint)}</div>`
      : `<button class="btn ghost hintbtn" id="hint">💡 ヒントを見る</button>`;
  }

  let feedback = "";
  let actions = "";
  if (answered) {
    const your = s.answers[s.pos];
    const ok = your === q.answerIndex;
    // 間違えたときは「選んだ答えがなぜ違うか」を先に見せ、そのあと正解の解説を出す
    const why = !ok && q.rationales[your]
      ? `<div class="feedback__why"><b>「${esc(q.choices[your])}」がちがう理由</b><br>${esc(q.rationales[your])}</div>`
      : "";
    const answerLine = ok ? "" : `<b>正解は「${esc(q.choices[q.answerIndex])}」</b><br>`;
    feedback = `<div class="feedback ${ok ? "ok" : "ng"}">
      <div class="feedback__head">${ok ? "正解!" : "ざんねん…"}</div>
      ${why}
      <div class="feedback__exp">${answerLine}${esc(q.explanation || "")}</div>
    </div>`;
    const last = s.pos === s.order.length - 1;
    actions = `<div class="actions"><button class="btn full" id="next">${last ? "結果を見る" : "次へ"}</button></div>`;
  }

  const title = s.mode === "review" ? `${s.quiz.title}(復習)` : s.quiz.title;
  app.innerHTML = crumbs([
    { label: "教科", href: "#/" },
    { label: s.found.subject.name, href: `#/s/${s.found.subject.id}` },
    { label: s.found.section.name, href: `#/s/${s.found.subject.id}/${s.found.section.id}` },
    { label: title },
  ])
    + `<div class="progress">
        <span>${s.pos + 1} / ${s.order.length}</span>
        <span class="progress__bar"><span class="progress__fill" style="width:${pct}%"></span></span>
        <button class="pausebtn" id="pause">${s.mode === "review" ? "復習をやめる" : "中断する"}</button>
      </div>`
    + `<div class="qtext">${esc(q.question)}</div>`
    + `<div class="choices">${choices}</div>`
    + hint + feedback + actions;

  if (!answered) {
    app.querySelectorAll(".choice").forEach((b) => {
      b.addEventListener("click", () => onAnswer(parseInt(b.dataset.i, 10)));
    });
    const hb = document.getElementById("hint");
    if (hb) hb.addEventListener("click", () => { s.hintShown = true; renderQuestion(); });
  } else {
    document.getElementById("next").addEventListener("click", onNext);
  }
  document.getElementById("pause").addEventListener("click", onPause);
}

// 中断: ここまでの回答を保存してクイズ一覧へ戻る。一覧とホームの「続きから」で同じ問題から再開できる
// (復習モードは保存せず、やめるだけ。1問も答えていないときも保存しない)
function onPause() {
  const s = session;
  if (s.mode !== "review" && s.answers.some((a) => a !== null && a !== undefined)) saveInProgress();
  location.hash = `#/s/${s.found.subject.id}/${s.found.section.id}`;
}

function onAnswer(choiceIndex) {
  const s = session;
  s.answers[s.pos] = choiceIndex;
  // 中断しても再開できるよう、回答のたびに進捗を保存
  if (s.mode !== "review") saveInProgress();
  renderQuestion();
}

function onNext() {
  const s = session;
  if (s.pos < s.order.length - 1) {
    s.pos += 1;
    s.hintShown = false;
    if (s.mode !== "review") saveInProgress();
    renderQuestion();
  } else {
    finishQuiz();
  }
}

function finishQuiz() {
  const s = session;
  let score = 0;
  const wrongIds = [];
  s.order.forEach((qIndex, pos) => {
    const q = s.quiz.questions[qIndex];
    if (s.answers[pos] === q.answerIndex) score += 1;
    else wrongIds.push(q.id);
  });

  const p = loadProgress(s.quizId);
  p.wrongIds = wrongIds;                 // 復習モードでも「まだ間違える問題」に更新
  if (s.mode !== "review") {
    delete p.inProgress;                 // 復習を終えても、中断中の本番の記録は消さない
    p.lastAttempt = { date: new Date().toISOString().slice(0, 10), score, total: s.order.length };
  }
  saveProgress(s.quizId, p);

  renderResult(score);
}

function renderResult(score) {
  const s = session;
  const total = s.order.length;
  const wrong = [];
  s.order.forEach((qIndex, pos) => {
    const q = s.quiz.questions[qIndex];
    if (s.answers[pos] !== q.answerIndex) wrong.push({ q, your: s.answers[pos] });
  });

  const reviewList = wrong.map(({ q, your }) => `
    <div class="review-item">
      <div class="q">${esc(q.question)}</div>
      <div class="line your">あなたの解答: ${your != null ? esc(q.choices[your]) : "(無回答)"}</div>
      ${your != null && q.rationales[your] ? `<div class="exp">ちがう理由: ${esc(q.rationales[your])}</div>` : ""}
      <div class="line ans">正解: ${esc(q.choices[q.answerIndex])}</div>
      <div class="exp">${esc(q.explanation || "")}</div>
    </div>`).join("");

  const back = `#/s/${s.found.subject.id}/${s.found.section.id}`;
  const buttons = [`<button class="btn" id="again">もう一度</button>`];
  if (wrong.length) buttons.push(`<button class="btn secondary" id="review">間違いだけ復習 (${wrong.length})</button>`);
  buttons.push(`<a class="btn ghost" href="${esc(back)}">クイズ一覧へ</a>`);

  app.innerHTML = crumbs([
    { label: "教科", href: "#/" },
    { label: s.found.subject.name, href: `#/s/${s.found.subject.id}` },
    { label: s.found.section.name, href: back },
    { label: "結果" },
  ])
    + `<div class="result-score">
        <div><span class="num">${score}</span><span class="total"> / ${total} 問正解</span></div>
      </div>`
    + (wrong.length ? `<h2 class="section-head">まちがえた問題</h2>${reviewList}` : `<p class="empty">全問正解!すばらしい 🎉</p>`)
    + `<div class="actions" style="flex-wrap:wrap">${buttons.join("")}</div>`;

  const quizId = s.quizId;
  document.getElementById("again").addEventListener("click", () => {
    const p = loadProgress(quizId); delete p.inProgress; saveProgress(quizId, p);
    // ハッシュが同一なら hashchange が起きないので自分で再描画する
    // (復習モードからはハッシュが変わるので、両方やると二重に開始してしまう)
    if (location.hash === `#/play/${quizId}`) route();
    else location.hash = `#/play/${quizId}`;
  });
  const rv = document.getElementById("review");
  if (rv) rv.addEventListener("click", () => {
    if (location.hash === `#/play/${quizId}/review`) route();
    else location.hash = `#/play/${quizId}/review`;
  });
}

/* ---------------- ルーティング ---------------- */

function route() {
  const hash = location.hash || "#/";
  const parts = hash.replace(/^#\//, "").split("/").filter(Boolean);

  updateWhoButton();
  // まだ誰も登録していなければ、どの画面を開いても先に名前を聞く
  if (!profile || parts[0] === "who") return renderWho();

  if (parts.length === 0) return renderHome();
  if (parts[0] === "s" && parts.length === 2) return renderSubject(parts[1]);
  if (parts[0] === "s" && parts.length === 3) return renderSection(parts[1], parts[2]);
  if (parts[0] === "s" && parts.length === 4) return renderSection(parts[1], parts[2], parts[3]);
  if (parts[0] === "play" && parts[1]) {
    const mode = parts[2] === "review" ? "review" : "normal";
    return startQuiz(parts[1], mode);
  }
  return renderHome();
}

async function main() {
  try {
    manifest = await fetchJSON("quizzes/manifest.json");
  } catch (e) {
    app.innerHTML = `<p class="empty">クイズ一覧の読み込みに失敗しました。<br>${esc(e.message)}</p>`;
    return;
  }
  profile = loadProfiles().find((p) => p.id === localStorage.getItem("currentProfile")) || null;
  whoBtn.addEventListener("click", () => { location.hash = "#/who"; });
  window.addEventListener("hashchange", route);
  route();
}

main();
