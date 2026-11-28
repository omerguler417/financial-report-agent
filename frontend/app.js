// The website: page navigation, running an analysis (progress, company choice, missing-services list), the agent workflow,
// the dashboard (metrics, four tabs, chart, printable report), sources and transcripts, my reports (remembered in this browser)
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

function card(title) {
  const box = el("div", null, "card");
  const head = el("div", null, "card-head");
  head.appendChild(el("h2", title));
  box.appendChild(head);
  return box;
}

const STATUS_CLASS = { calculated: "ok", reported_only: "ok", estimated: "warn", missing: "warn", not_meaningful: "warn", not_comparable: "warn", not_applicable: "" };
function statusPill(status) { return el("span", status.replace(/_/g, " "), `pill ${STATUS_CLASS[status] ?? ""}`); }

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
  document.body.classList.remove("menu-open");
  if (page === "reports") renderMyReports();
  if (page === "services") loadServicesPage();
  window.scrollTo(0, 0);
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
  select.value = recall("fra.language", null) || S.config.default_output_language;
  select.addEventListener("change", () => remember("fra.language", select.value));
  renderIndicatorPicker(S.config.indicators || []);
  loadTranscriptChoices();
  $("upload-limits").textContent = `Up to ${S.config.max_upload_mb} MB per file, ${S.config.max_recording_hours} hours per recording.`;
}

// ---------- choosing indicators ----------

function renderIndicatorPicker(catalogue) {
  const picker = $("indicator-picker");
  picker.replaceChildren();
  const groups = {};
  for (const item of catalogue) (groups[item.group] = groups[item.group] || []).push(item);
  for (const [group, items] of Object.entries(groups)) {
    const box = el("details", null, "indicator-group");
    const summary = el("summary");
    const groupCheck = el("input");
    groupCheck.type = "checkbox";
    groupCheck.checked = true;
    groupCheck.setAttribute("aria-label", `All ${group} indicators`);
    const count = el("span", "", "group-count");
    summary.append(groupCheck, el("span", group), count);
    box.appendChild(summary);
    const list = el("div", null, "checks");
    const boxes = items.map((item) => {
      const label = el("label", null, "check");
      const input = el("input");
      input.type = "checkbox";
      input.checked = true;
      input.name = "indicator";
      input.value = item.id;
      label.append(input, item.name);
      list.appendChild(label);
      return input;
    });
    const refresh = () => {
      const ticked = boxes.filter((b) => b.checked).length;
      groupCheck.checked = ticked === boxes.length;
      groupCheck.indeterminate = ticked > 0 && ticked < boxes.length;
      count.textContent = `${ticked} of ${boxes.length}`;
      updateIndicatorCount();
    };
    groupCheck.addEventListener("click", (e) => e.stopPropagation());  // ticking the group does not open or close it
    groupCheck.addEventListener("change", () => { boxes.forEach((b) => { b.checked = groupCheck.checked; }); refresh(); });
    boxes.forEach((b) => b.addEventListener("change", refresh));
    box.appendChild(list);
    picker.appendChild(box);
    refresh();
  }
}

function chosenIndicators() {
  const all = [...document.querySelectorAll('input[name="indicator"]')];
  const ticked = all.filter((b) => b.checked).map((b) => b.value);
  return { all: all.length, ticked };
}

function updateIndicatorCount() {
  const { all, ticked } = chosenIndicators();
  $("indicator-count").textContent = all ? `${ticked.length} of ${all} chosen` : "";
}

// ---------- running an analysis ----------

function resetForm() {  // "New analysis": an empty form; an analysis that is running carries on under Agent workflow
  $("company").value = "";
  $("peers").value = "";
  $("extra-questions").value = "";
  $("horizon").value = "5";
  $("transcript-upload").value = "";
  $("analysis-status").replaceChildren();
  if (S.config) renderIndicatorPicker(S.config.indicators || []);
  if (currentPage() === "new") showPage();
  setTimeout(() => $("company").focus(), 50);  // after the page has switched
}

async function runAnalysis(event, chosenTicker) {
  if (event) event.preventDefault();
  const box = $("analysis-status");
  const company = chosenTicker || $("company").value.trim();
  if (!company) { box.replaceChildren(el("p", "Enter a company name or ticker.", "error")); return; }
  const peers = $("peers").value.split(",").map((p) => p.trim()).filter(Boolean);
  const choice = chosenIndicators();
  if (choice.all && !choice.ticked.length) { box.replaceChildren(el("p", "Choose at least one indicator.", "error")); return; }
  const indicators = choice.ticked.length === choice.all ? null : choice.ticked;  // null: all of them
  box.replaceChildren(el("p", "Starting…", "hint"));
  const response = await fetch("/api/analyses", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ company, peers, indicators: indicators, output_language: $("language").value,
      transcript_upload: $("transcript-upload").value || null, horizon_years: Number($("horizon").value),
      questions: $("extra-questions").value.split("\n").map((q) => q.trim()).filter(Boolean) }),
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
  clearAnalysis();
  S.runningId = body.id;
  S.running = body;
  location.hash = "#workflow";
  pollAnalysis(body.id);
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
  $("dash-head").classList.remove("masthead");
  $("dash-eyebrow").textContent = "03 / Dashboard";
  $("dash-title").textContent = "Analysis dashboard";
  $("dash-sub").textContent = "The results of the current analysis.";
  $("sources-empty").hidden = false;
  $("sources-body").hidden = true;
  $("source-summary").replaceChildren(el("p", "Appears after an analysis has run.", "empty"));
  $("transcript-view").replaceChildren();
  renderTranscriptPicker();
}

async function openAnalysis(id) {
  const [report, view] = await Promise.all([api(`/api/analyses/${id}/report`), api(`/api/analyses/${id}/view`)]);
  S.report = report;
  S.view = view;
  S.runningId = id;
  remember("fra.current", id);
  buildSources(report);
  renderDashboard();
  renderSources();
  renderSourceSummary();
  renderTranscriptPicker();
  try {
    S.running = await api(`/api/analyses/${id}`);
    renderWorkflow(S.running);
  } catch (e) { /* progress no longer available */ }
}

// ---------- agent workflow ----------

const STEPS = [
  { key: "sources", parts: ["identify", "peers"], no: "Step 1", title: "Source discovery", cls: "",
    text: "Finds the company, its peers, reports and earnings call." },
  { key: "agent1", parts: ["agent1"], no: "Agent 1", title: "Financial analyst", cls: "agent-1",
    text: "Reads the reports and calculates the indicators." },
  { key: "agent2", parts: ["agent2"], no: "Agent 2", title: "Earnings-call analyst", cls: "agent-2",
    text: "Analyses the earnings call." },
  { key: "agent3", parts: ["agent3", "save"], no: "Agent 3", title: "Report combiner", cls: "agent-3",
    text: "Writes the combined report." },
];
const STEP_NAMES = { queued: "Waiting to start", identify: "Finding the company", peers: "Choosing peers", agent1: "Agent 1: reports and indicators",
  agent2: "Agent 2: earnings call", agent3: "Agent 3: combined report", save: "Saving the report" };

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
  if (key === "sources") return `${r.peers.peers.length} peers chosen, ${r.peers.excluded.length} left out · ${a1.documents.length} company reports · ${a2.call.documents.length} call transcript(s)`;
  if (key === "agent1") return `${a1.documents.length} reports read · ${a1.extraction_check.accepted} figures checked and used · ${a1.extraction_check.rejected.length} rejected · ${a1.summary.length} summary statements`;
  if (key === "agent2") return `${a2.call.statements.length} call statements`;
  return `${a3.statement_check.checked} statements checked across the agents · ${a3.statement_check.unverified} unverified`;
}

function renderWorkflow(state) {
  const banner = $("workflow-banner");
  const info = el("div", null, "grow");
  info.appendChild(el("h2", `${state.company.name} (${state.company.ticker})`));
  const line = el("p");
  line.appendChild(document.createTextNode(`${state.status === "completed" ? "Completed" : state.status === "failed" ? "Failed" : STEP_NAMES[state.current_step] || state.current_step}`));
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
}

// ---------- sources ----------

function sourceKey(c) {
  if (c.indicator) return `calc|${c.indicator}|${c.period}`;
  if (c.doc_id && c.page == null && c.tag) return `xbrl|${c.doc_id}|${c.tag}`;
  if (c.doc_id) return `doc|${c.doc_id}|${c.page}`;
  if (c.publisher) return `price|${c.publisher}|${c.date}`;
  return null;
}

function addSource(c, usedFor) {
  const key = sourceKey(c);
  if (!key) return null;
  let s = S.sourceIndex[key];
  if (!s) {
    const type = key.startsWith("calc") ? "calculated" : key.startsWith("price") ? "price"
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
    ...r.agent1.summary, ...r.agent2.call.statements, ...(r.agent2.call.questions || []).flatMap((q) => [q.question, q.answer]),
    ...Object.values((r.agent3.commentary || {}).sections || {}).flatMap((c) => [c.headline, ...c.paragraph].filter(Boolean)),
    ...((r.agent3.commentary || {}).valuation || [])];
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

const SOURCE_TYPES = { report: "Company report", call: "Earnings call", calculated: "Calculated", price: "Price" };

function sourceTitle(s) {
  const c = s.citation;
  if (s.type === "calculated") return `Calculated: ${c.name || c.indicator}`;
  if (s.type === "price") return `${c.publisher}: closing price`;
  return c.title || c.doc_id;
}

function sourceWhere(s) {
  const c = s.citation;
  if (s.type === "calculated") return c.period;
  if (s.type === "price") return `${c.exchange ? c.exchange + " · " : ""}close ${c.date}`;
  if (c.page == null && c.section) return `${c.section} · ${c.tag || ""}`;
  return c.page_unit === "turn" ? `turn ${c.page}` : `p. ${c.page}`;  // a call transcript is cited by speaker turn
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
  for (const [key, label] of [["all", "All"], ["report", "Company reports"], ["call", "Earnings call"], ["calculated", "Calculated"], ["price", "Prices"]]) {
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

function statementSources(st) { return (st.citations || []).map((c) => S.sourceIndex[sourceKey(c)]).filter(Boolean); }

function proseItem(st, notes, tag) {  // one statement as plain reading text; "Unverified" stays visible, its reason opens on request
  const item = el("div", null, `prose-item${st.label === "unverified" ? " unverified" : ""}`);
  if (tag) item.appendChild(el("div", tag, "prose-tag"));
  const p = el("p");
  if (st.label === "unverified") p.appendChild(el("span", "Unverified", "badge-unverified"));
  p.appendChild(document.createTextNode(st.text));
  p.appendChild(notes.mark(statementSources(st)));
  item.appendChild(p);
  if (st.label === "unverified" && (st.issues || []).length) {
    const why = el("details", null, "why");
    why.appendChild(el("summary", "Why unverified?"));
    for (const issue of st.issues) why.appendChild(el("div", issue, "issue"));
    item.appendChild(why);
  }
  return item;
}

function peersChosenCard(r) {
  const box = card("Peers chosen");
  if (!r.peers.peers.length) {
    box.appendChild(el("p", "No suitable peers were found.", "empty"));
    return box;
  }
  const list = el("dl", null, "key-data peers-list");
  for (const p of r.peers.peers) {
    list.appendChild(el("dt", p.ticker));
    list.appendChild(el("dd", p.name));
  }
  box.appendChild(list);
  return box;
}

function verifiedFirst(statements) {  // unverified statements stay visible and labelled, after the verified ones
  return [...statements].sort((a, b) => (a.label === "unverified") - (b.label === "unverified"));
}

function statementList(statements, notes, tagFor) {
  const list = el("div", null, "prose");
  if (!statements.length) list.appendChild(el("p", "Nothing to show.", "empty"));
  for (const st of statements) list.appendChild(proseItem(st, notes, tagFor ? tagFor(st) : null));
  return list;
}

const TOPICS = [["business", "What the company does"], ["results", "Results"], ["outlook", "Outlook"], ["risks", "Risks"]];

function splitPeriod(st) {  // "For fiscal year 2026, Microsoft Cloud revenue…" -> the period as a sub-heading and the rest as the point
  const m = (st.text || "").match(/^For (?:the )?([^,]{4,60}),\s+(\S)/);
  if (!m || !/\b(19|20)\d{2}\b/.test(m[1])) return { period: null, st };
  const rest = st.text.slice(m[0].length - 1);
  return { period: m[1][0].toUpperCase() + m[1].slice(1), st: { ...st, text: rest[0].toUpperCase() + rest.slice(1) } };
}

function notePanel(title, statements, notes) {  // a short topic as one flowing paragraph; unverified points stay labelled below it
  const panel = el("div", null, "note-panel");
  panel.appendChild(el("h3", title, "note-heading"));
  const verified = statements.filter((st) => st.label !== "unverified");
  if (verified.length) {
    const p = el("p");
    for (const st of verified) {
      p.appendChild(document.createTextNode(st.text));
      p.appendChild(notes.mark(statementSources(st)));
      p.appendChild(document.createTextNode(" "));
    }
    panel.appendChild(p);
  }
  for (const st of statements.filter((x) => x.label === "unverified")) panel.appendChild(proseItem(st, notes));
  return panel;
}

function periodPanel(period, statements, notes) {  // a period's results as one paragraph of explanation
  const panel = el("div", null, "period-panel");
  if (period) panel.appendChild(el("div", period, "note-period"));
  const verified = statements.filter((st) => st.label !== "unverified");
  if (verified.length) {
    const p = el("p");
    for (const st of verified) {
      p.appendChild(document.createTextNode(st.text));
      p.appendChild(notes.mark(statementSources(st)));
      p.appendChild(document.createTextNode(" "));
    }
    panel.appendChild(p);
  }
  for (const st of statements.filter((x) => x.label === "unverified")) panel.appendChild(proseItem(st, notes));
  return panel;
}

function riskCards(statements, notes) {  // numbered cards, each with its short title when the model gave one
  const grid = el("div", null, "risk-grid");
  if (!statements.length) grid.appendChild(el("p", "Nothing to show.", "empty"));
  statements.forEach((st, i) => {
    const cardEl = el("div", null, "risk-card");
    const head = el("div", null, "risk-head");
    head.appendChild(el("span", String(i + 1), "risk-number"));
    if (st.title) head.appendChild(el("span", st.title, "risk-title"));
    cardEl.appendChild(head);
    cardEl.appendChild(proseItem(st, notes));
    grid.appendChild(cardEl);
  });
  return grid;
}

function noteList(statements, notes) {
  const list = el("ul", null, "note-list");
  for (const st of statements) {
    const li = el("li");
    li.appendChild(proseItem(st, notes));
    list.appendChild(li);
  }
  return list;
}

function byTopic(statements, notes) {  // the reports' statements laid out like a research note, when the model gave each a topic
  if (!statements.some((st) => st.topic)) return statementList(statements, notes);
  const known = TOPICS.map(([key]) => key);
  const of = (key) => verifiedFirst(statements.filter((st) => (key === "other" ? !known.includes(st.topic) : st.topic === key)));
  const title = Object.fromEntries(TOPICS);
  const box = el("div", null, "note-layout");
  const pair = el("div", null, "note-pair");
  for (const key of ["business", "outlook"]) if (of(key).length) pair.appendChild(notePanel(title[key], of(key), notes));
  if (pair.children.length) box.appendChild(pair);
  const results = of("results");
  if (results.length) {  // one explained paragraph per period, the periods one under the other
    const section = el("div", null, "note-section");
    section.appendChild(el("h3", title.results, "note-heading"));
    const groups = new Map();
    for (const st of results) {
      const split = st.period ? { period: st.period, st } : splitPeriod(st);  // older reports: the period is in the sentence
      if (!groups.has(split.period)) groups.set(split.period, []);
      groups.get(split.period).push(split.st);
    }
    for (const [period, points] of groups) section.appendChild(periodPanel(period, points, notes));
    box.appendChild(section);
  }
  const risks = of("risks");
  if (risks.length) {
    const section = el("div", null, "note-section");
    section.appendChild(el("h3", title.risks, "note-heading"));
    section.appendChild(riskCards(risks, notes));
    box.appendChild(section);
  }
  const other = of("other");
  if (other.length) {
    const section = el("div", null, "note-section");
    section.appendChild(el("h3", "Other", "note-heading"));
    section.appendChild(noteList(other, notes));
    box.appendChild(section);
  }
  return box;
}


function renderDashboard() {
  const r = S.report;
  $("dash-empty").hidden = true;
  $("dash-body").hidden = false;
  const ind = r.agent1.indicators;  // the masthead of a research note
  $("dash-head").classList.add("masthead");
  $("dash-eyebrow").textContent = `Company analysis · ${r.analysis_date}`;
  $("dash-title").textContent = r.company.name;
  $("dash-sub").textContent = [r.company.ticker, ind.current_period.replace("TTM to ", "LTM "), `${ind.horizon_years || 5}-year horizon`,
    r.peers.peers.length ? `Peers: ${r.peers.peers.map((p) => p.ticker).join(", ")}` : "No peers"].join(" · ");
  renderMetrics();
  renderOverviewTab();
  renderFinancialsTab();
  renderCallTab();
  renderReportTab();
}

function renderMetrics() {
  const cmp = comparisonsView();
  const results = Object.fromEntries(S.report.agent1.indicators.current.map((x) => [x.name, x]));
  $("metrics").replaceChildren(...METRICS.map((name) => {
    const result = results[name];
    const cells = (result && cmp.cells[result.indicator]) || {};
    const box = el("div", null, "card metric");
    box.appendChild(el("div", name, "metric-name"));
    box.appendChild(el("div", cells.value || (result ? "—" : "—"), "metric-value"));
    const sub = el("div", null, "metric-sub");
    if (!result) sub.appendChild(document.createTextNode("Not chosen for this analysis"));
    else {
      if (cells.peer_median && cells.peer_median !== "—") {
        sub.appendChild(el("span", `Peer median ${cells.peer_median}`, "nowrap"));
        sub.appendChild(document.createTextNode(" · "));
        sub.appendChild(el("span", cells.difference, "nowrap"));
      }
      else sub.appendChild(document.createTextNode("No peer median"));
      if (result.status !== "calculated") sub.appendChild(statusPill(result.status));
    }
    box.appendChild(sub);
    return box;
  }));
}

function renderOverviewTab() {
  const r = S.report, a3 = r.agent3, cmp = comparisonsView();
  const overview = card("Summary");
  const notes = footnotes();
  overview.appendChild(statementList(verifiedFirst(a3.overview), notes));
  overview.appendChild(notes.box());

  const numbers = card("Key comparisons");
  const numberNotes = footnotes();
  const list = el("dl", null, "numbers-summary");
  for (const g of cmp.groups) {
    const first = g.lines.find((l) => l.kind !== "summary" && l.kind !== "trend");
    const chosen = first ? [first] : [];
    if (!chosen.length) continue;
    list.appendChild(el("dt", g.group));
    const dd = el("dd");
    dd.appendChild(sentences(chosen, numberNotes));
    list.appendChild(dd);
  }
  if (list.children.length) {
    numbers.appendChild(list);
    const more = button("All comparisons →", () => activateTab("financials"), "link-button");
    numbers.appendChild(more);
    numbers.appendChild(numberNotes.box());
  } else numbers.appendChild(el("p", "No comparisons are available for this analysis.", "empty"));

  const risks = card("Risks");
  const riskNotes = footnotes();
  risks.appendChild(statementList(verifiedFirst(a3.risks), riskNotes));  // the plain list: the user preferred it (28 November 2026)
  risks.appendChild(riskNotes.box());
  const ex = exhibitsView();
  const keyData = ex ? card("Key data") : null;
  if (keyData) keyData.appendChild(keyDataBox(ex.key_data.map((row) => [row.label, row.value])));
  const side = el("div", null, "overview-side");  // key data and the peers, beside the key comparisons
  side.append(...[keyData, peersChosenCard(r)].filter(Boolean));
  const top = el("div", null, "overview-top");  // as on a research note's first page
  top.append(numbers, side);
  $("tab-overview").replaceChildren(...[top, overview, questionsCard(), disagreementsCard(), risks].filter(Boolean));
}

// ---------- footnotes: small numbers by the data, one expandable "Sources" box per card ----------

function docKey(s) {  // sources from the same document share one footnote number
  const c = s.citation;
  if (s.type === "price") return `price|${c.publisher}`;
  if (s.type === "calculated") return s.key;
  return `doc|${c.doc_id}`;
}

function shortWhere(s) {
  const c = s.citation;
  if (s.type === "price") return `close ${c.date}`;
  if (c.page == null && c.section) return c.section;
  return sourceWhere(s);
}

function footnotes() {
  const entries = [];
  const index = {};
  const add = (s) => {
    const key = docKey(s);
    if (!index[key]) {
      index[key] = { n: entries.length + 1, title: s.type === "price" ? `${s.citation.publisher}: closing prices` : sourceTitle(s),
        url: s.citation.url, sources: [] };
      entries.push(index[key]);
    }
    if (!index[key].sources.includes(s)) index[key].sources.push(s);
    return index[key];
  };
  return {
    mark(sources) {
      const found = [...new Set((sources || []).filter(Boolean).map(add))].sort((a, b) => a.n - b.n);
      const runs = [];  // consecutive numbers are shown as one range, "1–4", to keep the tables quiet
      for (const e of found) {
        const last = runs[runs.length - 1];
        if (last && last[last.length - 1].n === e.n - 1) last.push(e); else runs.push([e]);
      }
      const sup = el("sup", null, "fn");
      for (const run of runs) {
        const b = el("button", run.length > 2 ? `${run[0].n}–${run[run.length - 1].n}` : run.map((e) => e.n).join(" "), "fn-link");
        b.type = "button";
        b.title = run.map((e) => e.title).join("; ");
        b.addEventListener("click", (event) => { event.stopPropagation(); if (run.length === 1) openFootnote(run[0]); else openFootnotes(run); });
        sup.appendChild(b);
      }
      return sup;
    },
    box() {
      if (!entries.length) return el("span");
      const details = el("details", null, "sources-box");
      details.appendChild(el("summary", `Sources (${entries.length})`));
      const list = el("ol");
      for (const e of entries) {
        const li = el("li");
        li.appendChild(e.url && /^https?:\/\//.test(e.url) ? link(e.title, e.url) : document.createTextNode(e.title));
        li.appendChild(el("span", ` · ${[...new Set(e.sources.map(shortWhere))].join(", ")}`, "hint"));
        list.appendChild(li);
      }
      details.appendChild(list);
      return details;
    },
  };
}

function openFootnotes(run) {
  $("modal-title").textContent = `Sources ${run[0].n}–${run[run.length - 1].n}`;
  const list = el("ol", null, "plain-list");
  list.start = run[0].n;
  for (const e of run) {
    const li = el("li");
    li.appendChild(button(e.title, () => openFootnote(e), "cite"));
    li.appendChild(el("span", ` · ${[...new Set(e.sources.map(shortWhere))].join(", ")}`, "hint"));
    list.appendChild(li);
  }
  $("modal-body").replaceChildren(list);
  $("modal").hidden = false;
}

function openFootnote(e) {
  if (e.sources.length === 1) { openSource(e.sources[0]); return; }
  $("modal-title").textContent = e.title;
  const body = $("modal-body");
  body.replaceChildren();
  if (e.url && /^https?:\/\//.test(e.url)) body.appendChild(el("p")).appendChild(link(e.url, e.url));
  const list = el("ul", null, "plain-list");
  for (const s of e.sources) {
    const li = el("li");
    li.appendChild(button(sourceWhere(s), () => openSource(s), "cite"));
    list.appendChild(li);
  }
  body.appendChild(list);
  $("modal").hidden = false;
}

function resultSources(indicator, period) {  // the sources of the figures a calculated result was built from
  const ind = S.report.agent1.indicators;
  const r = [...ind.current, ...Object.values(ind.history).flat()].find((x) => x.indicator === indicator && (!period || x.period === period));
  const out = [];
  for (const input of (r && r.inputs) || []) {
    for (const c of input.sources || []) {
      const s = addSource(c, `Key figure: ${r.name} (${input.name})`);
      if (s && !out.includes(s)) out.push(s);
    }
  }
  return out;
}

// ---------- financials: one card per topic, comparison lines first, compact table, details on click ----------

const NO_DATA = ["missing", "not_applicable"];  // shown in the report's appendices, not on the dashboard
const FIN_GROUPS = ["Valuation", "Profitability", "Debt and liquidity", "Cash flow and dividends", "Growth", "Per share and market"];
const KEY_HISTORY = ["Revenue growth", "Net profit margin", "Common ROE", "EBITDA margin", "FCF margin", "Net debt/EBITDA", "Current ratio"];

function comparisonsView() { return (S.view && S.view.comparisons) || { groups: [], by_indicator: {}, cells: {}, peers: [] }; }

function lineSources(line) {
  return line.cites.filter((c) => c.period !== "peer median").flatMap((c) => resultSources(c.indicator, c.period));
}

function sentences(lines, notes, className) {  // comparison lines as one flowing paragraph, each sentence with its footnotes
  const p = el("p", null, className);
  for (const line of lines) {
    p.appendChild(document.createTextNode(line.text));
    p.appendChild(notes.mark(lineSources(line)));
    p.appendChild(document.createTextNode(" "));
  }
  return p;
}

const FINDING_SECTIONS = [["Against the peers", ["peers"]], ["Against its own history", ["history", "peer history"]], ["Over time", ["trend"]]];

function commentaryFor(group) {  // the section's verified headline and paragraph, if the report writer gave one
  const c = (((S.report.agent3 || {}).commentary || {}).sections || {})[group];
  const paragraph = ((c && c.paragraph) || []).filter((st) => st.label === "verified");
  if (!paragraph.length) return null;
  return { headline: c.headline && c.headline.label === "verified" ? c.headline.text : null, paragraph };
}

function commentarySources(st) {  // a calculated result cites the figures it was built from
  return (st.citations || []).flatMap((c) => (c.indicator ? (c.period === "peer median" ? [] : resultSources(c.indicator, c.period))
    : statementSources({ citations: [c] })));
}

function findingsPanel(lines, notes, group) {  // shown after its table: what the numbers mean, then the comparisons behind it
  const panel = el("div", null, "findings-panel");
  const written = commentaryFor(group);
  let body = panel;
  if (written) {
    if (written.headline) panel.appendChild(el("div", written.headline, "findings-headline"));
    const p = el("p", null, "findings-text");
    for (const st of written.paragraph) {
      p.appendChild(document.createTextNode(st.text));
      p.appendChild(notes.mark(commentarySources(st)));
      p.appendChild(document.createTextNode(" "));
    }
    panel.appendChild(p);
    body = el("details", null, "findings-detail");
    body.appendChild(el("summary", "The comparisons in detail"));
    panel.appendChild(body);
  } else panel.appendChild(el("div", "Comparisons", "findings-head"));
  const lead = lines.filter((l) => l.kind === "summary");
  if (lead.length) body.appendChild(sentences(lead, notes, "findings-lead"));
  for (const [label, kinds] of FINDING_SECTIONS) {
    const chosen = lines.filter((l) => kinds.includes(l.kind));
    if (!chosen.length) continue;
    const section = el("div", null, "findings-section");
    section.appendChild(el("div", label, "findings-label"));
    section.appendChild(sentences(chosen, notes));
    body.appendChild(section);
  }
  return panel;
}

function renderFinancialsTab() {
  const r = S.report, cmp = comparisonsView();
  const groupOf = Object.fromEntries(((S.config && S.config.indicators) || []).map((x) => [x.id, x.group]));
  const parts = [peersCard(r), ...exhibitCards()];
  for (const group of FIN_GROUPS) {
    const results = r.agent1.indicators.current.filter((x) => groupOf[x.indicator] === group && !NO_DATA.includes(x.status));
    if (results.length) parts.push(groupCard(group, results, cmp));
  }
  const ownHistory = historyAgainstPeersCard(cmp);
  if (ownHistory) parts.push(ownHistory);
  parts.push(byYearCard());
  const summary = card("What the reports say");
  const notes = footnotes();
  summary.appendChild(byTopic(r.agent1.summary, notes));
  summary.appendChild(notes.box());
  parts.push(summary);
  $("tab-financials").replaceChildren(...parts);
}

function exhibitsView() { return (S.view && S.view.exhibits) || null; }

function exhibitCards() {  // the financial summary and the trading comparables, as in a bank's company report
  const ex = exhibitsView();
  if (!ex) return [];
  const out = [];
  if (ex.financial_summary.rows.length) {
    const box = card("Financial summary");
    box.appendChild(simpleTable({ ...ex.financial_summary, source: "Source: Company filings, Verity." }));
    out.push(box);
  }
  if (ex.comparables.rows.length > 1) {
    const box = card(`Trading comparables (${ex.comparables.period})`);
    box.appendChild(simpleTable({ ...ex.comparables, source: "Source: Company filings, share prices, Verity." }));
    out.push(box);
  }
  return out;
}

function peersCard(r) {
  const box = card("Compared with");
  const chips = el("div", null, "peer-chips");
  for (const p of r.peers.peers) {
    const chip = el("span", null, "peer-chip");
    chip.appendChild(el("strong", p.ticker));
    chip.appendChild(document.createTextNode(` ${p.name}`));
    chips.appendChild(chip);
  }
  if (!r.peers.peers.length) chips.appendChild(el("p", "No suitable peers: the company is compared with its own history only.", "empty"));
  box.appendChild(chips);
  if (r.peers.peers.length || r.peers.excluded.length) {
    const why = el("details", null, "more");
    why.appendChild(el("summary", "Why these peers"));
    const list = el("ul", null, "plain-list");
    for (const p of r.peers.peers) {
      const li = el("li");
      li.appendChild(el("strong", `${p.ticker}: `));
      li.appendChild(el("span", p.label, "pill"));
      li.appendChild(el("div", p.explanation, "hint"));
      list.appendChild(li);
    }
    for (const e of r.peers.excluded) list.appendChild(el("li", `Not used: ${e.ticker}. ${e.reason}`, "hint"));
    why.appendChild(list);
    box.appendChild(why);
  }
  return box;
}

function groupCard(group, results, cmp) {
  const box = card(group);
  const notes = footnotes();
  const summary = (cmp.groups.find((g) => g.group === group) || {}).lines || [];
  const { rows: formatted } = keyFigureRows();
  const wrap = el("div", null, "table-wrap");
  const t = el("table", null, "compact exhibit-table");
  const head = el("tr");
  for (const h of ["Indicator", "Value", "Peer median", "Difference", "Own history"]) head.appendChild(el("th", h));
  t.appendChild(head);
  for (const result of results) {
    const cells = cmp.cells[result.indicator] || {};
    const tr = el("tr", null, "row-main");
    const name = el("td");
    name.appendChild(el("span", "▸", "caret"));
    name.appendChild(document.createTextNode(result.name));
    tr.appendChild(name);
    const value = el("td", null, "num");
    value.appendChild(document.createTextNode(cells.value || "—"));
    value.appendChild(notes.mark(S.figureSources[result.indicator]));
    tr.appendChild(value);
    tr.appendChild(el("td", cells.peer_median || "—", "num"));
    tr.appendChild(el("td", cells.difference || "—", "num"));
    tr.appendChild(el("td", cells.own_history || "—", "num muted"));
    const more = el("tr", null, "row-details");
    more.hidden = true;
    const cell = el("td");
    cell.colSpan = 5;
    cell.appendChild(details(result, cells, (formatted[result.name] || [])[4], cmp, notes));
    more.appendChild(cell);
    tr.addEventListener("click", () => { more.hidden = !more.hidden; tr.classList.toggle("open", !more.hidden); });
    t.append(tr, more);
  }
  wrap.appendChild(t);
  box.appendChild(wrap);
  if (summary.length) box.appendChild(findingsPanel(summary, notes, group));
  box.appendChild(notes.box());
  return box;
}

function details(result, cells, statusText, cmp, notes) {
  const box = el("div", null, "details");
  const lines = cmp.by_indicator[result.indicator] || [];
  if (lines.length) box.appendChild(sentences(lines, notes, "details-text"));
  const peers = Object.entries(cells.peers || {});
  if (peers.length) {
    const each = el("div", null, "each-peer");
    each.appendChild(el("span", "Each peer: ", "label"));
    peers.forEach(([ticker, value], i) => {
      if (i) each.appendChild(document.createTextNode(" · "));
      each.appendChild(el("strong", ticker));
      each.appendChild(document.createTextNode(` ${value}`));
    });
    box.appendChild(each);
  }
  const facts = el("dl", null, "facts");
  const add = (term, text) => { if (text) { facts.appendChild(el("dt", term)); facts.appendChild(el("dd", text)); } };
  add("Status and notes", statusText);
  add("Formula", result.formula);
  add("Period", result.period);
  box.appendChild(facts);
  box.appendChild(button("All sources of this figure", () => openFigureSources(result), "cite"));
  return box;
}

function historyAgainstPeersCard(cmp) {
  const current0 = Object.fromEntries(S.report.agent1.indicators.current.map((x) => [x.indicator, x]));
  const bases = Object.keys(cmp.cells).filter((id) => id.endsWith("_hist_median") && current0[id] && !NO_DATA.includes(current0[id].status));
  if (!bases.length) return null;
  const current = Object.fromEntries(S.report.agent1.indicators.current.map((x) => [x.indicator, x]));
  const horizon = S.report.agent1.indicators.horizon_years || 5;
  const box = card(`Own ${horizon}-year history against the peers' own history`);
  const notes = footnotes();
  const lines = (cmp.groups.find((g) => g.group === "Historical comparison") || {}).lines || [];
  const peers = cmp.peers || [];
  const wrap = el("div", null, "table-wrap");
  const t = el("table", null, "compact exhibit-table");
  const head = el("tr");
  for (const h of ["Median of the multiple", S.report.company.ticker, ...peers, "Peer median"]) head.appendChild(el("th", h));
  t.appendChild(head);
  for (const id of bases) {
    const cells = cmp.cells[id];
    const tr = el("tr");
    tr.appendChild(el("td", (current[id] || {}).name || id));
    const own = el("td", null, "num strong");
    own.appendChild(document.createTextNode(cells.value));
    own.appendChild(notes.mark(S.figureSources[id]));
    tr.appendChild(own);
    for (const p of peers) tr.appendChild(el("td", (cells.peers || {})[p] || "—", "num"));
    tr.appendChild(el("td", cells.peer_median, "num"));
    t.appendChild(tr);
  }
  wrap.appendChild(t);
  box.appendChild(wrap);
  if (lines.length) box.appendChild(findingsPanel(lines, notes, "Historical comparison"));
  box.appendChild(notes.box());
  return box;
}

function byYearCard() {
  const box = card("By fiscal year");
  box.appendChild(chart());
  const hist = historyTable();
  if (hist) {
    const key = { ...hist, rows: hist.rows.filter((row) => KEY_HISTORY.includes(row[0])), notes: [] };
    if (key.rows.length) box.appendChild(simpleTable(key));
    const all = el("details", null, "more");
    all.appendChild(el("summary", `Show all ${hist.rows.length} indicators by fiscal year`));
    all.appendChild(simpleTable({ ...hist, notes: [] }));
    box.appendChild(all);
  }
  return box;
}

function simpleTable(block) {  // an exhibit (title, figures right-aligned, source underneath) or a plain table
  const wrap = el("div", null, `table-wrap${block.title ? " exhibit" : ""}`);
  if (block.title) wrap.appendChild(el("div", block.title, "exhibit-title"));
  const t = el("table", null, block.title ? "exhibit-table" : "");
  const head = el("tr");
  for (const c of block.columns) head.appendChild(el("th", c));
  t.appendChild(head);
  for (const row of block.rows) {
    const tr = el("tr", null, row[0] === "Peer median" ? "median-row" : "");
    row.forEach((cell, i) => tr.appendChild(el("td", cell, i ? "num" : "")));
    t.appendChild(tr);
  }
  wrap.appendChild(t);
  if (block.source) wrap.appendChild(el("p", block.source, "exhibit-source"));
  for (const note of block.notes || []) wrap.appendChild(el("p", note, "hint"));
  return wrap;
}

function keyDataBox(rows) {  // the report's key data: share price, market value, enterprise value, period and horizon
  const box = el("dl", null, "key-data");
  for (const [label, value] of rows) {
    box.appendChild(el("dt", label));
    box.appendChild(el("dd", value));
  }
  return box;
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
  return box;
}

const CALL_GROUPS = [["management", "Key points"], ["guidance", "Guidance"], ["analyst", "Analyst questions and assumptions"]];

function renderCallTab() {  // the earnings call, grouped by who is speaking; an analyst's assumption is not a fact
  const a2 = S.report.agent2;
  const call = card("Earnings call");
  const notes = footnotes();
  const doc = a2.call.documents[0];
  if (doc) call.appendChild(el("p", doc.title, "source-line"));
  for (const [kind, title] of CALL_GROUPS) {
    const chosen = a2.call.statements.filter((st) => st.kind === kind);
    if (!chosen.length) continue;
    call.appendChild(el("h3", title, "prose-heading"));
    call.appendChild(statementList(chosen, notes, (st) => st.speaker));
  }
  const other = a2.call.statements.filter((st) => !CALL_GROUPS.some(([kind]) => kind === st.kind));
  if (other.length) call.appendChild(statementList(other, notes, (st) => st.speaker));
  const questions = a2.call.questions || [];
  if (questions.length) {  // each analyst's question, then the summary of the answer
    call.appendChild(el("h3", "Questions and answers", "prose-heading"));
    const list = el("div", null, "qa-list");
    for (const q of questions) {
      const pair = el("div", null, "qa-pair");
      pair.appendChild(proseItem(q.question, notes, `Question · ${q.analyst}`));
      pair.appendChild(proseItem(q.answer, notes, `Answer · ${q.answered_by}`));
      list.appendChild(pair);
    }
    call.appendChild(list);
  }
  if (!a2.call.statements.length) call.appendChild(el("p", "No earnings-call material was available.", "empty"));
  if (!a2.call.statements.length) for (const note of a2.notes || []) call.appendChild(el("p", note, "empty"));  // why there is no call
  call.appendChild(notes.box());
  $("tab-call").replaceChildren(call);
}

function questionsCard() {  // the user's own questions, shown on the Overview only when there are any
  const questions = S.report.agent3.questions || [];
  if (!questions.length) return null;
  const box = card("Your questions");
  const notes = footnotes();
  for (const q of questions) {
    box.appendChild(el("h3", q.question, "prose-heading"));
    if (q.statements.length) box.appendChild(statementList(q.statements, notes));
    else box.appendChild(el("p", q.note, "empty"));
  }
  box.appendChild(notes.box());
  return box;
}

function disagreementsCard() {  // shown on the Overview only when there are any
  const a3 = S.report.agent3;
  const real = a3.disagreements.filter((d) => !d.note);  // older reports kept same-source items with a note
  if (!real.length) return null;
  const box = card("Where the sources disagree");
  const notes = footnotes();
  for (const d of real) {
    box.appendChild(el("h3", d.topic, "prose-heading"));
    box.appendChild(statementList(d.positions, notes, (p) => p.who));
  }
  box.appendChild(notes.box());
  return box;
}

// ---------- final report (same blocks as the PDF and Word files) ----------

function noteMarks(item) {  // footnote numbers after a point; the section's source list follows the section
  return el("sup", (item.notes || []).join(","), "fn-ref");
}

function renderBlock(block) {
  switch (block.type) {
    case "heading": return el(`h${Math.min(block.level + 1, 4)}`, block.text);
    case "paragraph": return el("p", block.text, { lead: "lead", note: "source-line" }[block.style] || "");
    case "commentary": {  // a section's headline and paragraph, with one source line
      const wrap = el("div", null, "commentary");
      if (block.headline) wrap.appendChild(el("p", block.headline, "commentary-headline"));
      const p = el("p", block.text);
      if ((block.notes || []).length) p.appendChild(noteMarks(block));
      wrap.appendChild(p);
      return wrap;
    }
    case "summarybox": {  // the research note's first-page box
      const box = el("div", null, "summarybox");
      const left = el("div");
      left.appendChild(el("div", "Key comparisons", "box-kicker"));
      const list = el("ul", null, "plain-list");
      for (const line of block.comparisons) list.appendChild(el("li", line));
      left.appendChild(list);
      const right = el("div", null, "summarybox-side");
      right.appendChild(el("div", "Key data", "box-kicker"));
      right.appendChild(keyDataBox(block.key_data));
      right.appendChild(el("p", `Peers: ${block.peers}`, "source-line"));
      box.append(left, right);
      return box;
    }
    case "statements": {
      const list = el("ul", null, "report-points");
      if (!block.items.length) list.appendChild(el("li", "Nothing to show.", "empty"));
      for (const item of block.items) {
        const li = el("li", null, item.label === "unverified" ? "unverified" : "");
        if (item.tag) li.appendChild(el("div", item.tag, "statement-tag"));
        const text = el("div");
        if (item.label === "unverified") text.appendChild(el("span", "Unverified", "badge-unverified"));
        text.appendChild(document.createTextNode(item.text));
        if ((item.notes || []).length) text.appendChild(noteMarks(item));
        li.appendChild(text);
        for (const issue of item.issues) li.appendChild(el("div", issue, "issue"));
        list.appendChild(li);
      }
      return list;
    }
    case "footnotes": {  // the section's sources in one line of small print, numbered as in its points
      const line = el("p", null, "report-notes");
      block.items.forEach((note, i) => {
        if (i) line.appendChild(el("span", "·", "note-sep"));
        line.appendChild(el("sup", String(note.number)));
        line.appendChild(note.url ? link(note.text, note.url) : document.createTextNode(note.text));
      });
      return line;
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
  const cover = el("div", null, "report-page report-cover");
  const top = el("div");
  top.appendChild(el("span", "Verity", "logo"));
  top.appendChild(el("p", "Financial Report Analysis Agent", "cover-sub"));
  top.appendChild(el("h1", r.company.name));
  top.appendChild(el("p", `${r.company.ticker} · analysis date ${r.analysis_date}`));
  cover.appendChild(top);
  cover.appendChild(el("p", `Prepared by three agents: reports and indicators, earnings call, combined report · indicator definitions ${r.agent1.indicators.definition_version}`));
  pages.appendChild(cover);

  const body = el("div", null, "report-page report-body");
  for (const block of S.view.blocks) {
    if (block.type === "heading" && block.level === 1) continue;  // shown on the cover
    body.appendChild(renderBlock(block));
  }
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

async function renderMyReports() {  // the analyses kept on the server, newest first
  const list = $("my-analyses");
  list.replaceChildren(el("li", "Loading…", "empty"));
  let analyses;
  try {
    analyses = await api("/api/analyses");
  } catch (e) {
    list.replaceChildren(el("li", e.message, "error"));
    return;
  }
  list.replaceChildren();
  if (!analyses.length) list.appendChild(el("li", "No analyses yet.", "empty"));
  for (const a of analyses) {
    const li = el("li");
    const info = el("div", null, "grow");
    info.appendChild(el("strong", `${a.name} (${a.ticker})`));
    info.appendChild(el("div", `Analysis date ${a.analysis_date} · run ${String(a.created_at || "").slice(0, 16).replace("T", " ")}`, "hint"));
    li.appendChild(info);
    li.appendChild(button("Open", async () => {
      try {
        await openAnalysis(a.id);
        location.hash = "#dashboard";
      } catch (e) {
        info.appendChild(el("div", e.message, "error"));
      }
    }, "btn btn-small btn-navy"));
    li.appendChild(link("PDF", `/api/analyses/${a.id}/download/pdf`, "btn btn-small"));
    li.appendChild(link("Word", `/api/analyses/${a.id}/download/docx`, "btn btn-small"));
    li.appendChild(button("Delete", async () => {
      if (!confirm(`Delete the analysis of ${a.name} (${a.analysis_date}) from this computer?`)) return;
      await api(`/api/analyses/${a.id}`, { method: "DELETE" });
      if (S.runningId === a.id) remember("fra.current", null);
      renderMyReports();
    }));
    list.appendChild(li);
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
  renderJobs();
  await loadFiles();
}

function formatBytes(n) {
  return n > 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1e3))} KB`;
}

async function loadTranscriptChoices() {
  const files = await api("/api/uploads").catch(() => []);
  const select = $("transcript-upload");
  const keep = select.value;
  select.replaceChildren(el("option", "None", ""));
  select.firstChild.value = "";
  for (const f of files.filter((x) => x.kind === "document")) {
    const option = el("option", f.filename);
    option.value = f.id;
    select.appendChild(option);
  }
  select.value = keep;
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
    loadTranscriptChoices();
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
  $("price-result").textContent = "Checking…";
  try {
    const q = await api(`/api/prices/${encodeURIComponent(ticker)}`);
    $("price-result").textContent = `${q.ticker} (${q.exchange}): ${q.close} ${q.currency}, closing price on ${q.price_date}`
      + `${q.stale ? " (stale: the latest session has no close yet)" : ""}. Source: ${q.source}.`;
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
  $("new-analysis-button").addEventListener("click", resetForm);
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
  const last = recall("fra.current", null);  // reopen the last analysis after a reload, if the server still has it
  if (last) openAnalysis(last).catch(() => remember("fra.current", null));
}

start();
