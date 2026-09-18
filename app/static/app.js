const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const state = { project: null, activeTab: "alignment" };
let runtime = {analysisMode:'offline', imageAnalysisEnabled:false};

const labels = {
  no_fixed_style: "No fixed style — combine individual preferences",
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
  vision_agent: "Reference assistant"
};

// Illustrative palettes support comparison; they are not generated room proposals.
const palettes = {
  warm_modern: ['#d9cbb8','#ad8b63','#656a50','#eee8dd'],
  japandi: ['#e3ddce','#bda57e','#525843','#d0ccc0'],
  contemporary_luxe: ['#d2c9bd','#887354','#46473f','#e9e4db'],
  industrial: ['#a9a49b','#656562','#815e43','#d7d0c5'],
  scandinavian: ['#ebe6dc','#cdb58c','#8b9b91','#d8d7c8'],
  warm_neutral: ['#e4d8c5','#bdab92','#8a7660'],
  light_neutral: ['#f0ece3','#d9d6cb','#b9b8ac'],
  earthy: ['#b3a17a','#876647','#747953'],
  monochrome: ['#e4e1da','#92938b','#393d38'],
  deep_tones: ['#454f42','#706051','#3c4245']
};
function paletteMarkup(value, className) {
  const colours = palettes[value];
  return colours ? `<span class="${className}" aria-hidden="true">${colours.map(colour => `<${className === 'option-swatch' ? 'i' : 'span'} style="background:${colour}"></${className === 'option-swatch' ? 'i' : 'span'}>`).join('')}</span>` : '';
}

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
  if (!$("#welcome").hidden) {
    selectTab('alignment');
    window.scrollTo({top: 0, behavior: 'instant'});
  }
  $("#welcome").hidden = true;
  $("#workspace").hidden = false;
}

function render() {
  if (!state.project) return;
  showWorkspace();
  const project = state.project;
  $("#project-name").textContent = project.name;
  $("#project-meta").textContent = `${human(project.housingType || "Living room")} · Brief v${project.briefVersion}`;
  $("#stage-label").textContent = project.readiness.stage;
  $("#readiness-label").textContent = `${project.attributes.filter(a => a.status === "confirmed").length}/8 decisions confirmed`;
  $("#progress-bar").style.width = `${project.readiness.coverage * 100}%`;
  const confirmed = project.attributes.filter(a => a.status === 'confirmed');
  $('#decision-ribbon').innerHTML = confirmed.length ? confirmed.map(a => `<div class="decision-chip"><span>${human(a.dimension)}</span>${human(a.value)} <span aria-hidden="true">✓</span></div>`).join('') : '<div class="decision-chip empty">Your design language will take shape here, one decision at a time.</div>';
  renderQuestion(project.questionsByRole?.[project.viewerRole] || null);
  renderGuidance();
  renderMessages();
  renderShortlist();
  renderBelief();
  renderPreferences();
  renderReferences();
  renderProposals();
  renderConflicts();
  renderBrief();
  renderApprovals();
  applyRoleControls();
  if (state.activeTab === "activity") loadAudit();
}

function bilingual(en, zh) {
  return `<span data-en="${escapeHtml(en)}" data-zh="${escapeHtml(zh || en)}">${escapeHtml(en)}</span>`;
}
async function interviewAction(action) {
  try {
    state.project = await api(`/api/projects/${state.project.id}/interview`, {method:'POST', body:JSON.stringify({role:state.project.viewerRole, action, expectedStateVersion:state.project.stateVersion})});
    render();
  } catch(error) { notify(error.message, true); }
}
function renderQuestion(question) {
  const card = $("#question-card");
  const project = state.project;
  const paused = project.interviewPaused?.[project.viewerRole];
  if (!question && (paused || project.questionCount >= project.maxQuestions)) {
    card.innerHTML = `<p class="eyebrow">A moment to reflect</p><h2>${paused ? 'Your answers are saved. Come back whenever you like.' : 'Ten more decisions made. Would you like to go deeper?'}</h2><p class="question-why">Continue with up to 10 more questions shaped by your answers, or review your brief now. More detail is optional.</p><div class="round-actions"><button class="button primary" id="continue-interview">Continue exploring</button><button class="button ghost" id="review-round">Review my brief</button></div>`;
    $('#continue-interview').addEventListener('click', () => interviewAction('continue'));
    $('#review-round').addEventListener('click', async () => { if (!paused) await interviewAction('pause'); selectTab('brief'); });
    return;
  }
  if (!question) {
    card.innerHTML = `<p class="eyebrow">Interview complete</p><h2>${state.project.readiness.readyForApproval ? "The brief is ready for both people to review." : "Your answers are saved. Your designer may still have decisions to review."}</h2><p class="question-why">Open the shared brief, resolve any conflicts, and complete the human approval gate.</p>`;
    return;
  }
  card.innerHTML = `
    <div class="question-meta"><span>Round ${Math.floor((question.sequence-1)/10)+1} · Question ${(question.sequence-1)%10+1} / 10</span><span>${human(question.target)} turn</span></div>
    <p class="eyebrow">One decision at a time</p>
    <h2>${question.promptZh ? bilingual(question.prompt, question.promptZh) : escapeHtml(question.prompt)}</h2>
    <p class="question-why">Why now: ${question.rationaleZh ? bilingual(question.rationale, question.rationaleZh) : escapeHtml(question.rationale)}</p>
    <div class="option-grid">${question.options.map(option => `<button class="option-button" type="button" data-answer="${option}">${paletteMarkup(option,'option-swatch')}${question.optionsZh?.[option] ? bilingual(option, question.optionsZh[option]) : human(option)}</button>`).join("")}</div><button class="text-button" id="pause-interview">Save and pause questions</button>`;
  $("#pause-interview").addEventListener("click", () => interviewAction("pause"));
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

function knowledgeMarkup(items) {
  return items.filter(item => item.kind === 'knowledge_reference').map(item => `
    <article class="direction knowledge-reference">
      <p class="eyebrow">Design reference · secondary source</p>
      <h3>${escapeHtml(item.title)}</h3>
      <p class="muted">${escapeHtml(item.section)} · Related topics: ${item.relevantDimensions.map(human).join(', ') || 'General context'}</p>
      <details class="source-definition" open><summary>Read the definition & source excerpt</summary>
        <p class="source-excerpt">${escapeHtml(item.text)}</p>
        <p class="muted">${escapeHtml(item.verification)}</p>
      </details>
      <p class="muted">Discuss how these ideas fit your activities, space and care preferences.</p>
    </article>`).join('');
}

function renderShortlist() {
  const refs = state.project.shortlist.filter(item => item.kind === 'knowledge_reference');
  $("#candidate-count").textContent = refs.length;
  $("#shortlist").innerHTML = knowledgeMarkup(refs) || '<p>No supporting excerpts yet. Confirm a preference to search the handbook. Your brief can describe a custom direction even when the library has no match.</p>';
  const terms = state.project.terminology || [];
  if (terms.length) $("#shortlist").innerHTML += `<div class="direction"><h3>Shared terminology</h3>${terms.map(term => `<p><a href="${escapeHtml(term.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(term.preferredLabel)} · Getty AAT ↗</a><br><small>${escapeHtml(term.mappingRelation)}. ${escapeHtml(term.attribution)} · ${escapeHtml(term.license)}</small></p>`).join('')}</div>`;
}


const beliefStatus = {
  confirmed: ['Confirmed', '已确认'], leaning: ['Leaning — please check', '倾向明显，请确认'],
  uncertain: ['Still open', '尚未明确'], blocked: ['Blocked by a constraint', '受约束限制'],
};
const actionLabels = {
  ask: ['Go to the question', '前往问题'], confirm: ['Review the suggestion', '查看建议'],
  invite: ['Create invitation link', '生成邀请链接'], refresh: ['Refresh shared changes', '刷新共享内容'],
  edit: ['Open the shared brief', '打开共享简报'], resume: ['Continue exploring', '继续探索'],
  show: ['Add a comparison note', '添加对比说明'], recommend: ['Open the conflict', '查看冲突'],
  present: ['Open the shared brief', '打开共享简报'], defer: ['Add a note', '添加说明'],
};

function renderBelief() {
  const p = state.project;
  const action = p.nextActions?.[p.viewerRole || 'homeowner'];
  const box = $('#next-action');
  if (!action) { box.innerHTML = ''; } else {
    const compare = action.compare ? `<p class="muted">${human(action.compare[0])} ↔ ${human(action.compare[1])}</p>` : '';
    const value = action.value ? `<p class="next-action-value">${human(action.dimension)}: ${human(action.value)}</p>` : '';
    const labelKey = action.resumeInterview ? 'resume' : action.waitingFor ? (p.viewerRole === 'homeowner' ? 'invite' : 'refresh') : action.blocker ? 'edit' : action.action;
    const [en, zh] = actionLabels[labelKey] || actionLabels.defer;
    box.innerHTML = `<h3>${escapeHtml(action.title)}</h3>${value}<p class="muted">${escapeHtml(action.reason)}</p>${compare}
      <button class="button secondary" type="button" id="next-action-button">${bilingual(en, zh)}</button>
      <p class="next-action-why"><small>${bilingual(`Expected value ${action.expectedReward.toFixed(2)} · uncertainty removed ${action.components.uncertaintyReduction.toFixed(2)} bits · hand-set weights, not learned`, `预期价值 ${action.expectedReward.toFixed(2)} · 预计减少不确定性 ${action.components.uncertaintyReduction.toFixed(2)} 比特 · 权重为人工设定，尚未经数据学习`)}</small></p>`;
    $('#next-action-button').addEventListener('click', () => followAction(action));
  }
  const dims = p.belief?.dimensions || {};
  $('#belief-list').innerHTML = Object.values(dims).map(entry => {
    const [en, zh] = beliefStatus[entry.status] || beliefStatus.uncertain;
    const top = entry.status === 'uncertain' && !entry.evidenceCount ? 'No evidence yet' : human(entry.top);
    const width = entry.status === 'confirmed' ? 100 : entry.evidenceCount ? Math.round(entry.topProbability * 100) : 0;
    return `<div class="belief-row ${entry.status}">
      <div class="belief-head"><strong>${human(entry.dimension)}</strong><span class="belief-status">${bilingual(en, zh)}</span></div>
      <div class="belief-bar" aria-hidden="true"><span style="width:${width}%"></span></div>
      <small>${top}${entry.status === 'confirmed' || !entry.evidenceCount ? '' : ` · ${Math.round(entry.topProbability * 100)}%`}</small>
    </div>`;
  }).join('');
}

function followAction(action) {
  const targets = {ask: '#question-card', confirm: '#proposal-list', recommend: '#conflicts-card', show: '#reference-form', defer: '#reference-form'};
  if (action.action === 'present' || action.blocker) { selectTab('brief'); return; }
  if (action.resumeInterview) { interviewAction('continue'); return; }
  if (action.waitingFor) {
    if (state.project.viewerRole === 'homeowner' && !$('#invite-button').hidden) $('#invite-button').click();
    else $('#refresh-button').click();
    return;
  }
  const target = $(targets[action.action]);
  target?.scrollIntoView({behavior: 'smooth', block: 'center'});
  if (action.action === 'show' || action.action === 'defer') $('#reference-form input[name="note"]')?.focus({preventScroll: true});
}

function renderPreferences() {
  const form = $("#preferences-form");
  form.elements.goals.value = state.project.goals.join("\n");
  form.elements.antiPreferences.value = state.project.antiPreferences.join("\n");
}

function renderReferences() {
  $("#reference-list").innerHTML = state.project.references.map(reference => `
    <div class="reference-item ${reference.status === 'catalogue_link' ? 'catalogue-reference' : ''}">${reference.status === 'catalogue_link' && /^https:\/\/d1hy6t2xeg0mdl\.cloudfront\.net\/image\//.test(reference.sourceDetails?.imageUrl || '') ? `<img class="reference-preview" src="${escapeHtml(reference.sourceDetails.imageUrl)}" alt="${escapeHtml(reference.filename)}" loading="lazy" referrerpolicy="no-referrer">` : reference.storageKey ? `<img class="reference-preview" src="/api/projects/${state.project.id}/references/${reference.id}/image" alt="Uploaded inspiration reference" loading="lazy">` : `<span class="sample-label">${reference.status === 'catalogue_link' ? 'Saved Singapore home' : reference.status === 'demo_note' ? 'Sample note' : 'Your note'}</span>`}<strong>${escapeHtml(reference.filename)}</strong><br><span class="muted" translate="no">${escapeHtml(reference.note || "")}</span>${reference.status === 'catalogue_link' && /^https:\/\/qanvast\.com\/sg\/[a-z0-9/-]+$/.test(reference.sourceUrl || '') ? `<br><a href="${reference.sourceUrl}" target="_blank" rel="noopener noreferrer">View original project on Qanvast ↗</a><br><small>${escapeHtml(reference.sourceDetails?.style || 'Choose the details you like')} · ${escapeHtml(reference.sourceDetails?.flatType || 'Home reference')}</small>` : ''}</div>`).join("") || '<p class="reference-empty">Your inspiration board starts with one good detail.</p>';
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
    <div class="brief-section"><h3>Project intent</h3><ul>${brief.goals.map(item => `<li translate="no">${escapeHtml(item)}</li>`).join("") || "<li>Not stated yet</li>"}</ul></div>
    <div class="brief-section"><h3>Confirmed design language</h3><div class="attribute-grid">${attributes}</div></div>
    <div class="brief-section"><h3>Design details</h3>${(brief.designDetails || []).map(d => `<div class="detail-answer"><strong>${bilingual(d.prompt, d.promptZh)}</strong><p>${bilingual(d.value, d.valueZh)}${d.needsReview ? " · Review after your preference changed" : ""}</p></div>`).join("") || "<p>Optional details will appear here.</p>"}</div>
    <div class="brief-section"><h3>Must avoid</h3><ul>${brief.antiPreferences.map(item => `<li translate="no">${escapeHtml(item)}</li>`).join("") || "<li>None recorded</li>"}</ul></div>
    <div class="brief-section"><h3>Designer constraints</h3><ul>${brief.constraints.map(item => `<li><strong>${human(item.category)}:</strong> <span translate="no">${escapeHtml(item.statement)}</span> <span class="muted">(${item.waived ? "Withdrawn by designer" : human(item.severity)})</span></li>`).join("") || "<li>No constraints recorded</li>"}</ul></div>
    <div class="brief-section"><h3>Supporting design references</h3>${knowledgeMarkup(brief.knowledgeReferences || []) || "<p>No supporting excerpts recorded.</p>"}</div>
    <div class="brief-section"><h3>Open decisions</h3><ul>${brief.unresolvedDecisions.map(item => `<li translate="no">${escapeHtml(item)}</li>`).join("") || "<li>None</li>"}</ul></div>`;
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
    $('#usage-list').innerHTML = '<h3>Analysis runs</h3>' + (runs.map(r => `<p>${human(r.mode)} · ${human(r.status)} · ${r.latencyMs ?? '—'} ms · Input tokens: ${r.inputTokens ?? 'unavailable'} · Output tokens: ${r.outputTokens ?? 'unavailable'}</p>`).join('') || '<p>No model calls yet.</p>') + '<p class="muted">Token counts may be unavailable for failed calls. Check team quota in Slack.</p>';
    $("#audit-list").innerHTML = events.map(event => `<div class="audit-event"><code>v${event.state_version}</code><strong>${human(event.action)}</strong><span>${human(event.actor)} · ${new Date(event.created_at).toLocaleString()}</span></div>`).join("");
  } catch (error) { notify(error.message, true); }
}

const HTML_ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
// String replacement rather than a throwaway element: render() calls this
// hundreds of times per pass, and quotes must be escaped for attribute values.
function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, character => HTML_ESCAPES[character]);
}

async function loadSavedProjects() {
  const projects = await api('/api/projects');
  $('#saved-projects').innerHTML = projects.length ? '<h3>Continue a project</h3>' + projects.map(p => `<button class="button ghost" data-open-project="${p.id}" translate="no">${escapeHtml(p.name)}</button>`).join('') : '';
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
  $('#constraint-role-help').textContent = role === 'designer' ? 'Bring the practical details into the brief. Explain the impact of each constraint.' : 'A space for your designer’s expertise. Invite them to add layout, care and everyday activities.';
  for (const id of ['preferences-form', 'reference-form']) {
    $$('input,textarea,button,select', $('#'+id)).forEach(el => el.disabled = role !== 'homeowner');
  }
  $$('input,textarea,button,select', $('#constraint-form')).forEach(el => el.disabled = role !== 'designer');
  $$('[data-resolve]').forEach(el => el.disabled = role !== 'designer');
  $$('[data-attribute]').forEach(el => el.disabled = role !== 'homeowner');
  $('#analyse-button').disabled = role !== 'homeowner' || !state.project.references.length;
  $('#offline-button').disabled = role !== 'homeowner' || !state.project.references.length;
  const selected = $('#decision-question').value;
  const own = availableDecisions().filter(q => q.target === role);
  $('#decision-question').innerHTML = own.map(q => `<option value="${q.id}">${q.detail ? escapeHtml(q.prompt) : human(q.dimension)}</option>`).join('');
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
    const inspirationIds = form.get('importInspiration') ? (window.AlignDiscovery?.selectedIds() || []) : [];
    state.project = await api("/api/projects", { method: "POST", body: JSON.stringify({ name: form.get("name"), housingType: form.get("housingType") || null, inspirationIds, inspirationConsent: inspirationIds.length > 0 }) });
    localStorage.setItem("alignspaceProjectId", state.project.id);
    render();
  } catch (error) { notify(error.message, true); }
});

$("#demo-button").addEventListener("click", async () => {
  try {
    state.project = await api("/api/demo", { method: "POST", body: "{}" });
    localStorage.setItem("alignspaceProjectId", state.project.id);
    render();
  } catch (error) { notify(error.message, true); }
});

function showHome() {
  localStorage.removeItem("alignspaceProjectId");
  state.project = null;
  loadSavedProjects().catch(e => { $('#saved-projects').textContent = e.message; });
  $("#workspace").hidden = true;
  $("#welcome").hidden = false;
}
$("#back-button").addEventListener("click", () => { showHome(); window.scrollTo({top: 0, behavior: 'instant'}); });
$$('[data-home-anchor]').forEach(link => link.addEventListener('click', event => {
  event.preventDefault();
  showHome();
  document.getElementById(link.dataset.homeAnchor).scrollIntoView({behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth'});
}));
$('.material-pin').addEventListener('click', event => {
  const open = event.currentTarget.getAttribute('aria-expanded') !== 'true';
  event.currentTarget.setAttribute('aria-expanded', String(open));
  event.currentTarget.textContent = open ? '−' : '+';
  $('#material-note').hidden = !open;
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

function selectTab(name) {
  state.activeTab = name;
  $$('.tab').forEach(item => {
    const selected = item.dataset.tab === name;
    item.classList.toggle('active', selected);
    item.setAttribute('aria-selected', String(selected));
  });
  $$('.tab-panel').forEach(panel => { panel.hidden = panel.id !== `${state.activeTab}-panel`; });
  if (state.activeTab === "activity" && state.project) loadAudit();
}
$$('.tab').forEach(button => button.addEventListener("click", () => selectTab(button.dataset.tab)));

const savedProject = localStorage.getItem("alignspaceProjectId");
if (location.hash.startsWith('#invite=')) {
  const token = location.hash.slice(8);
  history.replaceState(null, '', location.pathname);
  api('/api/invitations/claim', {method:'POST',body:JSON.stringify({token})}).then(r => loadProject(r.projectId)).catch(e => notify(e.message, true));
} else if (savedProject && !location.hash) loadProject(savedProject).catch(() => localStorage.removeItem("alignspaceProjectId"));
loadSavedProjects().catch(e => { $('#saved-projects').textContent = `Projects are unavailable: ${e.message}`; });

$('#guided-button').addEventListener('click', async () => {
  try {
    state.project = await api('/api/demo/start', {method: 'POST', body: '{}'});
    localStorage.setItem('alignspaceProjectId', state.project.id);
    render();
    notify('Review the sample note, suggest preferences, then answer a few questions. Invite a designer to finish the practical decisions.');
  } catch (error) { notify(error.message, true); }
});
$('#print-button').addEventListener('click', () => window.print());
let decisionOptions = [];
function availableDecisions() { return [...decisionOptions, ...(state.project?.detailQuestions || [])]; }
function updateDecisionValues() {
  const question = availableDecisions().find(q => q.id === $('#decision-question').value);
  if (!question) return;
  $('#decision-value').innerHTML = [...question.options, ...(question.detail ? ['not_sure'] : [])].map(v => `<option value="${v}">${question.detail && v === 'not_sure' ? 'Remove this detail' : human(v)}</option>`).join('');
}
api('/api/decision-options').then(options => {
  decisionOptions = options;
  $('#decision-question').innerHTML = options.map(q => `<option value="${q.id}">${human(q.dimension)} (${q.target})</option>`).join('');
  updateDecisionValues();
}).catch(error => console.error(error));
$('#decision-question').addEventListener('change', updateDecisionValues);
$('#decision-form').addEventListener('submit', async event => {
  event.preventDefault();
  const q = availableDecisions().find(q => q.id === $('#decision-question').value);
  try {
    state.project = await api(`/api/projects/${state.project.id}/decisions/${q.id}`, {method:'PUT', body: JSON.stringify({role:q.target, value:$('#decision-value').value, expectedStateVersion:state.project.stateVersion})});
    render(); notify('Decision revised. Both approvals must be renewed.');
  } catch (error) { notify(error.message, true); }
});
