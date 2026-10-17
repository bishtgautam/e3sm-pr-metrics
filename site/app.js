"use strict";

const DAY = 86400e3;
const STAGES = [
  ["wait", "Waiting for first review", "--s1"],
  ["review", "In review → last approval", "--s2"],
  ["toNext", "Approved → merged to next (or master)", "--s3"],
  ["onNext", "On next → master", "--s4"],
];

let DATA, NOW, COMPONENTS;
const state = {
  preset: "90", from: "", to: "", basis: "merged", measure: "createdAt",
  source: "best", slow: 14, speed: "all", comps: null, issuesOnly: false,
  sort: { key: "days", dir: -1 }, pr: null,
};

// ---------- helpers ----------
const $ = (id) => document.getElementById(id);
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const t = (s) => (s ? Date.parse(s) : null);
const fmtDate = (ms) => (ms ? new Date(ms).toISOString().slice(0, 10) : "–");
const fmtDays = (d) => (d == null ? "–" : d < 10 ? d.toFixed(1) : Math.round(d).toString());

function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (v != null) e.setAttribute(k, v);
  }
  for (const k of kids.flat()) if (k != null) e.append(k.nodeType ? k : document.createTextNode(String(k)));
  return e;
}

function quantile(xs, q) {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  const i = (s.length - 1) * q, lo = Math.floor(i), hi = Math.ceil(i);
  return s[lo] + (s[hi] - s[lo]) * (i - lo);
}

const compName = (k) => (k === "unclassified" ? "Unclassified" : COMPONENTS[k] || k);
const MODEL = (c) => c !== "infrastructure" && c !== "docs";

function compsOf(p) {
  const c = state.source === "best" ? p.components : p.componentsBy[state.source];
  return c.length ? c : ["unclassified"];
}
const startOf = (p) => t(state.measure === "readyAt" ? p.readyAt : p.createdAt);
function daysToMerge(p) {
  const s = startOf(p), m = t(p.mergedAt);
  return s && m ? Math.max(0, (m - s) / DAY) : null;
}

function labelIssue(p) {
  const best = p.components.filter(MODEL), lab = p.componentsBy.labels;
  if (!best.length) return null;
  if (!lab.length) return { kind: "unlabeled", text: "no component label" };
  const missing = best.filter((c) => !lab.includes(c));
  return missing.length ? { kind: "mismatch", text: "files touch " + missing.map(compName).join(", ") } : null;
}

function stagesOf(p) {
  const created = t(p.createdAt), ready = t(p.readyAt), review = t(p.firstReviewAt);
  const appr = t(p.lastApprovalAt), merged = t(p.mergedAt);
  const next = t(p.nextAt) && !(merged && t(p.nextAt) > merged) ? t(p.nextAt) : null;
  const out = {};
  let cur = ready || created;
  if (ready && ready > created) out.draft = (ready - created) / DAY;
  if (review && review >= cur) { out.wait = (review - cur) / DAY; cur = review; }
  if (appr && appr >= cur) { out.review = (appr - cur) / DAY; cur = appr; }
  if (next && next >= cur) {
    out.toNext = (next - cur) / DAY;
    out.onNext = merged ? (merged - next) / DAY : null;
  } else if (merged) out.toNext = (merged - cur) / DAY;
  return out;
}

function currentStage(p) {
  if (p.nextAt) return "on next";
  if (p.lastApprovalAt) return "approved";
  if (p.firstReviewAt) return "in review";
  return "waiting for review";
}

function range() {
  if (state.preset === "custom") {
    return [state.from ? Date.parse(state.from) : -Infinity, state.to ? Date.parse(state.to) + DAY : Infinity];
  }
  if (state.preset === "all") return [-Infinity, Infinity];
  if (state.preset === "ytd") return [Date.UTC(new Date(NOW).getUTCFullYear(), 0, 1), Infinity];
  return [NOW - Number(state.preset) * DAY, Infinity];
}

// ---------- URL state (so a filtered view can be shared as a link) ----------
function writeHash() {
  const h = new URLSearchParams({
    p: state.preset, b: state.basis, m: state.measure, s: state.source, slow: state.slow, v: state.speed,
  });
  if (state.preset === "custom") { h.set("from", state.from); h.set("to", state.to); }
  if (state.comps.size !== Object.keys(COMPONENTS).length + 1) h.set("c", [...state.comps].join(","));
  if (state.issuesOnly) h.set("issues", "1");
  if (state.pr) h.set("pr", state.pr);
  history.replaceState(null, "", "#" + h.toString());
}
function readHash() {
  const h = new URLSearchParams(location.hash.slice(1));
  const g = (k, d) => h.get(k) ?? d;
  Object.assign(state, {
    preset: g("p", state.preset), basis: g("b", state.basis), measure: g("m", state.measure),
    source: g("s", state.source), slow: Number(g("slow", state.slow)), speed: g("v", state.speed),
    from: g("from", ""), to: g("to", ""), issuesOnly: h.get("issues") === "1",
    pr: h.get("pr") ? Number(h.get("pr")) : null,
  });
  if (h.get("c") != null) state.comps = new Set(h.get("c").split(",").filter(Boolean));
}

// ---------- plotting ----------
function baseLayout(extra = {}) {
  const ink2 = css("--ink2"), grid = css("--grid"), axis = css("--axis");
  const ax = { gridcolor: grid, linecolor: axis, zerolinecolor: axis, tickfont: { color: ink2, size: 11 }, automargin: true };
  return {
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: "system-ui, -apple-system, Segoe UI, sans-serif", color: ink2, size: 12 },
    margin: { l: 10, r: 10, t: 10, b: 10 },
    hoverlabel: { bgcolor: css("--surface"), bordercolor: css("--axis"), font: { color: css("--ink"), size: 12 } },
    legend: { orientation: "h", y: 1.08, x: 0, font: { color: ink2 } },
    ...extra,
    xaxis: { ...ax, ...(extra.xaxis || {}) },
    yaxis: { ...ax, ...(extra.yaxis || {}) },
  };
}
const CONFIG = { displaylogo: false, responsive: true, modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d"] };

function emptyPlot(id, msg) {
  Plotly.purge(id);
  $(id).replaceChildren(el("p", { class: "empty" }, msg));
  $(id).dataset.empty = "1";
}

// Remove the "no data" message before plotting. Never clear a live plot:
// Plotly.react would keep updating an SVG that is no longer in the page.
function plotReady(id) {
  if ($(id).dataset.empty) {
    $(id).replaceChildren();
    delete $(id).dataset.empty;
  }
}

function drawScatter(merged) {
  if (!merged.length) return emptyPlot("scatter", "No merged PRs match these filters.");
  plotReady("scatter");
  const pts = (fast) => {
    const xs = merged.filter((r) => (r.days > state.slow) !== fast);
    return {
      type: "scattergl", mode: "markers", name: fast ? `Fast (≤ ${state.slow} d)` : `Slow (> ${state.slow} d)`,
      x: xs.map((r) => new Date(t(r.p.mergedAt))), y: xs.map((r) => Math.max(r.days, 0.01)),
      customdata: xs.map((r) => r.p.number),
      text: xs.map((r) => `#${r.p.number} ${r.p.title.slice(0, 70)}<br>${compsOf(r.p).map(compName).join(", ")}<br><b>${fmtDays(r.days)} days</b>`),
      hovertemplate: "%{text}<extra></extra>",
      marker: { size: 8, color: css(fast ? "--s1" : "--s2"), opacity: 0.8, line: { width: 1, color: css("--surface") } },
    };
  };
  // monthly median
  const byMonth = new Map();
  for (const r of merged) {
    const k = r.p.mergedAt.slice(0, 7);
    (byMonth.get(k) || byMonth.set(k, []).get(k)).push(r.days);
  }
  const months = [...byMonth.keys()].sort();
  const med = {
    type: "scatter", mode: "lines+markers", name: "Monthly median", line: { color: css("--ink"), width: 2 },
    marker: { size: 6, color: css("--ink") },
    x: months.map((m) => m + "-15"), y: months.map((m) => Math.max(quantile(byMonth.get(m), 0.5), 0.01)),
    text: months.map((m) => `${m}: median ${fmtDays(quantile(byMonth.get(m), 0.5))} d, ${byMonth.get(m).length} PRs`),
    hovertemplate: "%{text}<extra></extra>",
  };
  const layout = baseLayout({
    yaxis: { type: "log", title: { text: "days to merge", font: { size: 12 } } },
    shapes: [{ type: "line", xref: "paper", x0: 0, x1: 1, y0: state.slow, y1: state.slow,
      line: { color: css("--muted"), width: 1 } }],
    hovermode: "closest",
  });
  Plotly.react("scatter", [pts(true), pts(false), med], layout, CONFIG);
  $("scatter").removeAllListeners?.("plotly_click");
  $("scatter").on("plotly_click", (ev) => {
    const n = ev.points[0]?.customdata;
    if (n) showPR(n, true);
  });
}

function groupByComp(rows) {
  const g = new Map();
  for (const r of rows) for (const c of compsOf(r.p)) {
    if (!state.comps.has(c)) continue;
    (g.get(c) || g.set(c, []).get(c)).push(r);
  }
  return g;
}

function drawByComp(merged) {
  const g = [...groupByComp(merged)].map(([c, rs]) => {
    const d = rs.map((r) => r.days);
    return { c, n: d.length, med: quantile(d, 0.5), p75: quantile(d, 0.75), p90: quantile(d, 0.9) };
  }).sort((a, b) => a.med - b.med);
  if (!g.length) return emptyPlot("bycomp", "No merged PRs match these filters.");
  plotReady("bycomp");
  const y = g.map((r) => `${compName(r.c)} (${r.n})`);
  const hover = g.map((r) => `${compName(r.c)} · ${r.n} PRs<br>median <b>${fmtDays(r.med)} d</b> · P75 ${fmtDays(r.p75)} d · P90 ${fmtDays(r.p90)} d`);
  Plotly.react("bycomp", [
    { type: "bar", orientation: "h", name: "Median", y, x: g.map((r) => r.med), text: hover,
      hovertemplate: "%{text}<extra></extra>", marker: { color: css("--s1") }, textposition: "none" },
    { type: "scatter", mode: "markers", name: "P90", y, x: g.map((r) => r.p90), text: hover,
      hovertemplate: "%{text}<extra></extra>",
      marker: { symbol: "line-ns-open", size: 14, line: { width: 2, color: css("--ink") }, color: css("--ink") } },
  ], baseLayout({
    height: Math.max(260, 34 * g.length + 60), bargap: 0.35,
    xaxis: { title: { text: "days", font: { size: 12 } }, rangemode: "tozero" },
  }), CONFIG);
  $("bycomp").style.height = Math.max(260, 34 * g.length + 60) + "px";
}

function drawStages(merged) {
  const g = [...groupByComp(merged)].map(([c, rs]) => {
    const st = rs.map((r) => stagesOf(r.p));
    const o = { c, n: rs.length };
    for (const [k] of STAGES) o[k] = quantile(st.map((s) => s[k]).filter((v) => v != null), 0.5) || 0;
    o.tot = STAGES.reduce((a, [k]) => a + o[k], 0);
    return o;
  }).sort((a, b) => a.tot - b.tot);
  if (!g.length) return emptyPlot("stages", "No merged PRs match these filters.");
  plotReady("stages");
  const y = g.map((r) => compName(r.c));
  const traces = STAGES.map(([k, label, color]) => ({
    type: "bar", orientation: "h", name: label, y, x: g.map((r) => r[k]),
    marker: { color: css(color), line: { width: 2, color: css("--surface") } },
    text: g.map((r) => `${compName(r.c)}<br>${label}: <b>${fmtDays(r[k])} d</b> (median)`),
    hovertemplate: "%{text}<extra></extra>", textposition: "none",
  }));
  const h = Math.max(260, 34 * g.length + 140);
  Plotly.react("stages", traces, baseLayout({
    barmode: "stack", height: h, bargap: 0.35, legend: { orientation: "h", y: 1, x: 0, yanchor: "bottom", traceorder: "normal" },
    margin: { l: 10, r: 10, t: 60, b: 10 },
    xaxis: { title: { text: "median days", font: { size: 12 } } },
  }), CONFIG);
  $("stages").style.height = h + "px";
}

// ---------- tiles & tables ----------
function tile(k, v, sub) {
  return el("div", { class: "tile" }, el("div", { class: "k" }, k), el("div", { class: "v" }, v, sub ? el("small", {}, " " + sub) : null));
}

function drawTiles(merged, open, issues) {
  const d = merged.map((r) => r.days);
  const slow = d.filter((x) => x > state.slow).length;
  const ages = open.map((r) => r.age);
  $("tiles").replaceChildren(
    tile("Merged PRs", merged.length.toLocaleString()),
    tile("Median time to merge", fmtDays(quantile(d, 0.5)), "days"),
    tile("75th percentile", fmtDays(quantile(d, 0.75)), "days"),
    tile("90th percentile", fmtDays(quantile(d, 0.9)), "days"),
    tile(`Slow (> ${state.slow} d)`, d.length ? Math.round((100 * slow) / d.length) + "%" : "–", `${slow} PRs`),
    tile("Open now", open.length.toLocaleString(), ages.length ? `median age ${fmtDays(quantile(ages, 0.5))} d` : ""),
    tile("Label issues", issues.toLocaleString(), "in table below"),
  );
}

function prLink(p) {
  return el("a", { href: p.url, target: "_blank", rel: "noopener", onclick: (e) => {
    if (!e.metaKey && !e.ctrlKey) { e.preventDefault(); showPR(p.number, true); }
  } }, "#" + p.number);
}

function table(cols, rows, sortable) {
  const head = el("tr", {}, cols.map((c) => {
    const th = el("th", { scope: "col" }, c.label);
    if (sortable && c.sort) {
      if (state.sort.key === c.key) th.setAttribute("aria-sort", state.sort.dir < 0 ? "descending" : "ascending");
      th.addEventListener("click", () => {
        state.sort = { key: c.key, dir: state.sort.key === c.key ? -state.sort.dir : -1 };
        render();
      });
      th.append(state.sort.key === c.key ? (state.sort.dir < 0 ? " ↓" : " ↑") : "");
    }
    return th;
  }));
  const body = rows.map((r) => el("tr", { class: r.cls || "" }, cols.map((c) => el("td", { class: c.cls || "" }, c.cell(r)))));
  return el("table", {}, el("thead", {}, head), el("tbody", {}, body));
}

function drawOpen(open) {
  if (!open.length) return $("open").replaceChildren(el("p", { class: "empty" }, "No open PRs in these components."));
  const rows = [...open].sort((a, b) => b.age - a.age).slice(0, 100);
  $("open").replaceChildren(table([
    { label: "PR", cell: (r) => prLink(r.p) },
    { label: "Age (d)", cls: "num days", cell: (r) => fmtDays(r.age) },
    { label: "Stage", cell: (r) => currentStage(r.p) },
    { label: "Title", cls: "title", cell: (r) => [r.p.title, el("div", { class: "who" }, r.p.author)] },
  ], rows.map((r) => ({ ...r, cls: r.age > state.slow ? "slow" : "" }))));
}

function drawTable(rows) {
  const k = state.sort.key, dir = state.sort.dir;
  const val = {
    number: (r) => r.p.number, days: (r) => r.days ?? (r.age != null ? r.age : -1),
    opened: (r) => t(r.p.createdAt), merged: (r) => t(r.p.mergedAt) || 0, author: (r) => r.p.author.toLowerCase(),
  }[k] || ((r) => r.p.number);
  const sorted = [...rows].sort((a, b) => (val(a) > val(b) ? 1 : val(a) < val(b) ? -1 : 0) * dir);
  const shown = sorted.slice(0, 500);
  const badge = (r) => {
    const i = r.issue;
    return i ? el("span", { class: "badge warn", title: i.text }, i.kind === "unlabeled" ? "unlabeled" : "label mismatch") : null;
  };
  $("table").replaceChildren(
    rows.length ? table([
      { label: "PR", key: "number", sort: 1, cell: (r) => prLink(r.p) },
      { label: "Days", key: "days", sort: 1, cls: "num days", cell: (r) => fmtDays(r.days ?? r.age) },
      { label: "Title", cls: "title", cell: (r) => [r.p.title, el("div", { class: "who" }, r.p.author)] },
      { label: "Components", cell: (r) => [compsOf(r.p).map(compName).join(", "), " ", badge(r)] },
      { label: "Opened", key: "opened", sort: 1, cls: "num", cell: (r) => fmtDate(t(r.p.createdAt)) },
      { label: "Merged", key: "merged", sort: 1, cls: "num", cell: (r) => r.p.mergedAt ? fmtDate(t(r.p.mergedAt)) : r.p.state.toLowerCase() },
      { label: "Labels", cls: "labels", cell: (r) => r.p.labels.join(", ") },
    ], shown.map((r) => ({ ...r, cls: (r.days ?? r.age) > state.slow ? "slow" : "" })), true)
      : el("p", { class: "empty" }, "No PRs match these filters."),
    rows.length > 500 ? el("p", { class: "note" }, `Showing 500 of ${rows.length}. Sort or narrow the filters to see others.`) : null,
  );
}

// ---------- single PR ----------
function showPR(n, scroll) {
  state.pr = n;
  $("prnum").value = n;
  const p = DATA.prs.find((x) => x.number === n);
  const out = $("prOut");
  writeHash();
  if (!p) {
    out.replaceChildren(el("p", { class: "empty" }, `PR #${n} is not in the data (only PRs targeting master are tracked). `,
      el("a", { href: `https://github.com/E3SM-Project/E3SM/pull/${n}`, target: "_blank", rel: "noopener" }, "Open on GitHub")));
    return;
  }
  const s = stagesOf(p);
  const created = t(p.createdAt), merged = t(p.mergedAt), end = merged || t(p.closedAt) || NOW;
  const rows = [];
  if (s.draft) rows.push(["Draft", s.draft, css("--muted")]);
  for (const [k, label, color] of STAGES) if (s[k] != null) rows.push([label, s[k], css(color)]);
  if (!merged && p.state === "OPEN") {
    const done = rows.reduce((a, r) => a + r[1], 0);
    rows.push([`Open — ${currentStage(p)} (ongoing)`, (NOW - created) / DAY - done, css("--axis")]);
  }
  const by = p.componentsBy;
  const issue = labelIssue(p);
  const milestones = [
    ["Opened", p.createdAt, p.author],
    ["Ready for review", p.readyAt !== p.createdAt ? p.readyAt : null, null],
    ["First review", p.firstReviewAt, p.firstReviewer],
    ["Last approval", p.lastApprovalAt, p.approvers.join(", ")],
    ["Merged to next", p.nextAt, p.nextSha],
    ["Merged to master", p.mergedAt, p.mergedBy],
  ].filter((m) => m[1]);
  out.replaceChildren(
    el("p", {}, el("a", { href: p.url, target: "_blank", rel: "noopener" }, `#${p.number}`), " ", el("b", {}, p.title)),
    el("div", { class: "meta" },
      "Components: ", el("b", {}, p.components.map(compName).join(", ") || "–"),
      ` (files: ${by.files.join(", ") || "–"}; labels: ${by.labels.join(", ") || "–"}; branch: ${by.branch.join(", ") || "–"})`,
      issue ? [" ", el("span", { class: "badge warn" }, issue.text)] : null,
      el("br"), `Branch ${p.branch} · ${p.changedFiles} files · +${p.additions}/−${p.deletions}`),
    el("div", { id: "prBar" }),
    el("ol", {}, rows.map(([label, d, color]) => el("li", {},
      el("span", { class: "key", style: `background:${color}` }), label, el("span", { class: "num" }, fmtDays(d) + " d")))),
    el("p", { class: "total" }, merged
      ? `Total ${fmtDays((merged - created) / DAY)} days from opened to merged in master.`
      : p.state === "OPEN" ? `Open for ${fmtDays((NOW - created) / DAY)} days so far.`
      : `Closed without merging after ${fmtDays((end - created) / DAY)} days.`),
    el("table", {}, el("tbody", {}, milestones.map(([k, v, who]) =>
      el("tr", {}, el("td", {}, k), el("td", { class: "num" }, new Date(t(v)).toISOString().slice(0, 16).replace("T", " ")),
        el("td", { class: "num" }, "+" + fmtDays((t(v) - created) / DAY) + " d"), el("td", {}, who || ""))))),
  );
  Plotly.newPlot("prBar", rows.map(([label, d, color]) => ({
    type: "bar", orientation: "h", y: [""], x: [d], name: label, marker: { color, line: { width: 2, color: css("--surface") } },
    hovertemplate: `${label}: <b>%{x:.1f} d</b><extra></extra>`,
  })), baseLayout({ barmode: "stack", showlegend: false, height: 120, xaxis: { title: { text: "days", font: { size: 12 } } },
    yaxis: { showticklabels: false } }), { ...CONFIG, displayModeBar: false });
  if (scroll) $("lookup").scrollIntoView({ behavior: "smooth", block: "start" });
}

// ---------- main render ----------
function render() {
  writeHash();
  const [lo, hi] = range();
  const inComps = (p) => compsOf(p).some((c) => state.comps.has(c));
  const inRange = (ms) => ms != null && ms >= lo && ms < hi;

  const rows = [];
  for (const p of DATA.prs) {
    if (!inComps(p)) continue;
    const when = state.basis === "merged" ? t(p.mergedAt) : t(p.createdAt);
    if (!inRange(when)) continue;
    const days = daysToMerge(p);
    const age = p.state === "OPEN" && startOf(p) ? (NOW - startOf(p)) / DAY : null;
    rows.push({ p, days, age, issue: labelIssue(p) });
  }
  const speedOk = (d) => state.speed === "all" || (state.speed === "slow" ? d > state.slow : d <= state.slow);
  const merged = rows.filter((r) => r.days != null && speedOk(r.days));
  const open = DATA.prs.filter((p) => p.state === "OPEN" && !p.draft && inComps(p) && startOf(p))
    .map((p) => ({ p, age: (NOW - startOf(p)) / DAY })).filter((r) => speedOk(r.age));
  let tableRows = rows.filter((r) => speedOk(r.days ?? r.age ?? 0));
  const issues = tableRows.filter((r) => r.issue).length;
  if (state.issuesOnly) tableRows = tableRows.filter((r) => r.issue);

  drawTiles(merged, open, issues);
  drawScatter(merged);
  drawByComp(merged);
  drawStages(merged);
  drawOpen(open);
  drawTable(tableRows);
  if (state.pr) showPR(state.pr, false);
}

// ---------- controls ----------
function syncControls() {
  for (const seg of ["preset", "speed"]) {
    for (const b of $(seg).querySelectorAll("button")) b.setAttribute("aria-pressed", String(b.dataset.v === state[seg]));
  }
  $("custom").hidden = state.preset !== "custom";
  $("from").value = state.from; $("to").value = state.to;
  for (const k of ["basis", "measure", "source"]) $(k).value = state[k];
  $("slow").value = state.slow; $("slowv").textContent = state.slow;
  $("issuesOnly").checked = state.issuesOnly;
  for (const b of $("comps").querySelectorAll("button")) b.setAttribute("aria-pressed", String(state.comps.has(b.dataset.v)));
}

function buildChips() {
  const counts = {};
  for (const p of DATA.prs) for (const c of compsOf(p)) counts[c] = (counts[c] || 0) + 1;
  const keys = [...Object.keys(COMPONENTS), "unclassified"];
  $("comps").replaceChildren(...keys.map((k) => el("button", { type: "button", class: "chip", "data-v": k,
    onclick: () => { state.comps.has(k) ? state.comps.delete(k) : state.comps.add(k); update(); } },
    compName(k), el("span", { class: "n" }, (counts[k] || 0).toLocaleString()))));
}

function update() { syncControls(); render(); }

function wire() {
  for (const seg of ["preset", "speed"]) {
    $(seg).addEventListener("click", (e) => {
      const v = e.target.closest("button")?.dataset.v;
      if (!v) return;
      state[seg] = v;
      if (v === "custom" && !state.from) {
        state.from = fmtDate(NOW - 90 * DAY); state.to = fmtDate(NOW);
      }
      update();
    });
  }
  for (const k of ["basis", "measure"]) $(k).addEventListener("change", (e) => { state[k] = e.target.value; update(); });
  $("source").addEventListener("change", (e) => { state.source = e.target.value; buildChips(); update(); });
  $("from").addEventListener("change", (e) => { state.from = e.target.value; update(); });
  $("to").addEventListener("change", (e) => { state.to = e.target.value; update(); });
  $("slow").addEventListener("input", (e) => { state.slow = Number(e.target.value); update(); });
  $("issuesOnly").addEventListener("change", (e) => { state.issuesOnly = e.target.checked; update(); });
  $("compAll").addEventListener("click", () => { state.comps = new Set([...Object.keys(COMPONENTS), "unclassified"]); update(); });
  $("compNone").addEventListener("click", () => { state.comps = new Set(); update(); });
  $("lookupForm").addEventListener("submit", (e) => { e.preventDefault(); const n = Number($("prnum").value); if (n) showPR(n, false); });
  $("theme").addEventListener("click", () => {
    const dark = matchMedia("(prefers-color-scheme: dark)").matches;
    const cur = document.documentElement.dataset.theme || (dark ? "dark" : "light");
    document.documentElement.dataset.theme = cur === "dark" ? "light" : "dark";
    try { localStorage.setItem("theme", document.documentElement.dataset.theme); } catch {}
    render();
  });
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", render);
}

async function main() {
  try { const th = localStorage.getItem("theme"); if (th) document.documentElement.dataset.theme = th; } catch {}
  try {
    const r = await fetch("data/prs.json", { cache: "no-cache" });
    if (!r.ok) throw new Error(r.status + " " + r.statusText);
    DATA = await r.json();
  } catch (err) {
    document.querySelector(".tiles").replaceChildren(el("p", { class: "empty" }, `Could not load data/prs.json (${err.message}). Run fetch.py first.`));
    return;
  }
  if (!window.Plotly) {
    for (const id of ["scatter", "bycomp", "stages"]) {
      $(id).replaceChildren(el("p", { class: "empty" }, "The charting library did not load. Reload the page."));
    }
    window.Plotly = { react() {}, purge() {}, newPlot() {} };  // keep tiles and tables working
  }
  COMPONENTS = DATA.components;
  NOW = t(DATA.fetchedAt) || Math.max(...DATA.prs.map((p) => t(p.updatedAt)));
  $("asof").textContent = `Data as of ${new Date(NOW).toISOString().slice(0, 16).replace("T", " ")} UTC · ${DATA.prs.length.toLocaleString()} PRs.`;
  state.comps = new Set([...Object.keys(COMPONENTS), "unclassified"]);
  readHash();
  buildChips();
  wire();
  update();
}

main();
