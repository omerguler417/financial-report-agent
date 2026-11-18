// Page interactions: output language, uploads with progress, transcription jobs with progress and resume, price check, saved reports.
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

$("upload-form").addEventListener("submit", upload);
$("price-form").addEventListener("submit", checkPrice);
loadConfig().then(loadFiles).then(loadReports).catch((e) => { $("upload-message").textContent = e.message; });
