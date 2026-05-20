const state = {
  disputes: [],
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

async function loadDisputes() {
  const data = await request("/api/disputes");
  state.disputes = data.disputes;
  state.activeId = state.activeId || data.disputes[0]?.id;
  renderCaseList();
  if (state.activeId) await loadDetail(state.activeId);
}

async function loadDetail(id) {
  state.activeId = id;
  state.detail = await request(`/api/disputes/${id}`);
  renderCaseList();
  renderDetail();
}

function renderCaseList() {
  $("caseList").innerHTML = state.disputes
    .map(
      (item) => `
      <button class="case-card ${item.id === state.activeId ? "active" : ""}" data-id="${item.id}">
        <strong>${item.merchant_name}</strong>
        <span>${money(item.amount, item.currency)} · ${item.issuer_name}</span>
      </button>
    `
    )
    .join("");
  document.querySelectorAll(".case-card").forEach((button) => {
    button.addEventListener("click", () => loadDetail(button.dataset.id).catch((error) => showNotice(error.message)));
  });
}

function renderDetail() {
  const detail = state.detail;
  const dispute = detail.dispute;
  const packet = detail.packet;
  $("caseTitle").textContent = `${dispute.merchant_name} · ${detail.plan.label}`;
  $("disputeSummary").innerHTML = [
    ["Amount", money(dispute.amount, dispute.currency)],
    ["Charge date", dispute.charge_date],
    ["Issuer", dispute.issuer_name],
    ["Status", dispute.status],
    ["Summary", dispute.user_summary || "No summary entered"],
  ]
    .map(([label, value]) => `<div class="meta-row"><span>${label}</span><strong>${value}</strong></div>`)
    .join("");
  $("guidance").textContent = detail.plan.careful_guidance;
  $("readiness").textContent = detail.export_reason;
  $("exportBtn").href = `/api/disputes/${dispute.id}/export`;
  $("exportBtn").classList.toggle("disabled", !detail.export_ready);
  renderChecklist(detail.plan.checklist);
  renderGaps(detail.evidence_gaps);
  renderTimeline(detail.timeline);
  renderPacket(packet);

  if (packet?.validation_errors?.length) {
    showNotice(`Packet validation blocked export: ${packet.validation_errors.join("; ")}`);
  } else if (detail.evidence_gaps.some((gap) => gap.severity === "high")) {
    showNotice("This packet has important evidence gaps. Add evidence before exporting.");
  } else {
    showNotice("");
  }
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
      <h4>Next Steps</h4>
      ${packet.next_steps.map((step) => `<div class="step">${step}</div>`).join("")}
    </div>
    <div class="full muted">${packet.disclaimer}</div>
  `;
}

function toggleNewCase() {
  $("newCasePanel").classList.toggle("hidden");
}

async function createCase(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const body = Object.fromEntries(form.entries());
  const detail = await request("/api/disputes", { method: "POST", body: JSON.stringify(body) });
  state.activeId = detail.dispute.id;
  $("newCaseForm").reset();
  $("newCasePanel").classList.add("hidden");
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
  renderDetail();
}

async function generatePacket() {
  state.detail = await request(`/api/disputes/${state.activeId}/generate`, { method: "POST", body: "{}" });
  renderDetail();
}

$("newCaseBtn").addEventListener("click", toggleNewCase);
$("newCaseForm").addEventListener("submit", (event) => createCase(event).catch((error) => showNotice(error.message)));
$("evidenceForm").addEventListener("submit", (event) => addEvidence(event).catch((error) => showNotice(error.message)));
$("generateBtn").addEventListener("click", () => generatePacket().catch((error) => showNotice(error.message)));

loadDisputes().catch((error) => showNotice(error.message));

