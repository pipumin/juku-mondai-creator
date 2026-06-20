"use strict";

/* 受験クイズ アプリ本体。
   画面: ホーム(教科) → 節 → クイズ一覧 → 出題 → 結果。ハッシュルータで切替。
   進捗は localStorage に保存。MVP では profile は固定 "default"。
   将来ログインで profile を切り替え、保存先をクラウドへ差し替えられるよう
   進捗の読み書きは loadProgress/saveProgress に集約している。 */

const PROFILE = "default";
const app = document.getElementById("app");

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

/* --- 進捗 (localStorage) --- */
function progKey(quizId) { return `progress:${PROFILE}:${quizId}`; }
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
    return sep + (p.href ? `<a href="${p.href}">${esc(p.label)}</a>` : `<span>${esc(p.label)}</span>`);
  }).join(" ");
  return `<nav class="crumbs">${html}</nav>`;
}

/* ---------------- 一覧系の描画 ---------------- */

function renderHome() {
  const cards = manifest.subjects.map((s) => {
    const nQuiz = s.sections.reduce((a, sec) => a + sec.quizzes.length, 0);
    return `<a class="card" href="#/s/${s.id}">
      <div class="card__title">${esc(s.name)}</div>
      <div class="card__meta">${s.sections.length} 単元 ・ ${nQuiz} クイズ</div>
    </a>`;
  }).join("");
  app.innerHTML = `<h1 class="page-title">教科をえらぶ</h1>
    <div class="grid cols2">${cards || '<p class="empty">クイズがまだありません。</p>'}</div>`;
}

function renderSubject(subjectId) {
  const subj = findSubject(subjectId);
  if (!subj) return renderHome();
  const cards = subj.sections.map((sec) => {
    const badge = bestBadge(sec.quizzes);
    return `<a class="card" href="#/s/${subj.id}/${sec.id}">
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

function renderSection(subjectId, sectionId) {
  const subj = findSubject(subjectId);
  const sec = findSection(subj, sectionId);
  if (!sec) return renderSubject(subjectId);

  const rows = sec.quizzes.map((q) => {
    const p = loadProgress(q.id);
    const meta = `全 ${q.count} 問`
      + (p.lastAttempt ? ` ・ 前回 ${p.lastAttempt.score}/${p.lastAttempt.total}` : "");
    const buttons = [];
    if (p.inProgress) {
      buttons.push(`<button class="btn" data-act="resume" data-id="${q.id}">続きから (${p.inProgress.index + 1}問目)</button>`);
      buttons.push(`<button class="btn ghost" data-act="restart" data-id="${q.id}">最初から</button>`);
    } else {
      buttons.push(`<button class="btn" data-act="restart" data-id="${q.id}">はじめる</button>`);
    }
    if (p.wrongIds && p.wrongIds.length) {
      buttons.push(`<button class="btn secondary" data-act="review" data-id="${q.id}">間違いだけ復習 (${p.wrongIds.length})</button>`);
    }
    return `<div class="quizrow">
      <div class="quizrow__title">${esc(q.title)}</div>
      <div class="quizrow__meta">${meta}</div>
      <div class="btnrow">${buttons.join("")}</div>
    </div>`;
  }).join("");

  app.innerHTML = crumbs([
    { label: "教科", href: "#/" },
    { label: subj.name, href: `#/s/${subj.id}` },
    { label: sec.name },
  ])
    + `<h1 class="page-title">${esc(sec.name)}</h1>`
    + `<div class="grid">${rows || '<p class="empty">クイズがありません。</p>'}</div>`;

  app.querySelectorAll("button[data-act]").forEach((b) => {
    b.addEventListener("click", () => {
      const id = b.dataset.id;
      if (b.dataset.act === "restart") {
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

  if (mode === "review") {
    const wrong = new Set(prog.wrongIds || []);
    order = quiz.questions.map((q, i) => (wrong.has(q.id) ? i : -1)).filter((i) => i >= 0);
    if (!order.length) { location.hash = `#/s/${found.subject.id}/${found.section.id}`; return; }
    answers = new Array(order.length).fill(null);
  } else {
    order = quiz.questions.map((_, i) => i);
    if (prog.inProgress) { pos = prog.inProgress.index; answers = prog.inProgress.answers.slice(); }
    else { answers = new Array(order.length).fill(null); }
  }

  session = { quizId, quiz, found, mode, order, pos, answers };
  renderQuestion();
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

  let feedback = "";
  let actions = "";
  if (answered) {
    const ok = s.answers[s.pos] === q.answerIndex;
    feedback = `<div class="feedback ${ok ? "ok" : "ng"}">
      <div class="feedback__head">${ok ? "正解!" : "ざんねん…"}</div>
      <div class="feedback__exp">${esc(q.explanation || "")}</div>
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
      </div>`
    + `<div class="qtext">${esc(q.question)}</div>`
    + `<div class="choices">${choices}</div>`
    + feedback + actions;

  if (!answered) {
    app.querySelectorAll(".choice").forEach((b) => {
      b.addEventListener("click", () => onAnswer(parseInt(b.dataset.i, 10)));
    });
  } else {
    document.getElementById("next").addEventListener("click", onNext);
  }
}

function onAnswer(choiceIndex) {
  const s = session;
  s.answers[s.pos] = choiceIndex;
  if (s.mode !== "review") {
    // 中断しても再開できるよう、回答のたびに進捗を保存
    const p = loadProgress(s.quizId);
    p.inProgress = { index: s.pos, answers: s.answers };
    saveProgress(s.quizId, p);
  }
  renderQuestion();
}

function onNext() {
  const s = session;
  if (s.pos < s.order.length - 1) {
    s.pos += 1;
    if (s.mode !== "review") {
      const p = loadProgress(s.quizId);
      p.inProgress = { index: s.pos, answers: s.answers };
      saveProgress(s.quizId, p);
    }
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
  delete p.inProgress;
  if (s.mode !== "review") {
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
      <div class="line ans">正解: ${esc(q.choices[q.answerIndex])}</div>
      <div class="exp">${esc(q.explanation || "")}</div>
    </div>`).join("");

  const back = `#/s/${s.found.subject.id}/${s.found.section.id}`;
  const buttons = [`<button class="btn" id="again">もう一度</button>`];
  if (wrong.length) buttons.push(`<button class="btn secondary" id="review">間違いだけ復習 (${wrong.length})</button>`);
  buttons.push(`<a class="btn ghost" href="${back}">クイズ一覧へ</a>`);

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
    location.hash = `#/play/${quizId}`;
    route(); // ハッシュが同一でも再描画
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

  if (parts.length === 0) return renderHome();
  if (parts[0] === "s" && parts.length === 2) return renderSubject(parts[1]);
  if (parts[0] === "s" && parts.length === 3) return renderSection(parts[1], parts[2]);
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
  window.addEventListener("hashchange", route);
  route();
}

main();
