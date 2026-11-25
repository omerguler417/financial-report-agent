// Page interactions: company analysis with progress and the report view, output language, uploads with progress,
// transcription jobs with progress and resume, price check, saved reports.
const $ = (id) => document.getElementById(id);
const jobs = {}; // job id -> latest state
let config = null;

function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function button(label, onClick) {
  const b = el("button", label);
  b.type = "button";
  b.addEventListener("click", onClick);
  return b;
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || `Request failed (${response.status})`);
  return body;
}

function saveLanguage(code) {
  try { localStorage.setItem("outputLanguage", code); } catch (e) { /* storage unavailable */ }
}

function savedLanguage() {
  try { return localStorage.getItem("outputLanguage"); } catch (e) { return null; }
}

async function loadConfig() {
  config = await api("/api/config");
  const select = $("language");
  for (const [code, name] of Object.entries(config.supported_languages)) {
    const option = el("option", name);
    option.value = code;
    select.appendChild(option);
  }
  select.value = savedLanguage() || config.default_output_language;
  select.addEventListener("change", () => saveLanguage(select.value));
  $("limit-mb").textContent = config.max_upload_mb;
  $("limit-hours").textContent = config.max_recording_hours;

  const STATUS = { configured: "Configured (not yet checked live)", awaiting_configuration: "Awaiting configuration", no_adapter_yet: "No adapter yet" };
  const byKey = Object.fromEntries(config.services.map((s) => [s.key, s]));
  const problems = [];
  for (const key of ["transcription", "ffmpeg"]) {
    const s = byKey[key];
    if (s.status !== "configured") problems.push(`${s.label}: ${STATUS[s.status]}. ${s.missing.length ? "Add " + s.missing.join(", ") + ". " : ""}${s.how_to_configure}`);
  }
  $("model-status").textContent = problems.length ? "Transcription cannot run yet. " + problems.join(" ") : "Transcription is configured.";
  for (const s of config.services) {
    const li = el("li", `${s.label}: ${STATUS[s.status]}`, s.status === "configured" ? "ok" : "warn");
    if (s.status !== "configured") li.appendChild(el("div", (s.missing.length ? "Add " + s.missing.join(", ") + " to .env. " : "") + s.how_to_configure, "hint"));
    $("services").appendChild(li);
  }

  for (const item of config.features.working) $("working").appendChild(el("li", item));
  for (const item of config.features.awaiting_implementation) $("awaiting").appendChild(el("li", item));
}

function formatBytes(n) {
  return n > 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1e3))} KB`;
}

async function loadFiles() {
  const files = await api("/api/uploads");
  const list = $("files");
  list.replaceChildren();
  if (!files.length) list.appendChild(el("li", "No files yet.", "hint"));
  for (const f of files) {
    const latest = f.versions[f.versions.length - 1];
    const li = el("li");
    const origin = f.origin === "user_upload" ? "Uploaded by you" : "Retrieved from official source";
    li.appendChild(el("span", origin, f.origin === "user_upload" ? "tag upload" : "tag official"));
    li.appendChild(el("span", ` ${f.filename} · ${f.kind} · ${formatBytes(latest.size_bytes)}`));
    if (f.reporting_period) li.appendChild(el("span", ` · ${f.reporting_period}`));
    if (f.kind === "recording") li.appendChild(button("Transcribe", () => startJob(f.id)));
    li.appendChild(button("Delete", async () => {
      if (!confirm(`Delete ${f.filename}? This cannot be undone.`)) return;
      await api(`/api/uploads/${f.id}`, { method: "DELETE" });
      loadFiles();
    }));
    list.appendChild(li);
  }
}

function upload(event) {
  event.preventDefault();
  const form = new FormData($("upload-form"));
  const xhr = new XMLHttpRequest();
  const bar = $("upload-progress");
  bar.hidden = false;
  bar.value = 0;
  $("upload-message").textContent = "Uploading…";
  xhr.upload.addEventListener("progress", (e) => { if (e.lengthComputable) bar.value = (100 * e.loaded) / e.total; });
  xhr.addEventListener("load", () => {
    bar.hidden = true;
    const body = JSON.parse(xhr.responseText || "{}");
    if (xhr.status >= 400) {
      $("upload-message").textContent = body.detail || "Upload failed.";
      return;
    }
    $("upload-message").textContent = ["Uploaded " + body.filename + ".", ...(body.warnings || [])].join(" ");
    $("upload-form").reset();
    loadFiles();
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
    jobs[state.id] = state;
    renderJobs();
    poll(state.id);
  } catch (e) {
    alert(e.message);
  }
}

async function poll(jobId) {
  const state = await api(`/api/jobs/${jobId}`);
  jobs[jobId] = state;
  renderJobs();
  if (state.status === "running" || state.status === "queued") setTimeout(() => poll(jobId), 2000);
}

function renderJobs() {
  const list = $("jobs");
  list.replaceChildren();
  for (const job of Object.values(jobs)) {
    const li = el("li");
    li.appendChild(el("span", `${job.filename} → ${job.output_language}: ${job.current_step} `));
    const bar = el("progress");
    bar.max = 100;
    bar.value = job.progress_percent;
    li.appendChild(bar);
    if (job.status === "failed") {
      li.appendChild(el("span", ` Failed: ${job.error}`, "error"));
      li.appendChild(button("Resume", async () => { await api(`/api/jobs/${job.id}/resume`, { method: "POST" }); poll(job.id); }));
    }
    if (job.status === "completed") li.appendChild(button("View transcript", () => showTranscript(job.id)));
    list.appendChild(li);
  }
}

async function showTranscript(jobId) {
  const r = await api(`/api/jobs/${jobId}/result`);
  const box = $("transcript");
  box.replaceChildren();
  box.appendChild(el("h3", `${r.source.filename} (${r.transcript_type}${r.translation_type ? ", " + r.translation_type : ""})`));
  const flags = el("ul");
  for (const f of r.flags) flags.appendChild(el("li", f, "flag"));
  box.appendChild(flags);
  const table = el("table");
  const head = el("tr");
  for (const h of ["Time", "Speaker", `Original (${r.source_language})`, `Translation (${r.output_language})`]) head.appendChild(el("th", h));
  table.appendChild(head);
  for (const s of r.segments) {
    const row = el("tr", null, s.unclear ? "unclear" : "");
    row.appendChild(el("td", s.timestamp || "—"));
    row.appendChild(el("td", s.speaker || "unknown"));
    row.appendChild(el("td", (s.unclear ? "[unclear] " : "") + s.original));
    row.appendChild(el("td", s.translation || "(same language)"));
    table.appendChild(row);
  }
  box.appendChild(table);
}

async function checkPrice(event) {
  event.preventDefault();
  const ticker = $("ticker").value.trim();
  const date = $("price-date").value;
  $("price-result").textContent = "Checking…";
  try {
    const q = await api(`/api/prices/${encodeURIComponent(ticker)}${date ? "?on=" + date : ""}`);
    $("price-result").textContent = `${q.ticker} (${q.exchange}): ${q.close} ${q.currency} at the close on ${q.price_date}` +
      `${q.stale ? " — STALE" : ""}. Source: ${q.source}. ${q.note}`;
  } catch (e) {
    $("price-result").textContent = e.message;
  }
}

async function loadReports() {
  const reports = await api("/api/reports");
  const list = $("reports");
  list.replaceChildren();
  if (!reports.length) list.appendChild(el("li", "No saved reports yet. Reports are kept until you delete them.", "hint"));
  for (const r of reports) {
    const li = el("li", `${r.title} · ${r.created_at.slice(0, 10)} · ${r.citations} cited sources `);
    li.appendChild(button("Delete", async () => {
      if (!confirm(`Delete the report "${r.title}" and its saved sources?`)) return;
      await api(`/api/reports/${r.id}`, { method: "DELETE" });
      loadReports();
    }));
    list.appendChild(li);
  }
}

// ---- company analysis and report view ----

const STEP_NAMES = { queued: "Waiting to start", identify: "Finding the company", peers: "Choosing peers",
  agent1: "Agent 1: reports and indicators", agent2: "Agent 2: earnings call and news", agent3: "Agent 3: combined report", save: "Saving" };

async function runAnalysis(event, company) {
  if (event) event.preventDefault();
  const box = $("analysis-status");
  const query = company || $("company").value.trim();
  box.replaceChildren(el("p", "Starting…"));
  $("report-section").hidden = true;
  const response = await fetch("/api/analyses", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ company: query, demo: $("demo-mode").checked, output_language: $("language").value }),
  });
  const body = await response.json().catch(() => ({}));
  if (response.status === 409) {  // several companies match: let the user choose
    box.replaceChildren(el("p", body.detail));
    for (const c of body.candidates) box.appendChild(button(`${c.name} (${c.ticker})`, () => runAnalysis(null, c.ticker)));
    return;
  }
  if (response.status === 424) {  // live analysis: list every service still needed
    box.replaceChildren(el("p", body.detail, "warn"));
    const list = el("ul");
    for (const item of body.needs_configuration) list.appendChild(el("li", `${item.service}: ${item.how_to_configure}`));
    box.appendChild(list);
    return;
  }
  if (!response.ok || !body.id) {
    box.replaceChildren(el("p", body.detail || `Request failed (${response.status})`, "error"));
    return;
  }
  pollAnalysis(body.id);
}

async function pollAnalysis(id, failures = 0) {
  const box = $("analysis-status");
  let state;
  try {
    state = await api(`/api/analyses/${id}`);
  } catch (e) {  // a failed progress check is retried a few times instead of leaving the page waiting
    if (failures < 5) setTimeout(() => pollAnalysis(id, failures + 1), 1000);
    else box.replaceChildren(el("p", `Could not get the progress: ${e.message}`, "error"));
    return;
  }
  const bar = el("progress");
  bar.max = 100;
  bar.value = state.progress_percent;
  box.replaceChildren(el("span", `${state.company.name} (${state.company.ticker}): ${STEP_NAMES[state.current_step] || state.current_step} `), bar);
  if (state.status === "failed") box.appendChild(el("p", `Failed: ${state.error}`, "error"));
  else if (state.status === "completed") showReport(id);
  else setTimeout(() => pollAnalysis(id), 1000);
}

function sourcesLine(sources) {
  const line = el("div", null, "sources");
  line.appendChild(el("span", "Source: "));
  sources.forEach((s, i) => {
    if (i) line.appendChild(el("span", "; "));
    if (s.url) {
      const a = el("a", s.text);
      a.href = s.url;
      a.target = "_blank";
      a.rel = "noopener";
      line.appendChild(a);
    } else line.appendChild(el("span", s.text));
  });
  return line;
}

function renderBlock(block) {
  switch (block.type) {
    case "banner": return el("div", block.text, "banner");
    case "heading": return el(`h${Math.min(block.level + 1, 4)}`, block.text, block.level === 1 ? "report-title" : "");
    case "paragraph": return el("p", block.text);
    case "statements": {
      const list = el("ul", null, "statements");
      if (!block.items.length) list.appendChild(el("li", "Nothing to show.", "hint"));
      for (const item of block.items) {
        const li = el("li", null, item.label === "unverified" ? "unverified" : "");
        if (item.tag) li.appendChild(el("div", item.tag, "tag-line"));
        if (item.label === "unverified") li.appendChild(el("span", "Unverified", "badge"));
        li.appendChild(el("span", item.text));
        if (item.sources.length) li.appendChild(sourcesLine(item.sources));
        for (const issue of item.issues) li.appendChild(el("div", issue, "issue"));
        list.appendChild(li);
      }
      return list;
    }
    case "table": {
      const wrap = el("div", null, "table-wrap");
      const table = el("table");
      const head = el("tr");
      for (const c of block.columns) head.appendChild(el("th", c));
      table.appendChild(head);
      for (const row of block.rows) {
        const tr = el("tr");
        for (const cell of row) tr.appendChild(el("td", cell));
        table.appendChild(tr);
      }
      wrap.appendChild(table);
      for (const note of block.notes || []) wrap.appendChild(el("p", note, "hint"));
      return wrap;
    }
    case "list": {
      const wrap = el("div");
      if (block.title) wrap.appendChild(el("h4", block.title));
      const list = el("ul", null, block.style === "warn" ? "warn-list" : "");
      for (const item of block.items) list.appendChild(el("li", item));
      wrap.appendChild(list);
      return wrap;
    }
    default: return el("p", block.text || "");
  }
}

async function showReport(id) {
  const view = await api(`/api/analyses/${id}/view`);
  const box = $("report");
  box.replaceChildren(...view.blocks.map(renderBlock));
  if (view.demo_label) box.appendChild(el("div", view.demo_label, "banner"));  // the label at the end as well as the top
  const downloads = el("div", null, "downloads");
  downloads.appendChild(el("span", "Download the full report: "));
  for (const [kind, label] of [["pdf", "Download PDF"], ["docx", "Download Word"]]) {
    const link = el("a", label, "button-link");
    link.href = `/api/analyses/${id}/download/${kind}`;
    downloads.appendChild(link);
  }
  box.appendChild(downloads);
  $("report-section").hidden = false;
  $("report-section").scrollIntoView({ behavior: "smooth" });
}

$("analysis-form").addEventListener("submit", runAnalysis);
$("upload-form").addEventListener("submit", upload);
$("price-form").addEventListener("submit", checkPrice);
loadConfig().then(loadFiles).then(loadReports).catch((e) => { $("upload-message").textContent = e.message; });
