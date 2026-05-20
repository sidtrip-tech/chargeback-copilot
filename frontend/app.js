const state = {
  authenticated: false,
  tab: "in_progress",
  disputes: [],
  summary: null,
  activeId: null,
  detail: null,
};

const $ = (id) => document.getElementById(id);

function money(cents, currency) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(cents / 100);
}

function showNotice(message) {
  const notice = $("notice");
  notice.textContent = message || "";
  notice.classList.toggle("hidden", !message);
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok || payload.error) throw new Error(payload.error || "Request failed");
  return payload;
}

function login() {
  state.authenticated = true;
  $("publicPage").classList.add("hidden");
  $("privateApp").classList.remove("hidden");
  loadDisputes().catch((error) => showNotice(error.message));
}

function logoutToPublic() {
  state.authenticated = false;
  $("privateApp").classList.add("hidden");
  $("publicPage").classList.remove("hidden");
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
  $("summaryCards").innerHTML = [
    ["Total packets", summary.total || 0],
    ["In progress", summary.in_progress || 0],
    ["Completed", summary.completed || 0],
    ["High-priority gaps", summary.high_gap || 0],
    ["Reported success", summary.reported_success || 0],
    ["Reported failure", summary.reported_failure || 0],
  ]
    .map(([label, value]) => `<article><span>${label}</span><strong>${value}</strong></article>`)
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
}

function renderEmptyDetail() {
  $("generateBtn").disabled = true;
  $("exportBtn").classList.add("disabled");
  $("disputeSummary").innerHTML = "";
  $("readinessPanel").innerHTML = "<p class='empty-state'>Select a packet to view details.</p>";
  $("guidance").textContent = "";
  $("checklist").innerHTML = "";
  $("gaps").innerHTML = "";
  $("timeline").innerHTML = "";
  $("nextSteps").innerHTML = "";
  $("outcomePanel").innerHTML = "";
  $("packetStatus").textContent = "";
  $("packet").className = "empty-state";
  $("packet").textContent = "Select a packet to view generated content.";
}

function renderDetail() {
  const detail = state.detail;
  const dispute = detail.dispute;
  const packet = detail.packet;
  $("generateBtn").disabled = false;
  $("exportBtn").href = `/api/disputes/${dispute.id}/export`;
  $("exportBtn").classList.toggle("disabled", !detail.export_ready);
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
  $("guidance").textContent = `${detail.plan.careful_guidance} Remember: this tool prepares information; it does not guarantee an issuer result.`;
  renderReadiness(detail);
  renderChecklist(detail.plan.checklist);
  renderGaps(detail.evidence_gaps);
  renderTimeline(detail.timeline);
  renderNextSteps(detail.next_steps);
  renderOutcome(detail);
  renderPacket(packet);

  if (packet?.validation_errors?.length) {
    showNotice(`Packet validation blocked export: ${packet.validation_errors.join("; ")}`);
  } else if (detail.evidence_gaps.some((gap) => gap.severity === "high")) {
    showNotice("This packet has important evidence gaps. Add evidence before exporting.");
  } else {
    showNotice("");
  }
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
  $("checklist").innerHTML = items
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
  $("gaps").innerHTML = gaps.length
    ? gaps
        .map(
          (gap) => `
      <div class="gap-item">
        <span class="pill ${gap.severity === "high" ? "danger" : "warn"}">${gap.severity}</span>
        <p><strong>${gap.label}</strong></p>
        <p>${gap.explanation}</p>
        <p class="muted">${gap.suggested_action}</p>
      </div>
    `
        )
        .join("")
    : `<p class="empty-state">No evidence gaps detected.</p>`;
}

function renderTimeline(events) {
  $("timeline").innerHTML = events.length
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

function renderOutcome(detail) {
  const disabled = detail.derived_status !== "completed";
  const outcome = detail.outcome_feedback || { outcome: "pending", note: "" };
  $("outcomePanel").innerHTML = `
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
  $("packet").innerHTML = `
    <div class="full">
      <p>${packet.summary}</p>
      <p><strong>Suggested bank message:</strong> ${packet.suggested_bank_message}</p>
    </div>
    <div>
      <h4>Cited Claims</h4>
      ${packet.claims
        .map(
          (claim) => `
        <div class="claim">
          <p>${claim.text}</p>
          <div class="citations">Evidence: ${claim.citation_evidence_ids.join(", ")}</div>
        </div>`
        )
        .join("") || '<p class="empty-state">No supported claims yet.</p>'}
    </div>
    <div>
      <h4>Packet Safety</h4>
      <div class="step">${packet.disclaimer}</div>
      <div class="step">Every factual claim above includes evidence citations.</div>
    </div>
  `;
}

async function createCase(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const body = Object.fromEntries(form.entries());
  const detail = await request("/api/disputes", { method: "POST", body: JSON.stringify(body) });
  state.tab = "in_progress";
  state.activeId = detail.dispute.id;
  event.currentTarget.reset();
  $("startNewView").classList.add("hidden");
  $("dashboardView").classList.remove("hidden");
  await loadDisputes();
}

async function addEvidence(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const body = Object.fromEntries(form.entries());
  state.detail = await request(`/api/disputes/${state.activeId}/evidence`, {
    method: "POST",
    body: JSON.stringify(body),
  });
  event.currentTarget.reset();
  await loadDisputes();
}

async function generatePacket() {
  if (!state.activeId) return;
  state.detail = await request(`/api/disputes/${state.activeId}/generate`, { method: "POST", body: "{}" });
  await loadDisputes();
  if (state.detail.derived_status === "completed") {
    state.tab = "completed";
    await loadDisputes();
  }
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

document.querySelectorAll(".loginCta").forEach((button) => button.addEventListener("click", login));
$("backToPublicBtn").addEventListener("click", logoutToPublic);
document.querySelectorAll(".tab").forEach((button) => button.addEventListener("click", () => setTab(button.dataset.tab)));
$("newCaseForm").addEventListener("submit", (event) => createCase(event).catch((error) => showNotice(error.message)));
$("evidenceForm").addEventListener("submit", (event) => addEvidence(event).catch((error) => showNotice(error.message)));
$("generateBtn").addEventListener("click", () => generatePacket().catch((error) => showNotice(error.message)));
