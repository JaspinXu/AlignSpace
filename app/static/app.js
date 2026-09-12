const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const state = { project: null, activeTab: "alignment" };
let runtime = {analysisMode:'offline', imageAnalysisEnabled:false};

const labels = {
  warm_modern: "Warm modern", japandi: "Japandi", contemporary_luxe: "Contemporary luxe",
  industrial: "Industrial", scandinavian: "Scandinavian", calm: "Calm", cosy: "Cosy",
  bright: "Bright", dramatic: "Dramatic", social: "Social", warm_neutral: "Warm neutrals",
  light_neutral: "Light neutrals", earthy: "Earthy tones", monochrome: "Monochrome",
  deep_tones: "Deep tones", light_oak: "Light oak", walnut: "Walnut", stone: "Stone",
  metal: "Metal", soft_textiles: "Soft textiles", soft_layered: "Soft layered light",
  natural_bright: "Bright natural light", warm_ambient: "Warm ambient light", statement: "Statement lighting",
  task_focused: "Task-focused light", family_relaxing: "Family relaxing", hosting: "Hosting",
  tv_and_media: "TV and media", flexible_use: "Flexible use", quiet_retreat: "Quiet retreat",
  open_flow: "Open flow", zoned: "Zoned layout", compact: "Compact layout",
  conversation_focused: "Conversation-focused", storage_led: "Storage-led", easy_care: "Easy care",
  balanced: "Balanced care", premium_care: "Premium care", not_sure: "Not sure yet",
  "15k_to_30k_sgd": "S$15,000–30,000", "30k_to_50k_sgd": "S$30,000–50,000",
  under_15k_sgd: "Under S$15,000", above_50k_sgd: "Above S$50,000", vision_agent: "Reference assistant"
};

function human(value) {
  return escapeHtml(labels[value] || String(value || "").replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase()));
}

async function api(path, options = {}) {
  const writing = options.method && options.method !== 'GET';
  if (writing) {
    document.querySelector('main').inert = true;
    $('#request-status').textContent = path.endsWith('/analysis-runs') ? 'Reviewing your notes… This can take up to a minute.' : 'Saving your changes…';
    $('#request-status').hidden = false;
  }
  try {
  const response = await fetch(path, {
    ...options,
    headers: options.body instanceof FormData ? options.headers : { "Content-Type": "application/json", ...(options.headers || {}) }
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = payload.error?.message || payload.detail?.message || payload.detail || "Something went wrong";
    throw new Error(typeof message === "string" ? message : JSON.stringify(message));
  }
  if (payload.id && state.project?.id === payload.id && !payload.viewerRole) payload.viewerRole = state.project.viewerRole;
  return payload;
  } finally {
    if (writing) {
      document.querySelector('main').inert = false;
      $('#request-status').hidden = true;
    }
  }
}

function notify(message, error = false) {
  const notice = $("#notice");
  notice.textContent = message;
  notice.hidden = false;
  notice.style.borderColor = error ? "#b85f3c" : "#294f40";
  clearTimeout(notify.timer);
  notify.timer = setTimeout(() => { notice.hidden = true; }, 4500);
}

async function loadProject(projectId) {
  state.project = await api(`/api/projects/${projectId}`);
  localStorage.setItem("alignspaceProjectId", projectId);
  render();
}

function showWorkspace() {
  $("#welcome").hidden = true;
  $("#workspace").hidden = false;
}

function render() {
  if (!state.project) return;
  showWorkspace();
  const project = state.project;
  $("#project-name").textContent = project.name;
  $("#project-meta").textContent = `${human(project.housingType || "Living room")} · ${human(project.budgetBand)} · Brief v${project.briefVersion}`;
  $("#stage-label").textContent = project.readiness.stage;
  const readiness = Math.round(project.readiness.score * 100);
  $("#readiness-label").textContent = `${project.attributes.filter(a => a.status === "confirmed").length}/8 decisions confirmed`;
  $("#progress-bar").style.width = `${project.readiness.coverage * 100}%`;
  renderQuestion(project.questionsByRole?.[project.viewerRole] || null);
  renderGuidance();
  renderMessages();
  renderShortlist();
  renderPreferences();
  renderReferences();
  renderProposals();
  renderConflicts();
  renderBrief();
  renderApprovals();
  applyRoleControls();
  if (state.activeTab === "activity") loadAudit();
}

function renderQuestion(question) {
  const card = $("#question-card");
  if (!question) {
    card.innerHTML = `<p class="eyebrow">Interview complete</p><h2>${state.project.readiness.readyForApproval ? "The brief is ready for both people to review." : "Your answers are saved. Your designer may still have decisions to review."}</h2><p class="question-why">Open the shared brief, resolve any conflicts, and complete the human approval gate.</p>`;
    return;
  }
  card.innerHTML = `
    <div class="question-meta"><span>Question ${question.sequence} of up to ${state.project.maxQuestions}</span><span>${human(question.target)} turn</span></div>
    <p class="eyebrow">One decision at a time</p>
    <h2>${question.prompt}</h2>
    <p class="question-why">Why now: ${question.rationale}</p>
    <div class="option-grid">${question.options.map(option => `<button class="option-button" type="button" data-answer="${option}">${human(option)}</button>`).join("")}</div>`;
  $$('[data-answer]', card).forEach(button => button.addEventListener("click", () => answerQuestion(question, button.dataset.answer)));
}

async function answerQuestion(question, value) {
  try {
    state.project = await api(`/api/projects/${state.project.id}/questions/${question.id}/answer`, {
      method: "POST",
      body: JSON.stringify({ role: question.target, value, expectedStateVersion: state.project.stateVersion })
    });
    render();
  } catch (error) { notify(error.message, true); }
}

function renderMessages() {
  const messages = [...state.project.agentMessages].reverse().slice(0, 8);
  $("#agent-messages").innerHTML = messages.map(message => `
    <div class="message ${message.sender}">
      <div class="message-head"><strong>${human(message.sender)}</strong><span>to ${human(message.recipient)}</span></div>
      <p>${escapeHtml(message.text)}</p>
    </div>`).join("") || '<p class="muted">The agent exchange will appear here.</p>';
}

function renderShortlist() {
  $("#candidate-count").textContent = state.project.shortlist.length;
  $("#shortlist").innerHTML = state.project.shortlist.map(candidate => `
    <div class="direction">
      <div class="direction-head"><h3>${candidate.title}</h3><span class="match">${state.project.readiness.coverage ? Math.round(candidate.matchScore * 100)+"% preference match" : "Explore"}</span></div>
      <p>${human(candidate.style)} · ${human(candidate.mood)} · ${human(candidate.material)} · ${human(candidate.layout)}</p>
      <p class="muted">Matches: ${candidate.matches.map(human).join(', ') || 'Explore this direction'}</p>
      <p class="muted">Trade-offs: ${candidate.tradeoffs.map(human).join(', ') || 'No preference mismatch'}${candidate.overBudget ? ' · Above your budget band' : ''}</p>
      <small>${human(candidate.budget)} · Illustrative, not a quote</small>
    </div>`).join("") || '<p>No sample directions meet your must-avoid choices. Your brief can still describe a custom direction.</p>';
}

function renderPreferences() {
  const form = $("#preferences-form");
  form.elements.goals.value = state.project.goals.join("\n");
  form.elements.antiPreferences.value = state.project.antiPreferences.join("\n");
}

function renderReferences() {
  $("#reference-list").innerHTML = state.project.references.map(reference => `
    <div class="reference-item">${reference.storageKey ? `<img class="reference-preview" src="/api/projects/${state.project.id}/references/${reference.id}/image" alt="Uploaded inspiration reference" loading="lazy">` : `<span class="sample-label">${reference.status === 'demo_note' ? 'Sample note' : 'Your note'} · no image</span>`}<strong>${escapeHtml(reference.filename)}</strong><br><span class="muted">${escapeHtml(reference.note || "No note added")}</span></div>`).join("");
}

function renderProposals() {
  const proposals = state.project.attributes.filter(item => item.status === "proposed");
  $("#analyse-button").disabled = !state.project.references.length;
  $("#proposal-list").innerHTML = proposals.map(item => `
    <div class="proposal">
      <p><strong>${human(item.dimension)}: ${human(item.value)}</strong><br><span class="muted">${item.evidence[0]?.sourceType === "image" ? "Image observation" : "From your note"} · Is this something you want?</span><br>${escapeHtml(item.evidence[0]?.description || '')}</p>
      <div class="proposal-actions"><button data-attribute="${item.id}" data-decision="confirm">Yes, use this</button><button data-attribute="${item.id}" data-decision="reject">Not for me</button></div>
    </div>`).join("");
  $$('[data-attribute]', $("#proposal-list")).forEach(button => button.addEventListener("click", () => reviewAttribute(button.dataset.attribute, button.dataset.decision)));
}

async function reviewAttribute(id, decision) {
  try {
    state.project = await api(`/api/projects/${state.project.id}/attributes/${id}/review`, {
      method: "POST", body: JSON.stringify({ decision, expectedStateVersion: state.project.stateVersion })
    });
    render();
  } catch (error) { notify(error.message, true); }
}

function renderConflicts() {
  const card = $("#conflicts-card");
  const open = state.project.conflicts.filter(item => ['open', 'escalated'].includes(item.status));
  card.innerHTML = `<div class="panel-heading"><div><p class="eyebrow">Alignment decisions</p><h2>Open conflicts</h2></div><span class="count-badge">${open.length}</span></div>` +
    (open.length ? open.map(item => `<div class="conflict"><p><strong>${escapeHtml(item.summary)}</strong><br><span class="muted">${escapeHtml(item.impact)}</span></p><div class="conflict-actions"><button data-resolve="${item.id}" data-resolution="accept_designer_constraint">Accept constraint</button><button data-resolve="${item.id}" data-resolution="retain_preference_after_discussion">Retain preference</button><button data-resolve="${item.id}" data-resolution="discuss_offline">Discuss offline</button></div></div>`).join("") : '<p class="muted">No unresolved disagreement. New constraints are cross-checked automatically.</p>');
  $$('[data-resolve]', card).forEach(button => button.addEventListener("click", () => resolveConflict(button.dataset.resolve, button.dataset.resolution)));
}

async function resolveConflict(id, resolution) {
  try {
    state.project = await api(`/api/projects/${state.project.id}/conflicts/${id}/resolve`, {
      method: "POST", body: JSON.stringify({ resolution, expectedStateVersion: state.project.stateVersion })
    });
    render();
  } catch (error) { notify(error.message, true); }
}

function renderBrief() {
  const brief = state.project.brief;
  const attributes = brief.attributes.filter(item => item.status === 'confirmed').map(item => `<div class="attribute"><span>${human(item.dimension)}</span><strong>${human(item.value)}</strong></div>`).join("") || '<p class="muted">Answer the adaptive questions to build the brief.</p>';
  $("#brief-content").innerHTML = `
    <div class="brief-section"><h3>Project intent</h3><ul>${brief.goals.map(item => `<li>${escapeHtml(item)}</li>`).join("") || "<li>Not stated yet</li>"}</ul></div>
    <div class="brief-section"><h3>Confirmed design language</h3><div class="attribute-grid">${attributes}</div></div>
    <div class="brief-section"><h3>Must avoid</h3><ul>${brief.antiPreferences.map(item => `<li>${escapeHtml(item)}</li>`).join("") || "<li>None recorded</li>"}</ul></div>
    <div class="brief-section"><h3>Designer constraints</h3><ul>${brief.constraints.map(item => `<li><strong>${human(item.category)}:</strong> ${escapeHtml(item.statement)} <span class="muted">(${item.waived ? "Withdrawn by designer" : human(item.severity)})</span></li>`).join("") || "<li>No constraints recorded</li>"}</ul></div>
    <div class="brief-section"><h3>Preferred directions</h3><ul>${state.project.shortlist.map(item => `<li>${item.title} — ${human(item.style)}, ${human(item.mood)}, ${human(item.layout)}</li>`).join("")}</ul></div>
    <div class="brief-section"><h3>Open decisions</h3><ul>${brief.unresolvedDecisions.map(item => `<li>${escapeHtml(item)}</li>`).join("") || "<li>None</li>"}</ul></div>`;
}

function renderApprovals() {
  $('#approval-help').textContent = state.project.status === 'approved' ? 'Both participants approved this version. Ready to export.' : state.project.readiness.readyForApproval ? 'Ready for both approvals.' : `Complete missing decisions: ${state.project.readiness.missingDimensions.map(human).join(', ') || 'none'}. Resolve open conflicts and critical professional review tasks. ${state.project.readiness.blockers?.join("; ") || ""}`;
  const roles = new Map(state.project.approvals.map(item => [item.role, item]));
  $("#approval-status").innerHTML = ["homeowner", "designer"].map(role => `<div class="approval-state"><span>${human(role)}</span><span class="${roles.has(role) ? "approved" : "waiting"}">${roles.has(role) ? "Approved" : "Waiting"}</span></div>`).join("");
  $$('[data-approve]').forEach(button => {
    const approved = roles.has(button.dataset.approve);
    button.disabled = approved || !state.project.readiness.readyForApproval || button.dataset.approve !== state.project.viewerRole;
    button.textContent = approved ? `${human(button.dataset.approve)} approved` : `Approve as ${button.dataset.approve}`;
  });
}

async function loadAudit() {
  try {
    const events = await api(`/api/projects/${state.project.id}/audit`);
    const runs = await api(`/api/projects/${state.project.id}/analysis-runs`);
    $('#usage-list').innerHTML = '<h3>Analysis runs</h3>' + (runs.map(r => `<p>${human(r.mode)} · ${human(r.status)} · ${r.latencyMs ?? '—'} ms · Input tokens: ${r.inputTokens ?? 'unavailable'} · Output tokens: ${r.outputTokens ?? 'unavailable'}</p>`).join('') || '<p>No model calls yet.</p>') + '<p class="muted">Token counts may be unavailable for failed calls. Monetary cost is not estimated without verified pricing. Check team quota in Slack.</p>';
    $("#audit-list").innerHTML = events.map(event => `<div class="audit-event"><code>v${event.state_version}</code><strong>${human(event.action)}</strong><span>${human(event.actor)} · ${new Date(event.created_at).toLocaleString()}</span></div>`).join("");
  } catch (error) { notify(error.message, true); }
}

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value ?? "";
  return div.innerHTML;
}

async function loadSavedProjects() {
  const projects = await api('/api/projects');
  $('#saved-projects').innerHTML = projects.length ? '<h3>Continue a project</h3>' + projects.map(p => `<button class="button ghost" data-open-project="${p.id}">${escapeHtml(p.name)}</button>`).join('') : '';
  $$('[data-open-project]').forEach(b => b.addEventListener('click', () => loadProject(b.dataset.openProject)));
}

function renderGuidance() {
  const p = state.project;
  $('#viewer-role').textContent = `You are here as the ${p.viewerRole || 'homeowner'}`;
  const complete = p.readiness.readyForApproval;
  $('#next-step-title').textContent = p.status === 'approved' ? 'Your shared brief is ready' : complete ? 'Review and approve together' : p.viewerRole === 'designer' ? 'Add the practical perspective' : 'Tell us what feels right';
  $('#next-step-help').textContent = complete ? 'Open Shared brief. Each participant approves from their own browser session. Any edit asks both people to review again.' : p.viewerRole === 'designer' ? 'Review the homeowner’s preferences, answer the layout and care questions, then add any constraints.' : 'Answer one question at a time. References are optional. Invite your designer to check layout, care and constraints.';
  $('#invite-button').hidden = p.viewerRole !== 'homeowner';
  $('#analysis-help').textContent = runtime.imageAnalysisEnabled ? 'Image observations require your confirmation. Visible does not mean preferred.' : runtime.analysisMode === 'gateway' ? 'AI reads your notes. This gateway has not passed image-input verification; image pixels are not analysed.' : 'Offline mode reads explicit keywords in your notes. It does not inspect image pixels.';
  $('#analyse-button').textContent = runtime.imageAnalysisEnabled ? 'Suggest elements from references' : 'Suggest preferences from notes';
}

function applyRoleControls() {
  const role = state.project.viewerRole;
  for (const id of ['preferences-form', 'reference-form']) {
    $$('input,textarea,button,select', $('#'+id)).forEach(el => el.disabled = role !== 'homeowner');
  }
  $$('input,textarea,button,select', $('#constraint-form')).forEach(el => el.disabled = role !== 'designer');
  $$('[data-resolve]').forEach(el => el.disabled = role !== 'designer');
  $$('[data-attribute]').forEach(el => el.disabled = role !== 'homeowner');
  $('#analyse-button').disabled = role !== 'homeowner' || !state.project.references.length;
  $('#offline-button').disabled = role !== 'homeowner' || !state.project.references.length;
  const selected = $('#decision-question').value;
  const own = decisionOptions.filter(q => q.target === role);
  $('#decision-question').innerHTML = own.map(q => `<option value="${q.id}">${human(q.dimension)}</option>`).join('');
  if (own.some(q => q.id === selected)) $('#decision-question').value = selected;
  updateDecisionValues();
}

$('#invite-button').addEventListener('click', async () => {
  try {
    const result = await api(`/api/projects/${state.project.id}/invitations`, {method:'POST',body:'{}'});
    const link = location.origin + '/' + result.invitationFragment;
    $('#invite-link').value = link; $('#invite-link').hidden = false;
    $('#invite-link').select();
    notify('Share this private link with your designer. It expires in 24 hours and works once. For solo testing, open it in a private window.');
  } catch (e) { notify(e.message,true); }
});
$('#refresh-button').addEventListener('click', () => loadProject(state.project.id).catch(e => notify(e.message,true)));
$('#offline-button').addEventListener('click', async () => {
  try {
    state.project = await api(`/api/projects/${state.project.id}/analysis-runs`, {method:'POST',body:JSON.stringify({mode:'offline',expectedStateVersion:state.project.stateVersion})});
    render(); notify('Offline note rules completed. No image pixels or model were used.');
  } catch (e) { notify(e.message,true); }
});
api('/api/runtime').then(r => {runtime=r; if(state.project) renderGuidance();});

$("#project-form").addEventListener("submit", async event => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  try {
    state.project = await api("/api/projects", { method: "POST", body: JSON.stringify({ name: form.get("name"), housingType: form.get("housingType") || null, budgetBand: form.get("budgetBand") }) });
    localStorage.setItem("alignspaceProjectId", state.project.id);
    render();
  } catch (error) { alert(error.message); }
});

$("#demo-button").addEventListener("click", async () => {
  try {
    state.project = await api("/api/demo", { method: "POST", body: "{}" });
    localStorage.setItem("alignspaceProjectId", state.project.id);
    render();
  } catch (error) { alert(error.message); }
});

$("#back-button").addEventListener("click", () => {
  localStorage.removeItem("alignspaceProjectId");
  state.project = null;
  loadSavedProjects();
  $("#workspace").hidden = true;
  $("#welcome").hidden = false;
});

$("#preferences-form").addEventListener("submit", async event => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const lines = value => String(value || "").split("\n").map(item => item.trim()).filter(Boolean);
  try {
    state.project = await api(`/api/projects/${state.project.id}/preferences`, { method: "PUT", body: JSON.stringify({ goals: lines(form.get("goals")), antiPreferences: lines(form.get("antiPreferences")), expectedStateVersion: state.project.stateVersion }) });
    render(); notify("Goals saved and shared with the designer-side agent.");
  } catch (error) { notify(error.message, true); }
});

$("#constraint-form").addEventListener("submit", async event => {
  event.preventDefault();
  const formElement = event.currentTarget;
  const form = new FormData(formElement);
  const payload = Object.fromEntries(form.entries());
  if (!payload.affectedDimension) delete payload.affectedDimension;
  if (!payload.incompatibleValue) delete payload.incompatibleValue;
  payload.expectedStateVersion = state.project.stateVersion;
  try {
    state.project = await api(`/api/projects/${state.project.id}/constraints`, { method: "POST", body: JSON.stringify(payload) });
    formElement.reset(); render(); notify("Constraint added and cross-checked against confirmed preferences.");
  } catch (error) { notify(error.message, true); }
});

$("#reference-form").addEventListener("submit", async event => {
  event.preventDefault();
  const formElement = event.currentTarget;
  const form = new FormData(formElement);
  try {
    if (!form.get('file')?.size) {
      state.project = await api(`/api/projects/${state.project.id}/reference-notes`, {method:'POST',body:JSON.stringify({note:form.get('note'),consent:form.get('consent')==='true',expectedStateVersion:state.project.stateVersion})});
    } else {
      state.project = await api(`/api/projects/${state.project.id}/references`, { method: "POST", body: form });
    }
    formElement.reset(); render(); notify("Reference uploaded with its provenance note.");
  } catch (error) { notify(error.message, true); }
});

$("#analyse-button").addEventListener("click", async () => {
  try {
    state.project = await api(`/api/projects/${state.project.id}/analysis-runs`, { method: "POST", body: JSON.stringify({expectedStateVersion:state.project.stateVersion}) });
    render(); notify("Reference analysis complete. Review every tentative attribute before it enters the brief.");
  } catch (error) { notify(error.message, true); }
});

$$('[data-approve]').forEach(button => button.addEventListener("click", async () => {
  const role = button.dataset.approve;
  try {
    state.project = await api(`/api/projects/${state.project.id}/approvals`, { method: "POST", body: JSON.stringify({ role, actorId: `${role}-demo-user`, expectedStateVersion: state.project.stateVersion }) });
    render(); notify(`${human(role)} approval recorded for brief v${state.project.briefVersion}.`);
  } catch (error) { notify(error.message, true); }
}));

$("#export-button").addEventListener("click", () => {
  const blob = new Blob([JSON.stringify(state.project.brief, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url; link.download = `${state.project.name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-brief-v${state.project.briefVersion}.json`;
  link.click(); URL.revokeObjectURL(url);
});

$$('.tab').forEach(button => button.addEventListener("click", () => {
  state.activeTab = button.dataset.tab;
  $$('.tab').forEach(item => item.classList.toggle("active", item === button));
  $$('.tab-panel').forEach(panel => { panel.hidden = panel.id !== `${state.activeTab}-panel`; });
  if (state.activeTab === "activity") loadAudit();
}));

const savedProject = localStorage.getItem("alignspaceProjectId");
if (location.hash.startsWith('#invite=')) {
  const token = location.hash.slice(8);
  history.replaceState(null, '', location.pathname);
  api('/api/invitations/claim', {method:'POST',body:JSON.stringify({token})}).then(r => loadProject(r.projectId)).catch(e => alert(e.message));
} else if (savedProject) loadProject(savedProject).catch(() => localStorage.removeItem("alignspaceProjectId"));
loadSavedProjects();

$('#guided-button').addEventListener('click', async () => {
  try {
    state.project = await api('/api/demo/start', {method: 'POST', body: '{}'});
    localStorage.setItem('alignspaceProjectId', state.project.id);
    render();
    notify('Review the sample note, suggest preferences, then answer a few questions. Invite a designer to finish the practical decisions.');
  } catch (error) { alert(error.message); }
});
$('#print-button').addEventListener('click', () => window.print());
let decisionOptions = [];
function updateDecisionValues() {
  const question = decisionOptions.find(q => q.id === $('#decision-question').value);
  if (!question) return;
  $('#decision-value').innerHTML = question.options.map(v => `<option value="${v}">${human(v)}</option>`).join('');
}
api('/api/decision-options').then(options => {
  decisionOptions = options;
  $('#decision-question').innerHTML = options.map(q => `<option value="${q.id}">${human(q.dimension)} (${q.target})</option>`).join('');
  updateDecisionValues();
}).catch(error => console.error(error));
$('#decision-question').addEventListener('change', updateDecisionValues);
$('#decision-form').addEventListener('submit', async event => {
  event.preventDefault();
  const q = decisionOptions.find(q => q.id === $('#decision-question').value);
  try {
    state.project = await api(`/api/projects/${state.project.id}/decisions/${q.id}`, {method:'PUT', body: JSON.stringify({role:q.target, value:$('#decision-value').value, expectedStateVersion:state.project.stateVersion})});
    render(); notify('Decision revised. Both approvals must be renewed.');
  } catch (error) { notify(error.message, true); }
});
