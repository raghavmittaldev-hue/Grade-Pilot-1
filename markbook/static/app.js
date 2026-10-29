// Set window.API_BASE to the API's URL if the frontend is hosted separately.
const API_BASE = window.API_BASE || "";
const $ = (id) => document.getElementById(id);
const open = new Set();   // ids of expanded students, kept across re-renders

/* ---------- API client ---------- */
async function api(method, path, body) {
  const t0 = performance.now();
  let res;
  try {
    res = await fetch(API_BASE + path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    log(method, path, "ERR", performance.now() - t0);
    throw new Error("Cannot reach the server. Is the API running?");
  }
  log(method, path, res.status, performance.now() - t0);
  const data = res.status === 204 ? null : await res.json();
  if (!res.ok) throw new Error((data && data.error) || `Request failed (${res.status})`);
  return data;
}

function log(method, path, status, ms) {
  const li = document.createElement("li");
  const ok = typeof status === "number" && status < 400;
  li.append(
    el("span", `m ${method}`, method),
    el("span", "", path),
    el("span", `st ${ok ? "ok" : "bad"}`, `${status} · ${Math.round(ms)}ms`)
  );
  $("log").prepend(li);
}

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
}
const fmt = (n) => (n === null || n === undefined ? "n/a" : Number(n).toFixed(1).replace(/\.0$/, ""));

/* ---------- stats ---------- */
function renderStats(s) {
  const has = s.students_with_marks > 0;
  $("stats").hidden = !has;
  $("stats-empty").hidden = has;
  if (!has) return;

  const cards = [
    ["Students", s.total_students, `${s.students_with_marks} with marks`],
    ["Class average", fmt(s.class_average), `median ${fmt(s.median)}`],
    ["Pass rate", `${fmt(s.pass_rate)}%`, "average of 40 or more"],
    ["Highest", fmt(s.highest.average), s.highest.name],
    ["Lowest", fmt(s.lowest.average), s.lowest.name],
    ["Std deviation", fmt(s.std_dev), "spread of averages"],
  ];
  $("cards").replaceChildren(...cards.map(([k, v, sub]) => {
    const d = el("div", "card");
    const dd = el("dd", "", String(v));
    dd.append(el("small", "", sub));
    d.append(el("dt", "", k), dd);
    return d;
  }));

  $("subject-bars").replaceChildren(...s.subjects.map((x) =>
    bar(x.subject, x.average, x.average < 40 ? "low" : "", fmt(x.average))));

  const max = Math.max(1, ...Object.values(s.grade_distribution));
  $("grade-bars").replaceChildren(...Object.entries(s.grade_distribution).map(([g, n]) =>
    bar(`Grade ${g}`, (n / max) * 100, g, String(n))));

  $("top").replaceChildren(...s.top_performers.map((p) => {
    const li = el("li", "", `${p.name} (${p.roll_no}): ${fmt(p.average)}`);
    return li;
  }));
  $("attention").replaceChildren(...(s.needs_attention.length
    ? s.needs_attention.map((p) => el("li", "", `${p.name} (${p.roll_no}): ${fmt(p.average)}`))
    : [el("li", "empty", "No students below the pass mark.")]));
}

function bar(label, pct, cls, value) {
  const row = el("div", "bar-row");
  const fill = el("div", `fill ${cls}`);
  fill.style.width = `${Math.max(0, Math.min(100, pct))}%`;
  const track = el("div", "track");
  track.append(fill);
  row.append(el("span", "label", label), track, el("span", "val", value));
  return row;
}

/* ---------- students ---------- */
function renderStudents(students) {
  $("empty").hidden = students.length > 0;
  $("list").replaceChildren(...students.map(studentNode));
}

function studentNode(s) {
  const d = el("details", "student");
  d.open = open.has(s.id);
  d.addEventListener("toggle", () => (d.open ? open.add(s.id) : open.delete(s.id)));

  const sum = el("summary");
  const who = el("div", "who");
  who.append(el("strong", "", s.name), el("span", "", s.roll_no));
  sum.append(
    el("span", "rank", s.rank ? `#${s.rank}` : ""),
    who,
    el("span", "avg", s.average === null ? "No marks" : `${fmt(s.average)}%`),
    el("span", `grade ${s.grade || ""}`, s.grade || "-")
  );
  d.append(sum);

  const body = el("div", "detail");
  for (const m of s.marks) {
    const row = el("div", "mark-row");
    const inp = el("input");
    Object.assign(inp, { type: "number", min: 0, max: 100, step: "any", value: m.score });
    inp.setAttribute("aria-label", `${m.subject} score`);
    inp.addEventListener("change", () => act(() => api("PATCH", `/api/marks/${m.id}`, { score: inp.value === "" ? null : Number(inp.value) })));
    const del = el("button", "secondary danger", "Remove");
    del.addEventListener("click", () => act(() => api("DELETE", `/api/marks/${m.id}`)));
    row.append(el("span", "", m.subject), inp, del);
    body.append(row);
  }
  if (!s.marks.length) body.append(el("p", "empty", "No marks recorded yet."));

  const add = el("form", "add-mark");
  const subj = Object.assign(el("input"), { placeholder: "Subject", required: true, maxLength: 50 });
  const score = Object.assign(el("input"), { type: "number", placeholder: "Score", min: 0, max: 100, step: "any", required: true });
  subj.setAttribute("aria-label", "Subject"); score.setAttribute("aria-label", "Score");
  add.append(subj, score, Object.assign(el("button", "primary", "Add marks"), { type: "submit" }));
  add.addEventListener("submit", (e) => {
    e.preventDefault();
    open.add(s.id);
    act(() => api("POST", `/api/students/${s.id}/marks`, { subject: subj.value, score: Number(score.value) }));
  });
  body.append(add);

  const actions = el("div", "actions");
  const rename = el("button", "secondary", "Rename");
  rename.addEventListener("click", () => {
    const name = prompt("New name", s.name);
    if (name !== null) act(() => api("PATCH", `/api/students/${s.id}`, { name }));
  });
  const remove = el("button", "secondary danger", "Delete student");
  remove.addEventListener("click", () => {
    if (confirm(`Delete ${s.name} and all their marks?`)) act(() => api("DELETE", `/api/students/${s.id}`));
  });
  actions.append(rename, remove);
  body.append(actions);

  d.append(body);
  return d;
}

/* ---------- data flow ---------- */
async function refresh() {
  const q = $("search").value.trim();
  const [students, stats] = await Promise.all([
    api("GET", `/api/students${q ? `?q=${encodeURIComponent(q)}` : ""}`),
    api("GET", "/api/stats"),
  ]);
  renderStudents(students);
  renderStats(stats);
}

async function act(fn) {
  try {
    await fn();
    showError("");
  } catch (e) {
    showError(e.message);
  }
  try { await refresh(); } catch (e) { showError(e.message); }
}

function showError(msg) {
  $("error").textContent = msg;
  $("error").hidden = !msg;
}

$("student-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  await act(() => api("POST", "/api/students", { name: $("name").value, roll_no: $("roll").value }));
  if ($("error").hidden) { e.target.reset(); $("name").focus(); }
});

let timer;
$("search").addEventListener("input", () => {
  clearTimeout(timer);
  timer = setTimeout(() => act(async () => {}), 250);
});
$("clear-log").addEventListener("click", () => $("log").replaceChildren());

act(async () => {});
