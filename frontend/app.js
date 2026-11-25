// folio. website: page navigation, running an analysis (progress, company choice, missing-services list), the agent workflow,
// the dashboard (metrics, five tabs, chart, printable report), sources and transcripts, my reports (remembered in this browser)
// and services and setup (uploads, transcription jobs, price check, service status).
// Every figure shown comes from the backend, already calculated and formatted in Python; this file does no financial arithmetic.
// The only calculations here place points on the chart drawing.
const $ = (id) => document.getElementById(id);
const S = {
  config: null, runningId: null, running: null, report: null, view: null,
  sources: [], sourceIndex: {}, figureSources: {}, transcriptIds: new Set(), filter: "all", jobs: {},
};

// ---------- small helpers ----------

function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function button(label, onClick, className = "btn btn-small") {
  const b = el("button", label, className);
  b.type = "button";
  b.addEventListener("click", onClick);
  return b;
}

function link(label, href, className) {
  const a = el("a", label, className);
  a.href = href;
  if (/^https?:\/\//.test(href)) { a.target = "_blank"; a.rel = "noopener"; }
  return a;
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(body.detail || `Request failed (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return body;
}

function remember(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* storage unavailable */ } }
function recall(key, fallback) { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch (e) { return fallback; } }

function card(title, agentClass, agentLabel) {
  const box = el("div", null, "card");
  const head = el("div", null, "card-head");
  head.appendChild(el("h2", title));
  if (agentLabel) head.appendChild(el("span", agentLabel, `pill ${agentClass}`));
  box.appendChild(head);
  return box;
}

const STATUS_CLASS = { calculated: "ok", reported_only: "ok", estimated: "warn", missing: "warn", not_meaningful: "warn", not_comparable: "warn", not_applicable: "" };
function statusPill(status) { return el("span", status.replace(/_/g, " "), `pill ${STATUS_CLASS[status] ?? ""}`); }
function agentClass(text) { return text.startsWith("Agent 1") ? "agent-1" : text.startsWith("Agent 2") ? "agent-2" : "agent-3"; }

// ---------- navigation ----------

const PAGES = { new: "New analysis", workflow: "Agent workflow", dashboard: "Analysis dashboard", sources: "Sources & transcripts",
  reports: "My reports", services: "Services & setup" };

function currentPage() {
  const name = location.hash.slice(1);
  return PAGES[name] ? name : "new";
}

function showPage() {
  const page = currentPage();
  for (const key of Object.keys(PAGES)) $(`page-${key}`).hidden = key !== page;
  document.querySelectorAll(".sidebar nav a").forEach((a) => a.classList.toggle("active", a.getAttribute("href") === `#${page}`));
  updateBreadcrumb();
  document.body.classList.remove("menu-open");
  if (page === "reports") renderMyReports();
  if (page === "services") loadServicesPage();
  window.scrollTo(0, 0);
}

function updateBreadcrumb() {
  const crumb = $("breadcrumb");
  crumb.replaceChildren(el("span", "folio / "), el("strong", PAGES[currentPage()]));
  const company = (S.report || S.running || {}).company;
  if (company && ["workflow", "dashboard", "sources"].includes(currentPage())) crumb.appendChild(el("span", ` / ${company.name} (${company.ticker})`));
}

function renderDemoBanner() {
  const banner = $("demo-banner");
  if (S.report && S.report.demo_label) banner.textContent = S.report.demo_label;
  else if (S.running && S.running.demo) banner.textContent = "Demo analysis: fictional sample data, not real";
  else { banner.hidden = true; return; }
  banner.hidden = false;
}

// ---------- configuration ----------

async function loadConfig() {
  S.config = await api("/api/config");
  const select = $("language");
  for (const [code, name] of Object.entries(S.config.supported_languages)) {
    const option = el("option", name);
    option.value = code;
    select.appendChild(option);
  }
  select.value = recall("folio.language", null) || S.config.default_output_language;
  select.addEventListener("change", () => remember("folio.language", select.value));
  $("upload-limits").textContent = `Uploads (up to ${S.config.max_upload_mb} MB per file, ${S.config.max_recording_hours} hours per recording) are kept with your files under Services & setup and labelled as uploads. They are not yet used in the analysis.`;
}

// ---------- running an analysis ----------

async function runAnalysis(event, chosenTicker) {
  if (event) event.preventDefault();
  const box = $("analysis-status");
  const company = chosenTicker || $("company").value.trim();
  if (!company) { box.replaceChildren(el("p", "Enter a company name or ticker.", "error")); return; }
  const demo = document.querySelector('input[name="mode"]:checked').value === "demo";
  const peers = $("peers").value.split(",").map((p) => p.trim()).filter(Boolean);
  box.replaceChildren(el("p", "Starting…", "hint"));
  const response = await fetch("/api/analyses", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ company, demo, peers, output_language: $("language").value }),
  });
  const body = await response.json().catch(() => ({}));
  if (response.status === 409) {  // several companies match: the user chooses
    const list = el("div", null, "choice-list");
    for (const c of body.candidates) list.appendChild(button(`${c.name} (${c.ticker})`, () => runAnalysis(null, c.ticker)));
    box.replaceChildren(el("p", body.detail), list);
    return;
  }
  if (response.status === 424) {  // a live analysis lists every service it still needs
    const list = el("ul");
    for (const item of body.needs_configuration) {
      const li = el("li");
      li.appendChild(el("strong", item.service + ": "));
      li.appendChild(document.createTextNode(item.how_to_configure));
      list.appendChild(li);
    }
    box.replaceChildren(el("p", body.detail, "warn"), list);
    return;
  }
  if (!response.ok || !body.id) {
    box.replaceChildren(el("p", body.detail || `Request failed (${response.status})`, "error"));
    return;
  }
  box.replaceChildren(el("p", "Started. Follow it under Agent workflow.", "hint"));
  rememberAnalysis(body);
  clearAnalysis();
  S.runningId = body.id;
  S.running = body;
  renderDemoBanner();
  location.hash = "#workflow";
  pollAnalysis(body.id);
}

function rememberAnalysis(state) {
  const list = recall("folio.analyses", []).filter((a) => a.id !== state.id);
  list.unshift({ id: state.id, ticker: state.company.ticker, name: state.company.name, demo: state.demo, as_of: state.as_of, created_at: state.created_at });
  remember("folio.analyses", list.slice(0, 50));
}

async function pollAnalysis(id, failures = 0) {
  let state;
  try {
    state = await api(`/api/analyses/${id}`);
  } catch (e) {  // a failed progress check is retried a few times instead of leaving the page waiting
    if (failures < 5) setTimeout(() => pollAnalysis(id, failures + 1), 1000);
    else $("workflow-banner").replaceChildren(el("p", `Could not get the progress: ${e.message}`, "error"));
    return;
  }
  if (id !== S.runningId) return;
  S.running = state;
  renderWorkflow(state);
  if (state.status === "completed") await openAnalysis(id);
  else if (state.status !== "failed") setTimeout(() => pollAnalysis(id), 700);
}

function clearAnalysis() {
  S.report = null;
  S.view = null;
  S.sources = [];
  S.sourceIndex = {};
  S.figureSources = {};
  $("dash-empty").hidden = false;
  $("dash-body").hidden = true;
  $("dash-title").textContent = "Analysis dashboard";
  $("dash-sub").textContent = "The results of the current analysis.";
  $("sources-empty").hidden = false;
  $("sources-body").hidden = true;
  $("source-summary").replaceChildren(el("p", "Appears after an analysis has run.", "empty"));
  $("transcript-view").replaceChildren();
  renderTranscriptPicker();
  renderDemoBanner();
}

async function openAnalysis(id) {
  const [report, view] = await Promise.all([api(`/api/analyses/${id}/report`), api(`/api/analyses/${id}/view`)]);
  S.report = report;
  S.view = view;
  S.runningId = id;
  remember("folio.current", id);
  buildSources(report);
  renderDemoBanner();
  renderDashboard();
  renderSources();
  renderSourceSummary();
  renderTranscriptPicker();
  updateBreadcrumb();
  try {
    S.running = await api(`/api/analyses/${id}`);
    renderWorkflow(S.running);
  } catch (e) { /* progress no longer available */ }
}

// ---------- agent workflow ----------

const STEPS = [
  { key: "sources", parts: ["identify", "peers"], no: "Step 1", title: "Source discovery", cls: "",
    text: "Finds the company, chooses three to five comparable peers and gathers the reports, the earnings call and the news." },
  { key: "agent1", parts: ["agent1"], no: "Agent 1", title: "Financial analyst", cls: "agent-1",
    text: "Reads the reports into numbered pages, checks every extracted figure against its page, calculates the indicators in Python and compares them with history and peers." },
  { key: "agent2", parts: ["agent2"], no: "Agent 2", title: "Meeting & news analyst", cls: "agent-2",
    text: "Keeps management statements, guidance and analysts' questions on the earnings call apart, and reviews relevant news since the latest results." },
  { key: "agent3", parts: ["agent3", "save"], no: "Agent 3", title: "Report combiner", cls: "agent-3",
    text: "Combines both agents into one report: overview, where the sources disagree, risks, what is missing and what could not be verified." },
];
const STEP_NAMES = { queued: "Waiting to start", identify: "Finding the company", peers: "Choosing peers", agent1: "Agent 1: reports and indicators",
  agent2: "Agent 2: earnings call and news", agent3: "Agent 3: combined report", save: "Saving the report" };

function stepState(step, state) {
  if (step.parts.every((p) => state.steps_done.includes(p))) return "done";
  const started = step.parts.some((p) => state.steps_done.includes(p) || state.current_step === p) || (step.key === "sources" && state.current_step === "queued");
  if (state.status === "failed" && started) return "failed";
  return started ? "running" : "waiting";
}

function stepDetail(key) {
  const r = S.report;
  if (!r) return "";
  const a1 = r.agent1, a2 = r.agent2, a3 = r.agent3;
  if (key === "sources") return `${r.peers.peers.length} peers chosen, ${r.peers.excluded.length} left out · ${a1.documents.length} company reports · ${a2.call.documents.length} call transcript(s) · ${a2.news.included.length} news items used`;
  if (key === "agent1") return `${a1.documents.length} reports read · ${a1.extraction_check.accepted} figures checked and used · ${a1.extraction_check.rejected.length} rejected · ${a1.summary.length} summary statements`;
  if (key === "agent2") return `${a2.call.statements.length} call statements · ${a2.news.included.length} news items used, ${a2.news.excluded.length} left out`;
  return `${a3.statement_check.checked} statements checked across the agents · ${a3.statement_check.unverified} unverified`;
}

function renderWorkflow(state) {
  const banner = $("workflow-banner");
  const info = el("div", null, "grow");
  info.appendChild(el("h2", `${state.company.name} (${state.company.ticker})`));
  const line = el("p");
  line.appendChild(el("span", state.demo ? "Demo" : "Live", `pill ${state.demo ? "demo" : "live"}`));
  line.appendChild(document.createTextNode(`  ${state.status === "completed" ? "Completed" : state.status === "failed" ? "Failed" : STEP_NAMES[state.current_step] || state.current_step}`));
  info.appendChild(line);
  const bar = el("progress");
  bar.max = 100;
  bar.value = state.progress_percent;
  const parts = [info, bar, el("strong", `${state.progress_percent}%`)];
  if (state.status === "completed") parts.push(link("Open the dashboard →", "#dashboard", "btn btn-green"));
  banner.replaceChildren(...parts);
  if (state.status === "failed") banner.appendChild(el("p", `Failed: ${state.error}`, "error"));

  const cards = STEPS.map((step) => {
    const status = stepState(step, state);
    const box = el("div", null, `card step ${step.cls}`);
    const head = el("div", null, "step-head");
    const title = el("div");
    title.appendChild(el("div", step.no, "step-no"));
    title.appendChild(el("h3", step.title));
    head.appendChild(title);
    head.appendChild(el("span", status, `pill ${status === "done" ? "ok" : status === "running" ? "live" : status === "failed" ? "bad" : ""}`));
    box.appendChild(head);
    box.appendChild(el("p", step.text));
    const progress = el("div", null, `bar ${status === "done" ? "done" : status === "running" ? "running" : ""}`);
    progress.appendChild(el("span"));
    box.appendChild(progress);
    if (status === "done") box.appendChild(el("div", stepDetail(step.key), "step-detail"));
    return box;
  });
  const pair = el("div", null, "step-pair");
  pair.append(cards[1], cards[2]);
  $("workflow-steps").replaceChildren(cards[0], pair, cards[3]);
  updateBreadcrumb();
}

// ---------- sources ----------

function sourceKey(c) {
  if (c.indicator) return `calc|${c.indicator}|${c.period}`;
  if (c.publisher && c.doc_id) return `news|${c.doc_id}`;
  if (c.doc_id) return `doc|${c.doc_id}|${c.page}`;
  if (c.publisher) return `price|${c.publisher}|${c.date}`;
  return null;
}

function addSource(c, usedFor) {
  const key = sourceKey(c);
  if (!key) return null;
  let s = S.sourceIndex[key];
  if (!s) {
    const type = key.startsWith("calc") ? "calculated" : key.startsWith("news") ? "news" : key.startsWith("price") ? "price"
      : S.transcriptIds.has(c.doc_id) ? "call" : "report";
    s = { n: S.sources.length + 1, key, type, citation: c, lines: [], usedFor: [] };
    S.sources.push(s);
    S.sourceIndex[key] = s;
  }
  if (c.line && !s.lines.includes(c.line)) s.lines.push(c.line);
  if (usedFor && !s.usedFor.includes(usedFor)) s.usedFor.push(usedFor);
  return s;
}

function buildSources(r) {
  S.sources = [];
  S.sourceIndex = {};
  S.figureSources = {};
  S.transcriptIds = new Set(r.agent2.call.documents.map((d) => d.doc_id));
  const statements = [...r.agent3.overview, ...r.agent3.disagreements.flatMap((d) => d.positions), ...r.agent3.risks,
    ...r.agent1.summary, ...r.agent2.call.statements, ...r.agent2.news.included.map((i) => ({ text: i.channel, citations: i.citations }))];
  for (const s of statements) for (const c of s.citations || []) addSource(c, s.text);
  for (const result of r.agent1.indicators.current) {
    const list = [];
    for (const input of result.inputs || []) {
      for (const c of input.sources || []) {
        const s = addSource(c, `Key figure: ${result.name} (${input.name})`);
        if (s && !list.includes(s)) list.push(s);
      }
    }
    S.figureSources[result.indicator] = list;
  }
}

const SOURCE_TYPES = { report: "Company report", call: "Earnings call", news: "News", calculated: "Calculated", price: "Price" };

function sourceTitle(s) {
  const c = s.citation;
  if (s.type === "calculated") return `Calculated: ${c.name || c.indicator}`;
  if (s.type === "price") return `${c.publisher}: closing price`;
  return c.title || c.doc_id;
}

function sourceWhere(s) {
  const c = s.citation;
  if (s.type === "calculated") return c.period;
  if (s.type === "news") return `${c.publisher} · ${c.published}`;
  if (s.type === "price") return `${c.exchange ? c.exchange + " · " : ""}close ${c.date}`;
  return `p. ${c.page}`;
}

function citeButtons(citations) {
  return (citations || []).map((c) => S.sourceIndex[sourceKey(c)]).filter(Boolean)
    .map((s) => button(`[S${s.n}]`, () => openSource(s), "cite"));
}

function openSource(s) {
  $("modal-title").textContent = `[S${s.n}] ${sourceTitle(s)}`;
  const body = $("modal-body");
  const facts = el("dl");
  const add = (term, value) => { facts.appendChild(el("dt", term)); const dd = el("dd"); dd.append(value); facts.appendChild(dd); };
  add("Type", SOURCE_TYPES[s.type]);
  add("Where", sourceWhere(s));
  const url = s.citation.url;
  if (url && /^https?:\/\//.test(url)) add("Link", link(url, url));
  if (s.citation.demo) add("Note", "Fictional demo source");
  body.replaceChildren(facts);
  if (s.lines.length) {
    body.appendChild(el("h3", "Cited text"));
    for (const line of s.lines) body.appendChild(el("div", line, "evidence"));
  }
  body.appendChild(el("h3", `Used for (${s.usedFor.length})`));
  const list = el("ul", null, "plain-list");
  for (const use of s.usedFor) list.appendChild(el("li", use));
  body.appendChild(list);
  $("modal").hidden = false;
}

function openFigureSources(result) {
  $("modal-title").textContent = `Sources of ${result.name}`;
  const body = $("modal-body");
  body.replaceChildren(el("p", `Formula: ${result.formula}. Period: ${result.period}.`, "hint"));
  const list = el("ul", null, "plain-list");
  for (const s of S.figureSources[result.indicator] || []) {
    const li = el("li");
    li.appendChild(button(`[S${s.n}]`, () => openSource(s), "cite"));
    li.appendChild(document.createTextNode(` ${sourceTitle(s)}, ${sourceWhere(s)}`));
    list.appendChild(li);
  }
  if (!list.children.length) list.appendChild(el("li", "No sources: this figure was not calculated."));
  body.appendChild(list);
  $("modal").hidden = false;
}

function renderSources() {
  if (!S.report) return;
  $("sources-empty").hidden = true;
  $("sources-body").hidden = false;
  const chips = $("source-chips");
  chips.replaceChildren();
  for (const [key, label] of [["all", "All"], ["report", "Company reports"], ["call", "Earnings call"], ["news", "News"], ["calculated", "Calculated"], ["price", "Prices"]]) {
    const count = key === "all" ? S.sources.length : S.sources.filter((s) => s.type === key).length;
    const chip = button(`${label} (${count})`, () => { S.filter = key; renderSources(); }, `chip ${S.filter === key ? "active" : ""}`);
    chips.appendChild(chip);
  }
  const query = $("source-search").value.trim().toLowerCase();
  const grid = $("source-grid");
  grid.replaceChildren();
  const shown = S.sources.filter((s) => (S.filter === "all" || s.type === S.filter)
    && (!query || [sourceTitle(s), sourceWhere(s), ...s.lines, ...s.usedFor].join(" ").toLowerCase().includes(query)));
  if (!shown.length) grid.appendChild(el("p", "No sources match.", "empty"));
  for (const s of shown) {
    const item = el("button", null, "card source-card");
    item.type = "button";
    const top = el("div");
    top.appendChild(el("span", `[S${s.n}]`, "cite"));
    top.appendChild(el("span", ` ${SOURCE_TYPES[s.type]}`, "source-meta"));
    item.appendChild(top);
    item.appendChild(el("h3", sourceTitle(s)));
    item.appendChild(el("div", `${sourceWhere(s)} · used ${s.usedFor.length} time${s.usedFor.length === 1 ? "" : "s"}`, "source-meta"));
    item.addEventListener("click", () => openSource(s));
    grid.appendChild(item);
  }
}

function renderSourceSummary() {
  const r = S.report;
  const list = el("ul", null, "summary-list");
  const row = (label, value) => { const li = el("li"); li.append(el("span", label), el("strong", String(value))); list.appendChild(li); };
  row("Company reports read", r.agent1.documents.length);
  row("Earnings-call transcripts", r.agent2.call.documents.length);
  row("News items used", r.agent2.news.included.length);
  row("News items left out", r.agent2.news.excluded.length);
  row("Statements checked", r.agent3.statement_check.checked);
  row("Unverified statements", r.agent3.statement_check.unverified);
  const box = $("source-summary");
  box.replaceChildren(el("p", `${r.company.name} (${r.company.ticker}) · analysis date ${r.analysis_date}`, "hint"), list);
  box.appendChild(link("See every source →", "#sources"));
}

// ---------- transcripts ----------

function renderTranscriptPicker() {
  const picker = $("transcript-picker");
  picker.replaceChildren();
  if (S.report && S.report.agent2.call.statements.length) {
    picker.appendChild(button(`Earnings call: ${S.report.agent2.call.documents[0].title}`, showAnalysisCall, "chip"));
  }
  for (const job of Object.values(S.jobs).filter((j) => j.status === "completed")) {
    picker.appendChild(button(`Recording: ${job.filename}`, () => showJobTranscript(job.id), "chip"));
  }
  if (!picker.children.length) picker.appendChild(el("p", "No transcript yet. Run an analysis, or transcribe an uploaded recording under Services & setup.", "empty"));
}

function transcriptGrid(leftHead, rightHead, rows) {
  const grid = el("div", null, "transcript-cols");
  grid.append(el("div", leftHead, "col-head"), el("div", rightHead, "col-head"));
  for (const [left, right, unclear] of rows) {
    const a = el("div", null, unclear ? "unclear" : "");
    a.append(...left);
    const b = el("div", right, unclear ? "unclear" : "");
    grid.append(a, b);
  }
  return grid;
}

function showAnalysisCall() {
  const r = S.report;
  const translated = r.output_language !== "en";
  const note = translated ? "Translation needs the live text model (API stage)." : "No translation needed: the call is in the report's language.";
  const rows = r.agent2.call.statements.map((s) => [[el("div", `${KIND[s.kind] || s.kind} · ${s.speaker}`, "quote-who"), el("p", s.text), ...citeButtons(s.citations)], note]);
  $("transcript-view").replaceChildren(transcriptGrid("Original", "Translation", rows));
}

async function showJobTranscript(jobId) {
  const r = await api(`/api/jobs/${jobId}/result`);
  const rows = r.segments.map((s) => [[el("div", `${s.timestamp || "—"} · ${s.speaker || "speaker not identified"}`, "quote-who"),
    el("p", (s.unclear ? "[unclear] " : "") + s.original)], s.translation || "(same language)", s.unclear]);
  const view = $("transcript-view");
  view.replaceChildren(el("p", `${r.source.filename}: ${r.transcript_type}${r.translation_type ? ", " + r.translation_type : ""}`, "hint"));
  for (const flag of r.flags) view.appendChild(el("p", flag, "warn"));
  view.appendChild(transcriptGrid(`Original (${r.source_language})`, `Translation (${r.output_language})`, rows));
}

// ---------- dashboard ----------

const KIND = { management: "Management", guidance: "Guidance", analyst: "Analyst question or assumption" };
const METRICS = ["P/E", "Common ROE", "Net debt/EBITDA", "Revenue growth"];

function viewTable(test) { return S.view.blocks.find((b) => b.type === "table" && test(b)); }
function keyFigureRows() {
  const table = viewTable((b) => b.columns.includes("Peer median"));
  return { table, rows: Object.fromEntries((table ? table.rows : []).map((row) => [row[0], row])) };
}
function historyTable() { return viewTable((b) => b.columns[0] === "Indicator" && /^FY/.test(b.columns[1] || "")); }

function statementList(statements, tagFor) {
  const list = el("ul", null, "statements");
  if (!statements.length) list.appendChild(el("li", "Nothing to show.", "empty"));
  for (const s of statements) {
    const li = el("li", null, s.label === "unverified" ? "unverified" : "");
    const tag = tagFor ? tagFor(s) : null;
    if (tag) li.appendChild(tag);
    const text = el("div");
    if (s.label === "unverified") text.appendChild(el("span", "Unverified", "badge-unverified"));
    text.appendChild(document.createTextNode(s.text));
    text.append(...citeButtons(s.citations));
    li.appendChild(text);
    for (const issue of s.issues || []) li.appendChild(el("div", issue, "issue"));
    list.appendChild(li);
  }
  return list;
}

function basedOnTag(s) {
  const tag = el("div", null, "statement-tag");
  for (const origin of s.based_on || []) {
    tag.appendChild(el("span", origin, `pill ${agentClass(origin)}`));
    tag.appendChild(document.createTextNode(" "));
  }
  return tag;
}

function renderDashboard() {
  const r = S.report;
  $("dash-empty").hidden = true;
  $("dash-body").hidden = false;
  $("dash-title").textContent = `${r.company.name} (${r.company.ticker})`;
  $("dash-sub").textContent = `Analysis date ${r.analysis_date} · ${r.mode} mode · current period ${r.agent1.indicators.current_period} · indicator definitions ${r.agent1.indicators.definition_version}`;
  renderMetrics();
  renderOverviewTab();
  renderFinancialsTab();
  renderMeetingsTab();
  renderAssessmentTab();
  renderReportTab();
}

function renderMetrics() {
  const { rows } = keyFigureRows();
  const results = Object.fromEntries(S.report.agent1.indicators.current.map((x) => [x.name, x]));
  $("metrics").replaceChildren(...METRICS.map((name) => {
    const row = rows[name];
    const result = results[name];
    const box = el("div", null, "card metric");
    box.appendChild(el("div", name, "metric-name"));
    box.appendChild(el("div", row ? row[1] : "—", "metric-value"));
    const sub = el("div", null, "metric-sub");
    if (row && row[2] !== "—") sub.appendChild(document.createTextNode(`Peer median ${row[2]} · `));
    if (result) sub.appendChild(statusPill(result.status));
    box.appendChild(sub);
    return box;
  }));
}

function renderOverviewTab() {
  const a3 = S.report.agent3;
  const overview = card("Overview", "agent-3", "Agent 3");
  overview.appendChild(statementList(a3.overview, basedOnTag));
  const risks = card("Risks", "agent-3", "Agent 3");
  risks.appendChild(statementList(a3.risks, basedOnTag));
  $("tab-overview").replaceChildren(overview, risks);
}

function renderFinancialsTab() {
  const r = S.report;
  const panel = $("tab-financials");
  const summary = card("What the reports say", "agent-1", "Agent 1");
  summary.appendChild(statementList(r.agent1.summary));

  const figures = card("Key figures", "agent-1", "Agent 1 · calculated in Python");
  const { table, rows } = keyFigureRows();
  const wrap = el("div", null, "table-wrap");
  const t = el("table");
  const head = el("tr");
  for (const h of ["Indicator", "Value", "Peer median", "Compared with peers", "Status", "Notes", "Sources"]) head.appendChild(el("th", h));
  t.appendChild(head);
  for (const result of r.agent1.indicators.current) {
    const row = rows[result.name] || [result.name, "—", "—", "—", ""];
    const tr = el("tr");
    tr.appendChild(el("td", result.name));
    tr.appendChild(el("td", row[1], "num"));
    tr.appendChild(el("td", row[2], "num"));
    tr.appendChild(el("td", row[3], "num"));
    const status = el("td");
    status.appendChild(statusPill(result.status));
    tr.appendChild(status);
    tr.appendChild(el("td", row[4].replace(/^[a-z ]+\.\s*/, ""), "note"));
    const sources = el("td");
    sources.appendChild(button("Sources", () => openFigureSources(result), "cite"));
    tr.appendChild(sources);
    t.appendChild(tr);
  }
  wrap.appendChild(t);
  figures.appendChild(wrap);
  for (const note of (table && table.notes) || []) figures.appendChild(el("p", note, "hint"));

  const peers = card("Peers", "agent-1", "Agent 1");
  const peerList = el("ul", null, "plain-list");
  for (const p of r.peers.peers) {
    const li = el("li");
    li.appendChild(el("strong", `${p.name} (${p.ticker}) `));
    li.appendChild(el("span", p.label, "pill"));
    li.appendChild(el("div", p.explanation, "hint"));
    peerList.appendChild(li);
  }
  if (!r.peers.peers.length) peerList.appendChild(el("li", "No suitable peers: the company is compared with its own history only."));
  peers.appendChild(peerList);
  for (const e of r.peers.excluded) peers.appendChild(el("p", `Not used as a peer: ${e.ticker}. ${e.reason}`, "hint"));

  const history = card("Key figures by fiscal year", "agent-1", "Agent 1");
  history.appendChild(chart());
  const hist = historyTable();
  if (hist) history.appendChild(simpleTable(hist));

  panel.replaceChildren(summary, figures, peers, history);
}

function simpleTable(block) {
  const wrap = el("div", null, "table-wrap");
  const t = el("table");
  const head = el("tr");
  for (const c of block.columns) head.appendChild(el("th", c));
  t.appendChild(head);
  for (const row of block.rows) {
    const tr = el("tr");
    row.forEach((cell, i) => tr.appendChild(el("td", cell, i ? "num" : "")));
    t.appendChild(tr);
  }
  wrap.appendChild(t);
  for (const note of block.notes || []) wrap.appendChild(el("p", note, "hint"));
  return wrap;
}

function chart() {
  // Plots values Python calculated; the labels are Python's own formatted values. Only the drawing positions are worked out here.
  const SERIES = [["net_margin", "Net profit margin", "#159579"], ["roe_common", "Common ROE", "#2f6fd6"], ["ebitda_margin", "EBITDA margin", "#7a4fd0"]];
  const history = S.report.agent1.indicators.history;
  const years = Object.keys(history);
  const hist = historyTable();
  const labels = hist ? Object.fromEntries(hist.rows.map((row) => [row[0], row])) : {};
  const series = SERIES.map(([id, name, color]) => ({
    name, color,
    points: years.map((fy, i) => {
      const result = (history[fy] || []).find((x) => x.indicator === id);
      const label = labels[name] ? labels[name][i + 1] : "";
      return result && result.status === "calculated" ? { value: result.value, label } : null;
    }),
  }));
  const values = series.flatMap((s) => s.points.filter(Boolean).map((p) => p.value));
  const box = el("div");
  if (!values.length || years.length < 2) { box.appendChild(el("p", "Not enough fiscal-year values to chart.", "empty")); return box; }
  const W = 640, H = 230, left = 16, right = 16, top = 22, bottom = 30;
  const low = Math.min(...values), high = Math.max(...values), span = high - low || 1;
  const x = (i) => left + (i * (W - left - right)) / (years.length - 1);
  const y = (v) => top + ((high - v) * (H - top - bottom)) / span;
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("class", "chart");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "Net profit margin, common ROE and EBITDA margin by fiscal year");
  const node = (tag, attrs, text) => {
    const n = document.createElementNS(ns, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    if (text) n.textContent = text;
    svg.appendChild(n);
    return n;
  };
  node("line", { x1: left, x2: W - right, y1: H - bottom + 6, y2: H - bottom + 6, class: "axis" });
  years.forEach((fy, i) => node("text", { x: x(i), y: H - 8, "text-anchor": "middle", class: "grid-label" }, fy));
  for (const s of series) {
    let path = "";
    s.points.forEach((p, i) => { if (p) path += `${path && s.points[i - 1] ? "L" : "M"}${x(i)},${y(p.value)} `; });
    if (path) node("path", { d: path, fill: "none", stroke: s.color, "stroke-width": 2.2 });
    s.points.forEach((p, i) => {
      if (!p) return;
      node("circle", { cx: x(i), cy: y(p.value), r: 3.5, fill: s.color });
      node("text", { x: x(i), y: y(p.value) - 7, "text-anchor": "middle", class: "point-label", fill: s.color }, p.label);
    });
  }
  box.appendChild(svg);
  const legend = el("div", null, "legend");
  for (const s of series) {
    const item = el("span");
    const swatch = el("i");
    swatch.style.background = s.color;
    item.append(swatch, s.name);
    legend.appendChild(item);
  }
  box.appendChild(legend);
  box.appendChild(el("p", "Missing years are left as gaps, never filled. Values and labels come from the Python calculations.", "hint"));
  return box;
}

function renderMeetingsTab() {
  const a2 = S.report.agent2;
  const call = card("Earnings call", "agent-2", "Agent 2");
  if (a2.call.documents.length) call.appendChild(el("p", `${a2.call.documents[0].title}. Management statements, guidance and analysts' questions are kept apart; an analyst's assumption is not a fact.`, "hint"));
  for (const s of a2.call.statements) {
    const quote = el("blockquote", null, `quote ${s.kind} ${s.label === "unverified" ? "unverified" : ""}`);
    quote.appendChild(el("div", `${KIND[s.kind] || s.kind} · ${s.speaker}`, "quote-who"));
    const p = el("p", s.text);
    p.append(...citeButtons(s.citations));
    quote.appendChild(p);
    for (const issue of s.issues) quote.appendChild(el("div", issue, "issue"));
    call.appendChild(quote);
  }
  if (!a2.call.statements.length) call.appendChild(el("p", "No earnings-call material was available.", "empty"));

  const news = card("News", "agent-2", "Agent 2");
  news.appendChild(el("p", `Since the latest results announcement (${a2.news.since}), plus older items that are still material. Timing alone does not show that news moved the share price.`, "hint"));
  for (const item of a2.news.included) {
    const box = el("div", null, `news-item ${item.verified ? "" : "unverified"}`);
    const meta = el("div", `${item.published} · ${item.publisher} `, "news-meta");
    if (!item.recent) meta.appendChild(el("span", "older item, still material", "pill"));
    box.appendChild(meta);
    const title = el("strong");
    title.appendChild(/^https?:\/\//.test(item.url) ? link(item.title, item.url) : document.createTextNode(item.title));
    box.appendChild(title);
    const p = el("p");
    if (!item.verified) p.appendChild(el("span", "Unverified", "badge-unverified"));
    p.appendChild(document.createTextNode(item.channel));
    p.append(...citeButtons(item.citations));
    box.appendChild(p);
    for (const issue of item.issues) box.appendChild(el("div", issue, "issue"));
    news.appendChild(box);
  }
  if (a2.news.excluded.length) {
    news.appendChild(el("h3", "Left out"));
    const list = el("ul", null, "plain-list");
    for (const e of a2.news.excluded) list.appendChild(el("li", `${e.published} · ${e.title}: ${e.reason}`));
    news.appendChild(list);
  }
  $("tab-meetings").replaceChildren(call, news);
}

function renderAssessmentTab() {
  const r = S.report, a3 = r.agent3;
  const disagreements = card("Where the sources disagree", "agent-3", "Agent 3");
  if (!a3.disagreements.length) disagreements.appendChild(el("p", "No disagreements were identified.", "empty"));
  for (const d of a3.disagreements) {
    disagreements.appendChild(el("h3", d.topic));
    for (const p of d.positions) {
      const box = el("div", null, `position ${p.verified ? "" : "unverified"}`);
      const who = el("div", null, "statement-tag");
      who.appendChild(el("strong", `${p.who} `));
      for (const origin of p.based_on || []) who.appendChild(el("span", origin, `pill ${agentClass(origin)}`));
      box.appendChild(who);
      const text = el("div", p.text);
      text.append(...citeButtons(p.citations));
      box.appendChild(text);
      for (const issue of p.issues) box.appendChild(el("div", issue, "issue"));
      disagreements.appendChild(box);
    }
    if (d.note) disagreements.appendChild(el("p", d.note, "hint"));
  }
  const unverified = card("Not verified", "agent-3", "All agents");
  const list = el("ul", null, "plain-list warn-list");
  for (const u of a3.unverified_statements) list.appendChild(el("li", `${u.agent}: “${u.text}” — ${u.issues.join(" ")}`));
  if (!a3.unverified_statements.length) list.appendChild(el("li", "Every statement was verified."));
  unverified.appendChild(list);
  const missing = card("Missing information");
  const missingList = el("ul", null, "plain-list");
  for (const m of a3.missing_information) missingList.appendChild(el("li", m));
  if (!a3.missing_information.length) missingList.appendChild(el("li", "Nothing missing was recorded."));
  missing.appendChild(missingList);
  const limits = card("Limitations");
  const limitList = el("ul", null, "plain-list");
  for (const l of [...a3.limitations, ...(r.notes || [])]) limitList.appendChild(el("li", l));
  limits.appendChild(limitList);
  $("tab-assessment").replaceChildren(disagreements, unverified, missing, limits);
}

// ---------- final report (same blocks as the PDF and Word files) ----------

function renderBlock(block) {
  switch (block.type) {
    case "banner": return el("div", block.text, "banner");
    case "heading": return el(`h${Math.min(block.level + 1, 4)}`, block.text);
    case "paragraph": return el("p", block.text);
    case "statements": {
      const list = el("ul", null, "statements");
      if (!block.items.length) list.appendChild(el("li", "Nothing to show.", "empty"));
      for (const item of block.items) {
        const li = el("li", null, item.label === "unverified" ? "unverified" : "");
        if (item.tag) li.appendChild(el("div", item.tag, "statement-tag"));
        const text = el("div");
        if (item.label === "unverified") text.appendChild(el("span", "Unverified", "badge-unverified"));
        text.appendChild(document.createTextNode(item.text));
        li.appendChild(text);
        if (item.sources.length) {
          const line = el("div", "Source: ", "sources");
          item.sources.forEach((s, i) => {
            if (i) line.appendChild(document.createTextNode("; "));
            line.appendChild(s.url ? link(s.text, s.url) : document.createTextNode(s.text));
          });
          li.appendChild(line);
        }
        for (const issue of item.issues) li.appendChild(el("div", issue, "issue"));
        list.appendChild(li);
      }
      return list;
    }
    case "table": return simpleTable(block);
    case "list": {
      const wrap = el("div");
      if (block.title) wrap.appendChild(el("h4", block.title));
      const list = el("ul", null, `plain-list ${block.style === "warn" ? "warn-list" : ""}`);
      for (const item of block.items) list.appendChild(el("li", item));
      wrap.appendChild(list);
      return wrap;
    }
    default: return el("p", block.text || "");
  }
}

function renderReportTab() {
  const r = S.report, id = S.runningId;
  const toolbar = el("div", null, "report-toolbar");
  toolbar.appendChild(el("span", "The same report as the PDF and Word files.", "grow"));
  toolbar.appendChild(button("Print", printReport, "btn"));
  toolbar.appendChild(link("Download PDF", `/api/analyses/${id}/download/pdf`, "btn btn-green"));
  toolbar.appendChild(link("Download Word", `/api/analyses/${id}/download/docx`, "btn"));

  const pages = el("div", null, "report-pages");
  if (r.demo_label) pages.appendChild(el("div", r.demo_label, "print-label"));
  const cover = el("div", null, "report-page report-cover");
  const top = el("div");
  const logo = el("span", "folio", "logo");
  logo.appendChild(el("span", "."));
  top.appendChild(logo);
  top.appendChild(el("h1", `Financial analysis: ${r.company.name}`));
  top.appendChild(el("p", `${r.company.ticker} · analysis date ${r.analysis_date} · ${r.mode} mode`));
  if (r.demo_label) top.appendChild(el("p", r.demo_label, "cover-demo"));
  cover.appendChild(top);
  cover.appendChild(el("p", `Prepared by three agents: reports and indicators, earnings call and news, combined report · indicator definitions ${r.agent1.indicators.definition_version}`));
  pages.appendChild(cover);

  const body = el("div", null, "report-page report-body");
  for (const block of S.view.blocks) {
    if (block.type === "heading" && block.level === 1) continue;  // shown on the cover
    body.appendChild(renderBlock(block));
  }
  if (r.demo_label) body.appendChild(el("div", r.demo_label, "banner"));
  pages.appendChild(body);
  $("tab-report").replaceChildren(toolbar, pages);
}

function activateTab(name) {
  document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".tab-panel").forEach((p) => { p.hidden = p.id !== `tab-${name}`; });
}

function printReport() {
  activateTab("report");
  window.print();
}

// ---------- my reports ----------

async function renderMyReports() {
  const list = $("my-analyses");
  list.replaceChildren();
  const analyses = recall("folio.analyses", []);
  if (!analyses.length) list.appendChild(el("li", "No analyses yet. Analyses you run are remembered by this browser only.", "empty"));
  for (const a of analyses) {
    const li = el("li");
    const info = el("div", null, "grow");
    info.appendChild(el("strong", `${a.name} (${a.ticker})`));
    info.appendChild(el("div", `Analysis date ${a.as_of} · started ${String(a.created_at || "").slice(0, 16).replace("T", " ")}`, "hint"));
    li.appendChild(info);
    li.appendChild(el("span", a.demo ? "Demo" : "Live", `pill ${a.demo ? "demo" : "live"}`));
    li.appendChild(button("Open", async () => {
      try {
        await openAnalysis(a.id);
        location.hash = "#dashboard";
      } catch (e) {
        info.appendChild(el("div", e.status === 404 ? "This analysis is no longer stored on the server." : e.message, "error"));
      }
    }, "btn btn-small btn-navy"));
    li.appendChild(link("PDF", `/api/analyses/${a.id}/download/pdf`, "btn btn-small"));
    li.appendChild(link("Word", `/api/analyses/${a.id}/download/docx`, "btn btn-small"));
    li.appendChild(button("Forget", () => {
      remember("folio.analyses", recall("folio.analyses", []).filter((x) => x.id !== a.id));
      renderMyReports();
    }));
    list.appendChild(li);
  }
  const saved = await api("/api/reports").catch(() => []);
  const reports = $("reports");
  reports.replaceChildren();
  if (!saved.length) reports.appendChild(el("li", "No saved reports yet. Saved reports are kept until you delete them.", "empty"));
  for (const r of saved) {
    const li = el("li", null);
    li.appendChild(el("span", `${r.title} · ${r.created_at.slice(0, 10)} · ${r.citations} cited sources`, "grow"));
    li.appendChild(button("Delete", async () => {
      if (!confirm(`Delete the report "${r.title}" and its saved sources?`)) return;
      await api(`/api/reports/${r.id}`, { method: "DELETE" });
      renderMyReports();
    }));
    reports.appendChild(li);
  }
}

// ---------- services and setup ----------

const SERVICE_STATUS = { configured: "Configured (not yet checked live)", awaiting_configuration: "Awaiting configuration", no_adapter_yet: "No adapter yet" };

function serviceAdvice(s) {
  if (s.key === "ffmpeg") return "Only needed to transcribe uploaded recordings. Install it with brew install ffmpeg (Mac) or winget install ffmpeg (Windows).";
  return (s.missing.length ? `Add ${s.missing.join(", ")} to .env. ` : "") + s.how_to_configure;
}

async function loadServicesPage() {
  if (!S.config) return;
  const grid = $("services");
  grid.replaceChildren();
  for (const s of S.config.services) {
    const box = el("div", null, "service");
    box.appendChild(el("strong", s.label));
    box.appendChild(el("span", SERVICE_STATUS[s.status], `pill ${s.status === "configured" ? "ok" : "warn"}`));
    if (s.status !== "configured") box.appendChild(el("p", serviceAdvice(s)));
    grid.appendChild(box);
  }
  const byKey = Object.fromEntries(S.config.services.map((s) => [s.key, s]));
  const problems = ["transcription", "ffmpeg"].filter((k) => byKey[k] && byKey[k].status !== "configured")
    .map((k) => `${byKey[k].label}: ${SERVICE_STATUS[byKey[k].status]}. ${serviceAdvice(byKey[k])}`);
  $("model-status").textContent = problems.length ? "Transcription cannot run yet. " + problems.join(" ") : "Transcription is configured.";
  $("working").replaceChildren(...S.config.features.working.map((f) => el("li", f)));
  $("awaiting").replaceChildren(...S.config.features.awaiting_implementation.map((f) => el("li", f)));
  renderJobs();
  await loadFiles();
}

function formatBytes(n) {
  return n > 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1e3))} KB`;
}

async function loadFiles() {
  const files = await api("/api/uploads").catch(() => []);
  const list = $("files");
  list.replaceChildren();
  if (!files.length) list.appendChild(el("li", "No files yet. Drop one on the New analysis page.", "empty"));
  for (const f of files) {
    const latest = f.versions[f.versions.length - 1];
    const li = el("li");
    li.appendChild(el("span", f.origin === "user_upload" ? "Uploaded by you" : "Official source", `pill ${f.origin === "user_upload" ? "live" : "ok"}`));
    li.appendChild(el("span", `${f.filename} · ${f.kind} · ${formatBytes(latest.size_bytes)}${f.reporting_period ? " · " + f.reporting_period : ""}`, "grow"));
    if (f.kind === "recording") li.appendChild(button("Transcribe", () => startJob(f.id)));
    li.appendChild(button("Delete", async () => {
      if (!confirm(`Delete ${f.filename}? This cannot be undone.`)) return;
      await api(`/api/uploads/${f.id}`, { method: "DELETE" });
      loadFiles();
    }));
    list.appendChild(li);
  }
}

function uploadFile(file) {
  if (!file) return;
  const form = new FormData();
  form.append("file", file);
  const xhr = new XMLHttpRequest();
  const bar = $("upload-progress");
  bar.hidden = false;
  bar.value = 0;
  $("upload-message").textContent = `Uploading ${file.name}…`;
  xhr.upload.addEventListener("progress", (e) => { if (e.lengthComputable) bar.value = (100 * e.loaded) / e.total; });
  xhr.addEventListener("load", () => {
    bar.hidden = true;
    const body = JSON.parse(xhr.responseText || "{}");
    $("upload-message").textContent = xhr.status >= 400 ? body.detail || "Upload failed." : ["Uploaded " + body.filename + ".", ...(body.warnings || [])].join(" ");
    $("upload-message").className = `message ${xhr.status >= 400 ? "error" : ""}`;
  });
  xhr.addEventListener("error", () => { bar.hidden = true; $("upload-message").textContent = "Upload failed."; });
  xhr.open("POST", "/api/uploads");
  xhr.send(form);
}

async function startJob(uploadId) {
  try {
    const state = await api("/api/transcriptions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ upload_id: uploadId, output_language: $("language").value }),
    });
    S.jobs[state.id] = state;
    renderJobs();
    pollJob(state.id);
  } catch (e) {
    alert(e.message);
  }
}

async function pollJob(jobId) {
  const state = await api(`/api/jobs/${jobId}`);
  S.jobs[jobId] = state;
  renderJobs();
  renderTranscriptPicker();
  if (state.status === "running" || state.status === "queued") setTimeout(() => pollJob(jobId), 2000);
}

function renderJobs() {
  const list = $("jobs");
  list.replaceChildren();
  const jobs = Object.values(S.jobs);
  if (!jobs.length) list.appendChild(el("li", "No transcription jobs in this session.", "empty"));
  for (const job of jobs) {
    const li = el("li");
    li.appendChild(el("span", `${job.filename} → ${job.output_language}: ${job.current_step}`, "grow"));
    const bar = el("progress");
    bar.max = 100;
    bar.value = job.progress_percent;
    li.appendChild(bar);
    if (job.status === "failed") {
      li.appendChild(el("span", `Failed: ${job.error}`, "error"));
      li.appendChild(button("Resume", async () => { await api(`/api/jobs/${job.id}/resume`, { method: "POST" }); pollJob(job.id); }));
    }
    if (job.status === "completed") li.appendChild(button("View transcript", () => { location.hash = "#sources"; showJobTranscript(job.id); }));
    list.appendChild(li);
  }
}

async function checkPrice(event) {
  event.preventDefault();
  const ticker = $("ticker").value.trim();
  const date = $("price-date").value;
  $("price-result").textContent = "Checking…";
  try {
    const q = await api(`/api/prices/${encodeURIComponent(ticker)}${date ? "?on=" + date : ""}`);
    $("price-result").textContent = `${q.ticker} (${q.exchange}): ${q.close} ${q.currency} at the close on ${q.price_date}${q.stale ? " — STALE" : ""}. Source: ${q.source}. ${q.note}`;
  } catch (e) {
    $("price-result").textContent = e.message;
  }
}

// ---------- start-up ----------

function wireUp() {
  window.addEventListener("hashchange", showPage);
  $("menu-button").addEventListener("click", () => document.body.classList.toggle("menu-open"));
  $("scrim").addEventListener("click", () => document.body.classList.remove("menu-open"));
  $("analysis-form").addEventListener("submit", runAnalysis);
  $("price-form").addEventListener("submit", checkPrice);
  $("source-search").addEventListener("input", renderSources);
  document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => activateTab(b.dataset.tab)));
  $("modal-close").addEventListener("click", () => { $("modal").hidden = true; });
  $("modal").addEventListener("click", (e) => { if (e.target === $("modal")) $("modal").hidden = true; });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") $("modal").hidden = true; });

  const zone = $("drop-zone"), input = $("file-input");
  zone.addEventListener("click", () => input.click());
  zone.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } });
  input.addEventListener("change", () => { uploadFile(input.files[0]); input.value = ""; });
  zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("over"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("over"));
  zone.addEventListener("drop", (e) => { e.preventDefault(); zone.classList.remove("over"); uploadFile(e.dataTransfer.files[0]); });
}

async function start() {
  wireUp();
  showPage();
  renderTranscriptPicker();
  try {
    await loadConfig();
  } catch (e) {
    $("analysis-status").replaceChildren(el("p", e.message, "error"));
    return;
  }
  if (currentPage() === "services") loadServicesPage();
  const last = recall("folio.current", null);  // reopen the last analysis after a reload, if the server still has it
  if (last) openAnalysis(last).catch(() => remember("folio.current", null));
}

start();
