const state = {
  authenticated: false,
  user: null,
  tab: "in_progress",
  disputes: [],
  summary: null,
  activeId: null,
  detail: null,
  selectedStartCategory: null,
  emailDeliveryConfigured: null,
};

const $ = (id) => document.getElementById(id);

function readCookie(name) {
  return document.cookie
    .split(";")
    .map((item) => item.trim())
    .find((item) => item.startsWith(`${name}=`))
    ?.slice(name.length + 1) || "";
}

function money(cents, currency) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(cents / 100);
}

function showNotice(message) {
  const notice = $("notice");
  notice.textContent = message || "";
  notice.classList.toggle("hidden", !message);
}

function showPublicNotice(message) {
  const notice = $("publicNotice");
  notice.textContent = message || "";
  notice.classList.toggle("hidden", !message);
}

async function request(path, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  const csrfToken = readCookie("chargeback_copilot_csrf");
  if (!["GET", "HEAD", "OPTIONS"].includes(method) && csrfToken) {
    headers["X-CSRF-Token"] = decodeURIComponent(csrfToken);
  }
  const response = await fetch(path, {
    headers,
    credentials: "same-origin",
    ...options,
  });
  const payload = await response.json();
  if (!response.ok || payload.error) throw new Error(payload.error || "Request failed");
  return payload;
}

async function requestForm(path, formData) {
  const csrfToken = readCookie("chargeback_copilot_csrf");
  const headers = {};
  if (csrfToken) headers["X-CSRF-Token"] = decodeURIComponent(csrfToken);
  const response = await fetch(path, {
    method: "POST",
    headers,
    credentials: "same-origin",
    body: formData,
  });
  const payload = await response.json();
  if (!response.ok || payload.error) throw new Error(payload.error || "Request failed");
  return payload;
}

function showAuthPanel() {
  $("authPanel").scrollIntoView({ behavior: "smooth", block: "start" });
  const email = document.querySelector('#signinForm input[name="email"]');
  if (email) email.focus({ preventScroll: true });
}

async function enterPrivate(data) {
  state.authenticated = true;
  state.user = data.user;
  state.emailDeliveryConfigured = data.email_delivery_configured ?? state.emailDeliveryConfigured;
  $("publicPage").classList.add("hidden");
  $("privateApp").classList.remove("hidden");
  renderAccountStatus();
  showPublicNotice("");
  loadDisputes().catch((error) => showNotice(error.message));
}

function renderAccountStatus() {
  if (!state.user) return;
  $("accountStatus").textContent = state.user.email_verified
    ? `${state.user.email} · email verified`
    : `${state.user.email} · email not verified`;
  $("verifyEmailBtn").classList.toggle("hidden", Boolean(state.user.email_verified) || state.emailDeliveryConfigured === false);
}

async function demoLogin() {
  const data = await request("/api/auth/demo", { method: "POST", body: "{}" });
  await enterPrivate(data);
}

async function signup(event) {
  event.preventDefault();
  const formEl = event.currentTarget;
  const form = new FormData(formEl);
  const body = Object.fromEntries(form.entries());
  const data = await request("/api/auth/signup", { method: "POST", body: JSON.stringify(body) });
  formEl.reset();
  await enterPrivate(data);
  if (!data.email_verification_sent) {
    showNotice("Account created. Email delivery is not configured yet, so verification email was not sent.");
  }
}

async function signin(event) {
  event.preventDefault();
  const formEl = event.currentTarget;
  const form = new FormData(formEl);
  const body = Object.fromEntries(form.entries());
  const data = await request("/api/auth/login", { method: "POST", body: JSON.stringify(body) });
  formEl.reset();
  await enterPrivate(data);
}

async function requestPasswordReset(event) {
  event.preventDefault();
  const formEl = event.currentTarget;
  const body = Object.fromEntries(new FormData(formEl).entries());
  const data = await request("/api/auth/request-password-reset", { method: "POST", body: JSON.stringify(body) });
  formEl.reset();
  showPublicNotice(
    data.email_delivery_configured
      ? data.message
      : "Email delivery is not configured yet, so reset links cannot be sent."
  );
}

async function resetPassword(event) {
  event.preventDefault();
  const formEl = event.currentTarget;
  const body = Object.fromEntries(new FormData(formEl).entries());
  await request("/api/auth/reset-password", { method: "POST", body: JSON.stringify(body) });
  formEl.reset();
  showPublicNotice("Password updated. You can sign in with the new password.");
}

async function verifyEmail(event) {
  event.preventDefault();
  const formEl = event.currentTarget;
  const body = Object.fromEntries(new FormData(formEl).entries());
  await request("/api/auth/verify-email", { method: "POST", body: JSON.stringify(body) });
  formEl.reset();
  showPublicNotice("Email verified.");
}

async function requestEmailVerification() {
  const data = await request("/api/auth/request-email-verification", { method: "POST", body: "{}" });
  state.emailDeliveryConfigured = data.email_delivery_configured;
  renderAccountStatus();
  showNotice(data.email_sent ? "Verification email sent." : "Email delivery is not configured yet.");
}

async function logoutToPublic() {
  await request("/api/auth/logout", { method: "POST", body: "{}" }).catch(() => null);
  state.authenticated = false;
  state.user = null;
  $("privateApp").classList.add("hidden");
  $("publicPage").classList.remove("hidden");
}

async function deleteAccount() {
  const confirmed = window.prompt("Type DELETE to permanently delete this account and its packets.");
  if (confirmed !== "DELETE") {
    showNotice("Account deletion canceled.");
    return;
  }
  await request("/api/account/delete", {
    method: "POST",
    body: JSON.stringify({ confirmation: confirmed }),
  });
  state.authenticated = false;
  state.user = null;
  state.disputes = [];
  state.summary = null;
  state.activeId = null;
  state.detail = null;
  $("privateApp").classList.add("hidden");
  $("publicPage").classList.remove("hidden");
  showPublicNotice("Your account and stored packet data were deleted.");
}

async function loadDisputes() {
  const data = await request("/api/disputes");
  state.disputes = data.disputes;
  state.summary = data.summary;
  renderSummaryCards();
  renderTabs();
  renderCaseList();
  const filtered = filteredDisputes();
  if (!state.activeId || !filtered.some((item) => item.id === state.activeId)) {
    state.activeId = filtered[0]?.id || null;
  }
  if (state.activeId && state.tab !== "start_new") {
    await loadDetail(state.activeId);
  } else {
    state.detail = null;
    renderEmptyDetail();
  }
}

async function loadDetail(id) {
  state.activeId = id;
  state.detail = await request(`/api/disputes/${id}`);
  renderCaseList();
  renderDetail();
}

function setTab(tab) {
  state.tab = tab;
  showNotice("");
  renderTabs();
  renderSummaryCards();
  if (tab === "start_new") {
    state.activeId = null;
    state.detail = null;
    renderStartNew();
    return;
  }
  $("startNewView").classList.add("hidden");
  $("dashboardView").classList.remove("hidden");
  $("workspaceTitle").textContent = tab === "completed" ? "Completed Packets" : "In Progress Packets";
  $("caseListTitle").textContent = tab === "completed" ? "Completed" : "In Progress";
  renderCaseList();
  const filtered = filteredDisputes();
  state.activeId = filtered[0]?.id || null;
  if (state.activeId) {
    loadDetail(state.activeId).catch((error) => showNotice(error.message));
  } else {
    renderEmptyDetail();
  }
}

function renderTabs() {
  document.querySelectorAll(".tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === state.tab);
  });
}

function filteredDisputes() {
  if (state.tab === "completed") {
    return state.disputes.filter((item) => item.derived_status === "completed");
  }
  if (state.tab === "in_progress") {
    return state.disputes.filter((item) => item.derived_status === "in_progress");
  }
  return [];
}

function renderSummaryCards() {
  const summary = state.summary || {};
  const inProgress = state.disputes.filter((item) => item.derived_status === "in_progress");
  const completed = state.disputes.filter((item) => item.derived_status === "completed");
  const averageReadiness = inProgress.length
    ? Math.round(inProgress.reduce((total, item) => total + item.readiness_score, 0) / inProgress.length)
    : 0;
  const readyToGenerate = inProgress.filter((item) => item.readiness_score === 100).length;
  const pendingOutcome = completed.filter((item) => !item.outcome_feedback || item.outcome_feedback.outcome === "pending").length;
  const cardsByTab = {
    in_progress: [
      ["In-progress packets", summary.in_progress || 0, "Packets still being prepared"],
      ["High-priority gaps", summary.high_gap || 0, "Missing evidence to resolve"],
      ["Average readiness", `${averageReadiness}%`, "Across in-progress packets"],
      ["Ready to generate", readyToGenerate, "Packets with required evidence"],
    ],
    completed: [
      ["Completed packets", summary.completed || 0, "Ready or already exported"],
      ["Reported success", summary.reported_success || 0, "Issuer outcome marked success"],
      ["Reported failure", summary.reported_failure || 0, "Issuer outcome marked failure"],
      ["Pending outcome", pendingOutcome, "Waiting for issuer update"],
    ],
    start_new: [
      ["Total packets created", summary.total || 0, "All packets in this workspace"],
      ["In progress", summary.in_progress || 0, "Currently being prepared"],
      ["Completed", summary.completed || 0, "Ready to export or track"],
      ["Next step", "Choose situation", "Start with the dispute type"],
    ],
  };
  $("summaryCards").innerHTML = (cardsByTab[state.tab] || cardsByTab.in_progress)
    .map(
      ([label, value, caption]) => `
      <article>
        <span>${label}</span>
        <strong>${value}</strong>
        <em>${caption}</em>
      </article>
    `
    )
    .join("");
}

function renderCaseList() {
  if (state.tab === "start_new") return;
  const list = filteredDisputes();
  $("caseList").innerHTML = list.length
    ? list
        .map((item) => {
          const outcome = item.outcome_feedback ? `<em>${item.outcome_feedback.outcome}</em>` : "";
          return `
          <button class="case-card ${item.id === state.activeId ? "active" : ""}" data-id="${item.id}">
            <strong>${item.merchant_name}</strong>
            <span>${money(item.amount, item.currency)} · ${item.plan_label}</span>
            <div class="case-meta">
              <span>${item.readiness_score}% ready</span>
              <span>${item.high_gap_count} gaps</span>
              ${outcome}
            </div>
          </button>
        `;
        })
        .join("")
    : `<p class="empty-state">No packets in this status yet.</p>`;
  document.querySelectorAll(".case-card").forEach((button) => {
    button.addEventListener("click", () => loadDetail(button.dataset.id).catch((error) => showNotice(error.message)));
  });
}

function renderStartNew() {
  $("workspaceTitle").textContent = "Start New Packet";
  $("startNewView").classList.remove("hidden");
  $("dashboardView").classList.add("hidden");
  $("generateBtn").disabled = true;
  $("exportBtn").classList.add("disabled");
  renderCategorySelection(state.selectedStartCategory);
}

function renderEmptyDetail() {
  $("generateBtn").disabled = true;
  $("exportBtn").classList.add("disabled");
  $("completedView").classList.add("hidden");
  $("prepView").classList.remove("hidden");
  $("disputeSummary").innerHTML = "";
  $("readinessPanel").innerHTML = "<p class='empty-state'>Select a packet to view details.</p>";
  $("gaps").innerHTML = "";
  $("nextSteps").innerHTML = "";
  $("packetStatus").textContent = "";
  $("generateHelper").textContent = "";
  $("prepReview").innerHTML = "";
}

function renderDetail() {
  const detail = state.detail;
  const dispute = detail.dispute;
  const packet = detail.packet;
  const isCompleted = detail.derived_status === "completed";
  $("generateBtn").disabled = isCompleted;
  $("exportBtn").href = `/api/disputes/${dispute.id}/export`;
  $("exportBtn").classList.toggle("disabled", !detail.export_ready);
  $("completedView").classList.toggle("hidden", !isCompleted);
  $("prepView").classList.toggle("hidden", isCompleted);
  if (isCompleted) {
    renderCompletedDetail(detail);
    showNotice("");
    return;
  }
  $("disputeSummary").innerHTML = [
    ["Merchant", dispute.merchant_name],
    ["Amount", money(dispute.amount, dispute.currency)],
    ["Charge date", dispute.charge_date],
    ["Issuer", dispute.issuer_name],
    ["Status", detail.derived_status.replace("_", " ")],
    ["Summary", dispute.user_summary || "No summary entered"],
  ]
    .map(([label, value]) => `<div class="meta-row"><span>${label}</span><strong>${value}</strong></div>`)
    .join("");
  renderPrepAction(detail);
  renderReadiness(detail);
  renderGaps(detail.evidence_gaps);
  renderNextSteps(detail.next_steps);
  renderPrepReview(detail);

  if (packet?.validation_errors?.length) {
    showNotice(`Packet validation blocked export: ${packet.validation_errors.join("; ")}`);
  } else if (detail.evidence_gaps.some((gap) => gap.severity === "high")) {
    showNotice("This packet has important evidence gaps. Add evidence before exporting.");
  } else {
    showNotice("");
  }
}

function renderPrepAction(detail) {
  const topGap = sortedGaps(detail.evidence_gaps)[0];
  const ready = detail.readiness_score === 100;
  $("prepActionTitle").textContent = topGap ? `Add ${topGap.label.toLowerCase()}` : "Generate your packet";
  $("prepActionText").textContent = topGap
    ? topGap.suggested_action
    : "Required evidence is complete. Generate a packet, review the citations, then export when ready.";
  $("generateHelper").textContent = ready
    ? "Ready to generate an exportable packet."
    : "You can generate a draft, but export may stay blocked until required evidence is added.";
}

function renderCompletedDetail(detail) {
  const dispute = detail.dispute;
  const packet = detail.packet;
  $("completedTitle").textContent = `${dispute.merchant_name} packet is ready`;
  $("completedSummary").textContent = "Export the packet, submit through your issuer's official channel, then come back to track the real-life result.";
  $("completedExportBtn").href = `/api/disputes/${dispute.id}/export`;
  $("completedSnapshot").innerHTML = [
    ["Merchant", dispute.merchant_name],
    ["Amount", money(dispute.amount, dispute.currency)],
    ["Issuer", dispute.issuer_name],
    ["Category", detail.plan.label],
    ["Evidence progress", `${detail.evidence_progress.satisfied_required} of ${detail.evidence_progress.total_required} required items`],
    ["Readiness", `${detail.readiness_score}%`],
  ]
    .map(([label, value]) => `<div class="meta-row"><span>${label}</span><strong>${value}</strong></div>`)
    .join("");
  renderOutcomeInto("completedOutcomePanel", detail);
  $("completedAudit").innerHTML = `
    <details open>
      <summary>View packet summary</summary>
      <p>${packet.summary}</p>
      <p><strong>Suggested bank message:</strong> ${packet.suggested_bank_message}</p>
    </details>
    <details>
      <summary>View cited claims</summary>
      ${renderClaimList(packet)}
    </details>
    <details>
      <summary>View evidence timeline</summary>
      ${renderTimelineList(detail.timeline)}
    </details>
    <details>
      <summary>View uploaded files</summary>
      ${renderEvidenceFiles(detail.evidence_files || [])}
    </details>
    <details>
      <summary>View evidence checklist</summary>
      ${renderChecklistList(detail.plan.checklist)}
    </details>
  `;
}

function renderReadiness(detail) {
  const progress = detail.evidence_progress;
  $("readinessPanel").innerHTML = `
    <div class="score-row">
      <strong>${detail.readiness_score}%</strong>
      <span>${detail.export_reason}</span>
    </div>
    <div class="progress"><span style="width:${detail.readiness_score}%"></span></div>
    <p class="muted">${progress.satisfied_required} of ${progress.total_required} required evidence items satisfied.</p>
  `;
}

function renderChecklist(items) {
  $("checklist").innerHTML = renderChecklistList(items);
}

function renderChecklistList(items) {
  return items
    .map(
      (item) => `
      <div class="check-item">
        <span class="dot ${item.satisfied ? "ok" : ""}"></span>
        <div>
          <strong>${item.label}</strong>
          <div class="citations">${item.artifact_types.join(", ")}</div>
        </div>
        <span class="pill ${item.required && !item.satisfied ? "danger" : ""}">${item.required ? "Required" : "Helpful"}</span>
      </div>
    `
    )
    .join("");
}

function renderGaps(gaps) {
  const sorted = sortedGaps(gaps);
  $("gaps").innerHTML = sorted.length
    ? sorted
        .map(
          (gap) => `
      <div class="gap-item" data-requirement="${gap.requirement_key}">
        <span class="pill ${gap.severity === "high" ? "danger" : "warn"}">${gap.severity}</span>
        <p><strong>${gap.label}</strong></p>
        <p>${gap.explanation}</p>
        <p class="muted">${gap.suggested_action}</p>
        <button class="gap-add" type="button" data-requirement="${gap.requirement_key}">Add this evidence</button>
      </div>
    `
        )
        .join("")
    : `<p class="empty-state">No evidence gaps detected. Generate a packet and review the draft.</p>`;
  document.querySelectorAll(".gap-add").forEach((button) => {
    button.addEventListener("click", () => preselectEvidence(button.dataset.requirement));
  });
}

function sortedGaps(gaps) {
  return [...gaps].sort((a, b) => {
    if (a.severity === b.severity) return a.label.localeCompare(b.label);
    return a.severity === "high" ? -1 : 1;
  });
}

function renderTimeline(events) {
  $("timeline").innerHTML = renderTimelineList(events);
}

function renderTimelineList(events) {
  return events.length
    ? events
        .map(
          (event) => `
      <div class="event">
        <time>${event.date}</time>
        <p><strong>${event.title}</strong></p>
        <p>${event.description}</p>
        <div class="citations">${event.support_status} · ${event.evidence_ids.join(", ")}</div>
      </div>
    `
        )
        .join("")
    : `<p class="empty-state">Add evidence to build the timeline.</p>`;
}

function renderNextSteps(steps) {
  $("nextSteps").innerHTML = steps.map((step) => `<div class="step">${step}</div>`).join("");
}

function renderPrepReview(detail) {
  const packet = detail.packet;
  $("prepReview").innerHTML = `
    <details>
      <summary>View evidence checklist</summary>
      ${renderChecklistList(detail.plan.checklist)}
    </details>
    <details>
      <summary>View evidence timeline</summary>
      ${renderTimelineList(detail.timeline)}
    </details>
    <details>
      <summary>View uploaded files</summary>
      ${renderEvidenceFiles(detail.evidence_files || [])}
    </details>
    <details>
      <summary>View category guidance</summary>
      <p>${detail.plan.careful_guidance}</p>
      <p class="muted">This tool prepares information; it does not guarantee an issuer result.</p>
    </details>
    <details ${packet ? "open" : ""}>
      <summary>View generated draft</summary>
      ${packet ? renderPacketContent(packet) : '<p class="empty-state">Generate a packet to see a draft here.</p>'}
    </details>
  `;
  const status = $("packetStatus");
  if (packet) {
    status.textContent = packet.status;
    status.className = `pill ${packet.status === "blocked" ? "danger" : ""}`;
  } else {
    status.textContent = "not generated";
    status.className = "pill warn";
  }
}

function renderOutcome(detail) {
  renderOutcomeInto("outcomePanel", detail);
}

function renderOutcomeInto(containerId, detail) {
  const disabled = detail.derived_status !== "completed";
  const outcome = detail.outcome_feedback || { outcome: "pending", note: "" };
  $(containerId).innerHTML = `
    <p class="muted">Track the real-life issuer result after you submit. This is not a prediction or advice.</p>
    <form id="outcomeForm" class="stack-form">
      <label>Result
        <select name="outcome" ${disabled ? "disabled" : ""}>
          <option value="pending" ${outcome.outcome === "pending" ? "selected" : ""}>Pending</option>
          <option value="success" ${outcome.outcome === "success" ? "selected" : ""}>Success</option>
          <option value="failure" ${outcome.outcome === "failure" ? "selected" : ""}>Failure</option>
        </select>
      </label>
      <label>Update note
        <textarea name="note" rows="3" ${disabled ? "disabled" : ""} placeholder="Example: Bank issued temporary credit.">${outcome.note || ""}</textarea>
      </label>
      <button type="submit" ${disabled ? "disabled" : ""}>Save outcome</button>
    </form>
  `;
  $("outcomeForm").addEventListener("submit", (event) => saveOutcome(event).catch((error) => showNotice(error.message)));
}

function renderPacket(packet) {
  const status = $("packetStatus");
  if (!packet) {
    status.textContent = "";
    $("packet").className = "empty-state";
    $("packet").textContent = "Generate a packet after reviewing the checklist and evidence gaps.";
    return;
  }
  status.textContent = packet.status;
  status.className = `pill ${packet.status === "blocked" ? "danger" : ""}`;
  $("packet").className = "packet-grid";
  $("packet").innerHTML = renderPacketContent(packet);
}

function renderPacketContent(packet) {
  return `
    <div class="full">
      <p>${packet.summary}</p>
      <p><strong>Suggested bank message:</strong> ${packet.suggested_bank_message}</p>
    </div>
    <div>
      <h4>Cited Claims</h4>
      ${renderClaimList(packet)}
    </div>
    <div>
      <h4>Packet Safety</h4>
      <div class="step">${packet.disclaimer}</div>
      <div class="step">Every factual claim above includes evidence citations.</div>
    </div>
  `;
}

const REQUIREMENT_TO_EVIDENCE_TYPE = {
  transaction: "statement_transaction",
  cancellation: "cancellation_confirmation",
  merchant_response: "merchant_message",
  merchant_contact: "merchant_message",
  terms: "terms_or_policy",
  delivery: "delivery_status",
  refund_promise: "refund_promise",
  return_or_cancel: "return_proof",
  issuer_alert: "issuer_alert",
  merchant_relationship: "merchant_relationship",
};

function preselectEvidence(requirementKey) {
  const type = REQUIREMENT_TO_EVIDENCE_TYPE[requirementKey];
  if (type) {
    document.querySelector('#evidenceForm select[name="type"]').value = type;
  }
  document.querySelector('#evidenceForm input[name="title"]').focus();
}

function renderClaimList(packet) {
  return packet.claims
    .map(
      (claim) => `
        <div class="claim">
          <p>${claim.text}</p>
          <div class="citations">Evidence: ${claim.citation_evidence_ids.join(", ")}</div>
        </div>`
    )
    .join("") || '<p class="empty-state">No supported claims yet.</p>';
}

function renderEvidenceFiles(files) {
  return files.length
    ? files
        .map(
          (file) => `
      <div class="file-item">
        <strong>${file.original_filename}</strong>
        <span>${file.content_type} · ${Math.round(file.size_bytes / 1024)} KB</span>
        <div class="citations">Evidence: ${file.evidence_id} · Scan: ${file.scan_status}</div>
        <div class="file-actions">
          <a href="/api/evidence-files/${file.id}/download" target="_blank" rel="noreferrer">Download</a>
          <button type="button" class="text-button danger" data-delete-file="${file.id}">Delete</button>
        </div>
      </div>
    `
        )
        .join("")
    : '<p class="empty-state">No uploaded files yet.</p>';
}

async function deleteEvidenceFile(fileId) {
  const confirmed = window.confirm("Delete this uploaded file from the packet?");
  if (!confirmed) return;
  state.detail = await request(`/api/evidence-files/${fileId}`, { method: "DELETE" });
  await loadDisputes();
}

async function createCase(event) {
  event.preventDefault();
  if (!state.selectedStartCategory) {
    showNotice("Choose the situation before creating a packet.");
    return;
  }
  const formEl = event.currentTarget;
  const form = new FormData(formEl);
  const body = Object.fromEntries(form.entries());
  const detail = await request("/api/disputes", { method: "POST", body: JSON.stringify(body) });
  state.tab = "in_progress";
  state.activeId = detail.dispute.id;
  state.selectedStartCategory = null;
  formEl.reset();
  renderCategorySelection(null);
  $("startNewView").classList.add("hidden");
  $("dashboardView").classList.remove("hidden");
  await loadDisputes();
}

async function addEvidence(event) {
  event.preventDefault();
  const formEl = event.currentTarget;
  const form = new FormData(formEl);
  const file = form.get("file");
  if (file && file.size > 0) {
    state.detail = await requestForm(`/api/disputes/${state.activeId}/evidence-file`, form);
  } else {
    form.delete("file");
    const body = Object.fromEntries(form.entries());
    state.detail = await request(`/api/disputes/${state.activeId}/evidence`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  }
  formEl.reset();
  await loadDisputes();
}

async function generatePacket() {
  if (!state.activeId) return;
  const generatedDetail = await request(`/api/disputes/${state.activeId}/generate`, { method: "POST", body: "{}" });
  state.detail = generatedDetail;
  if (generatedDetail.derived_status === "completed") {
    state.tab = "completed";
  }
  await loadDisputes();
}

async function saveOutcome(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const body = Object.fromEntries(form.entries());
  state.detail = await request(`/api/disputes/${state.activeId}/outcome`, {
    method: "POST",
    body: JSON.stringify(body),
  });
  await loadDisputes();
}

document.querySelectorAll(".loginCta").forEach((button) => button.addEventListener("click", showAuthPanel));
$("demoLoginBtn").addEventListener("click", () => demoLogin().catch((error) => showPublicNotice(error.message)));
$("signupForm").addEventListener("submit", (event) => signup(event).catch((error) => showPublicNotice(error.message)));
$("signinForm").addEventListener("submit", (event) => signin(event).catch((error) => showPublicNotice(error.message)));
$("passwordResetRequestForm").addEventListener("submit", (event) => requestPasswordReset(event).catch((error) => showPublicNotice(error.message)));
$("passwordResetForm").addEventListener("submit", (event) => resetPassword(event).catch((error) => showPublicNotice(error.message)));
$("emailVerificationForm").addEventListener("submit", (event) => verifyEmail(event).catch((error) => showPublicNotice(error.message)));
$("backToPublicBtn").addEventListener("click", () => logoutToPublic().catch((error) => showNotice(error.message)));
$("verifyEmailBtn").addEventListener("click", () => requestEmailVerification().catch((error) => showNotice(error.message)));
$("deleteAccountBtn").addEventListener("click", () => deleteAccount().catch((error) => showNotice(error.message)));
document.querySelectorAll(".tab").forEach((button) => button.addEventListener("click", () => setTab(button.dataset.tab)));
$("newCaseForm").addEventListener("submit", (event) => createCase(event).catch((error) => showNotice(error.message)));
$("evidenceForm").addEventListener("submit", (event) => addEvidence(event).catch((error) => showNotice(error.message)));
$("generateBtn").addEventListener("click", () => generatePacket().catch((error) => showNotice(error.message)));

const START_CATEGORY_EVIDENCE = {
  canceled_subscription: {
    label: "I canceled but was still charged",
    evidence: ["Card statement charge", "Cancellation confirmation", "Merchant support response", "Subscription terms or renewal notice"],
  },
  not_received: {
    label: "I did not receive the item or service",
    evidence: ["Card statement or order confirmation", "Tracking or delivery status", "Merchant contact attempt", "Promised delivery date"],
  },
  refund_not_received: {
    label: "I was promised a refund but did not receive it",
    evidence: ["Original transaction", "Refund promise or approval", "Return or cancellation proof", "Merchant follow-up"],
  },
  unauthorized_charge: {
    label: "I do not recognize this charge",
    evidence: ["Card statement transaction", "What you know about the merchant", "Bank alert or issuer message", "Merchant explanation if available"],
  },
};

function renderCategorySelection(category) {
  state.selectedStartCategory = category;
  $("newCaseCategory").value = category || "";
  document.querySelectorAll(".category-card").forEach((card) => {
    card.classList.toggle("active", card.dataset.category === category);
  });
  const preview = $("evidencePreview");
  if (!category) {
    preview.classList.add("hidden");
    preview.innerHTML = "";
    return;
  }
  const config = START_CATEGORY_EVIDENCE[category];
  preview.classList.remove("hidden");
  preview.innerHTML = `
    <p class="label">Evidence preview</p>
    <h4>${config.label}</h4>
    <p class="muted">Top evidence that may help. You do not need everything now; we’ll help you add evidence next.</p>
    <div class="preview-list">
      ${config.evidence.map((item) => `<span>${item}</span>`).join("")}
    </div>
  `;
}

document.querySelectorAll(".category-card").forEach((card) => {
  card.addEventListener("click", () => renderCategorySelection(card.dataset.category));
});

function hydrateAuthTokensFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const resetToken = params.get("reset_password_token");
  const verifyToken = params.get("verify_email_token");
  if (resetToken) {
    $("passwordResetForm").querySelector('input[name="token"]').value = resetToken;
    showAuthPanel();
  }
  if (verifyToken) {
    $("emailVerificationForm").querySelector('input[name="token"]').value = verifyToken;
    showAuthPanel();
  }
}

document.addEventListener("click", (event) => {
  const target = event.target;
  if (target.matches("[data-add-gap]")) {
    preselectEvidence(target.dataset.addGap);
  }
  if (target.matches("[data-delete-file]")) {
    deleteEvidenceFile(target.dataset.deleteFile).catch((error) => showNotice(error.message));
  }
});

hydrateAuthTokensFromUrl();
