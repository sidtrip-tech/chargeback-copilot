# Chargeback Copilot PRD

## 1. Overview

Chargeback Copilot is a consumer-facing assistant that helps people prepare legitimate payment dispute packets for their bank or card issuer. It guides users through the chargeback preparation process, helps them organize evidence, identifies missing support, and generates a bank-ready packet with cited claims and next steps.

The product is a careful helper, not an aggressive claims engine. It should help consumers understand whether they have enough evidence, present their case clearly, and avoid unsupported or misleading statements. It must not promise outcomes, provide legal advice, encourage false disputes, or help users bypass valid merchant policies.

### MVP Thesis

Consumers often know something went wrong with a charge, subscription, delivery, cancellation, or refund, but they do not know what evidence their bank needs. The MVP should reduce confusion and preparation time by turning scattered receipts, emails, screenshots, tracking details, and notes into a structured dispute packet.

### Public Page Goal

The public page should optimize for **educate + convert**. It must explain what Chargeback Copilot does, when it is appropriate to use, what evidence consumers need, and what the product will not do. The goal is to help legitimate users self-select into packet preparation while discouraging fabricated, exaggerated, or unsupported disputes.

## 2. Problem

When consumers dispute a card charge, they are usually forced into a confusing process across their bank app, merchant support, email inbox, receipts, screenshots, and memory. Many legitimate disputes are weakly documented because consumers do not know what matters.

Common consumer problems:

- They do not know which dispute reason fits their situation.
- They are unsure whether to contact the merchant first.
- They cannot tell which receipts, emails, tracking records, screenshots, or cancellation confirmations matter.
- They struggle to explain events in a clear timeline.
- They submit unsupported claims or omit important facts.
- They miss issuer deadlines or fail to respond to follow-up requests.

Job to be done:

> When I believe a card charge is wrong, I need to understand my options, collect the right evidence, and prepare a clear dispute packet for my bank without overstating my case or missing important details.

## 3. Users And Personas

### Primary Persona: Everyday Cardholder

An individual consumer who notices a confusing, unauthorized, undelivered, or unresolved charge. They may be unfamiliar with chargebacks and want a calm guide that explains what to collect and how to describe the issue.

Success looks like:

- Understands the likely dispute category.
- Collects the evidence their issuer is likely to ask for.
- Exports a clear, concise packet.
- Knows the next step to take with their bank or merchant.

### Secondary Persona: Busy Subscription Manager

A consumer managing multiple subscriptions, renewals, trials, cancellations, and refund requests. They need help reconstructing dates, terms, cancellation attempts, and merchant communications.

Success looks like:

- Builds a timeline of signup, renewal, cancellation, and refund events.
- Flags missing cancellation or refund evidence.
- Generates a neutral dispute explanation.

### Excluded / Unsupported User

A user attempting to fabricate claims, hide relevant facts, bypass valid merchant terms, or file disputes they know are false. The product should refuse or redirect when a user asks for help creating unsupported or misleading claims.

## 4. Product Positioning

Chargeback Copilot should be positioned as a careful consumer preparation tool.

It should:

- Help users prepare legitimate disputes.
- Ask clarifying questions before drafting.
- Cite every factual claim to user-provided evidence.
- Surface weak spots and missing evidence.
- Encourage merchant resolution when appropriate.
- Use plain language and avoid legal jargon.

It should not:

- Guarantee a refund or dispute win.
- Give legal or financial advice.
- Submit claims directly to banks in v1.
- Encourage friendly fraud or unsupported chargebacks.
- Draft accusations that are not supported by evidence.

## 5. MVP Scope: Prepare Packet

The MVP focuses on helping a consumer prepare a bank-ready dispute packet. It does not submit directly to a card issuer or merchant.

### In Scope

- Public education/conversion page
- Prototype login gate into a private workspace
- Private dashboard with In Progress, Completed, and Start New Packet tabs
- Guided dispute intake
- Reason/category selection
- Evidence checklist
- Evidence upload or manual evidence entry
- Timeline builder
- Claim strength and gap review
- Readiness score and evidence progress
- Cited dispute explanation
- Bank-ready packet export
- Next-step checklist
- Real-life outcome feedback for completed packets

### Out Of Scope For MVP

- Direct bank or card-network submission
- Real-time bank account integration
- Merchant negotiation automation
- Legal advice or regulatory interpretation
- Outcome prediction guarantees
- Multi-user household workflows
- Paid subscription management automation

### Path To Production

The MVP should remain focused on workflow validation, but production readiness requires a separate implementation track:

- Real authentication and user-owned packet boundaries.
- Managed Postgres with schema migrations.
- Secure object storage for uploaded evidence files.
- Background processing for file scanning, OCR, PDF export, and optional AI work.
- Stronger citation validation before export.
- Privacy, terms, consent, audit logs, data deletion/export support, and operational monitoring.

The detailed phased plan is maintained in [Production Roadmap](production-roadmap.md).

## 6. Core User Flow

### 0. Learn On Public Page

The user first sees a public page that explains:

- Chargeback Copilot helps prepare dispute packets.
- The product is for legitimate disputes only.
- Useful evidence includes receipts, emails, chats, screenshots, tracking details, cancellation confirmations, and issuer messages.
- The product does not provide legal advice, financial advice, direct bank submission, or outcome guarantees.

The primary call to action is **Start preparing a packet**.

### 0.5. Prototype Login

For the MVP, login is a prototype gate rather than real authentication. Selecting the public-page call to action takes the user into the private workspace with a clear explanation that no real account or password is being used in the prototype.

### 1. Start Dispute

Inside the private workspace, the user can select **Start New Packet** and enter:

- Merchant name
- Charge amount
- Charge date
- Card issuer or bank name
- Current status, such as not contacted merchant, contacted merchant, refund denied, or bank already contacted

### 2. Answer Guided Questions

The product asks plain-language questions to identify the most likely dispute category:

- I do not recognize this charge.
- I canceled but was still charged.
- I did not receive the item or service.
- The item or service was not as described.
- I was promised a refund but did not receive it.
- I was charged the wrong amount.

The product should explain that the category is a preparation aid, not a final legal or issuer classification.

### 3. Build Evidence Checklist

Based on the selected category, the product generates a checklist of useful evidence.

Examples:

- Unauthorized charge: transaction details, card possession status, merchant relationship, account access history, bank alerts.
- Canceled subscription: cancellation confirmation, terms shown at signup, renewal notice, billing descriptor, merchant response.
- Not received: order confirmation, tracking details, delivery status, merchant communications, promised delivery date.
- Refund not received: refund promise, return proof, merchant acknowledgement, timeline since refund approval.

### 4. Upload Or Enter Evidence

The user can upload or manually enter evidence artifacts:

- Receipts
- Emails
- Chat transcripts
- Screenshots
- Tracking records
- Cancellation confirmations
- Refund promises
- Bank or merchant messages

Each artifact should store its source, date, type, and short summary.

### 5. Build Timeline

The product turns evidence into a chronological timeline. The user can edit dates, add missing events, or remove irrelevant items.

The timeline should clearly separate:

- User-entered facts
- Evidence-backed facts
- Missing or uncertain facts

### 6. Review Evidence Gaps

Before generation, the product flags missing or weak evidence. Examples:

- No proof of cancellation found.
- No merchant contact attempt recorded.
- No tracking or delivery status provided.
- Refund promise is mentioned but not evidenced.
- Charge was recognized, but the reason for dispute is unclear.

The user can continue with gaps, but the packet should label weak areas rather than invent support.

### 7. Generate Dispute Packet

The product generates a concise packet with:

- Dispute summary
- Chronological timeline
- Cited factual claims
- Evidence index
- Suggested bank message
- Next-step checklist

Every factual claim must cite one or more evidence artifacts. If evidence is missing, the packet should say what is missing instead of filling the gap.

### 8. Export

The user exports the packet as Markdown, HTML, or PDF-ready content. The MVP does not submit the dispute directly.

### 9. Record Outcome Feedback

After a completed/export-ready packet has been submitted through the user's official issuer channel, the user can record the real-life result:

- Pending
- Success
- Failure

The user may add an optional note about what happened. Outcome feedback is for personal tracking and future product learning only. It must not be shown as a prediction, guarantee, or advice.

## 7. Functional Requirements

### Dispute Intake

- Create a consumer dispute packet.
- Capture basic charge, merchant, and issuer information.
- Allow users to update dispute status and notes.

### Public Page And Prototype Login

- Show a public education/conversion page before the private workspace.
- Explain legitimate use, evidence needs, and safety boundaries.
- Provide a prototype login/start CTA that enters the private workspace without real authentication.
- Do not imply that using the product guarantees a refund or issuer success.

### Private Dashboard

- Show dashboard tabs for In Progress, Completed, and Start New Packet.
- Derive packet status from readiness and packet validation:
  - In Progress: missing required evidence, no generated packet, blocked packet, or draft state.
  - Completed: generated packet with no validation errors and no high-severity gaps.
- Optimize each status for a different user job:
  - In Progress: prepare, add evidence, fix gaps, and generate a packet.
  - Completed: export the packet, track issuer outcome, and optionally audit details.
  - Start New Packet: complete guided intake with minimal distraction.
- Optimize Start New Packet for guided confidence:
  - Use a two-step intake.
  - Step 1 asks the user to choose their situation using plain-language category cards.
  - Step 2 asks for only the required charge details and a short factual summary.
  - Show a short evidence preview after category selection with 3-4 likely evidence items.
  - Explain that users do not need all evidence before creating the packet.
  - Do not save a partial packet after category selection in v1; create the packet only after Step 2 submission.
  - Route the newly created packet into In Progress.
- Optimize In Progress around **Next Best Action**:
  - Show readiness and the top missing evidence item first.
  - List high-priority gaps before lower-priority supporting detail.
  - Provide contextual `Add this evidence` actions from missing-evidence cards.
  - Preselect the likely evidence type when a user chooses a contextual add action.
  - Keep manual evidence entry available for evidence that does not map to a listed gap.
  - Keep Generate visible even below 100% readiness, with clear copy that export may remain blocked until required evidence and validation pass.
  - Move checklist, timeline, generated draft, and category guidance into optional review sections.
- Show dashboard summary metrics that change by selected tab:
  - In Progress: in-progress packets, high-priority gaps, average readiness, ready to generate.
  - Completed: completed packets, reported success, reported failure, pending outcome.
  - Start New Packet: total packets created, in progress, completed, and next step.
- Include short captions on metric cards so users understand why the number matters.
- Show readiness score based on required checklist completion.
- Show evidence progress as satisfied required items out of total required items.
- Reduce cognitive load in Completed by hiding preparation-heavy sections by default. Supporting details such as cited claims, evidence timeline, packet summary, and checklist should be available through collapsible audit sections rather than always visible.

### Reason Selection

- Support first-pass categories for unauthorized charge, canceled subscription, not received, not as described, refund not received, and wrong amount.
- Provide plain-language examples for each category.
- Allow users to change the category before export.

### Evidence Management

- Support manual evidence entry in MVP.
- Upload support should preserve file name, date, source, content type, size, storage key, scan status, and user-written summary.
- Uploaded files should be downloadable and deletable only by the account owner.
- Allow users to mark evidence as relevant, uncertain, or excluded.

### Timeline Builder

- Sort evidence and user events chronologically.
- Allow timeline editing.
- Preserve source links from timeline events to evidence artifacts.

### Packet Generation

- Generate packet content using deterministic templates by default.
- Support optional AI generation later, with template fallback.
- Require citations for every factual claim.
- Refuse unsupported claims or mark them as evidence gaps.

### Evidence Gap Detection

- Compare category requirements against available evidence.
- Flag high-priority missing evidence before export.
- Use consumer-safe language: "This may be useful to add" rather than "You will lose without this."

### Export

- Export bank-ready packet as Markdown or HTML in MVP.
- Include evidence index and citation IDs.
- Include a disclaimer that the packet is preparation support, not legal or financial advice.

### Outcome Feedback

- Allow outcome feedback only for completed/export-ready packets.
- Support feedback values: pending, success, and failure.
- Support an optional user note describing the real-life issuer update.
- Show outcome status on completed packet cards and packet detail.
- Treat feedback as tracking data, not prediction, advice, or proof of product efficacy.
- In Completed, make outcome feedback the primary post-export interaction alongside the export action.

## 8. AI And Guardrails

AI generation is optional and should not be required for the MVP to function.

Required guardrails:

- Use only user-provided dispute details and evidence artifacts.
- Cite every factual claim.
- Avoid unsupported accusations.
- Avoid legal advice.
- Avoid guarantees about chargeback outcomes.
- Flag weak cases and missing evidence.
- Refuse requests to fabricate receipts, alter facts, or hide relevant information.

If the AI output contains uncited or unsupported factual claims, the validator should block export or require user revision.

## 9. Data Concepts

### Consumer Dispute

Represents a user's dispute preparation case.

Key fields:

- ID
- merchant name
- charge amount
- charge date
- issuer name
- dispute category
- status
- user summary
- created and updated timestamps

### Evidence Artifact

Represents an uploaded or manually entered source.

Key fields:

- ID
- dispute ID
- type
- title
- source
- occurred date
- summary
- file reference or text content
- relevance status

### Timeline Event

Represents a chronological event in the dispute story.

Key fields:

- ID
- dispute ID
- date
- title
- description
- linked evidence artifact IDs
- confidence or support status

### Cited Claim

Represents a factual statement in the packet.

Key fields:

- ID
- text
- citation evidence IDs
- support status

### Evidence Gap

Represents missing or weak support.

Key fields:

- ID
- dispute ID
- category requirement
- severity
- explanation
- suggested user action

### Packet Export

Represents generated content for user review and download.

Key fields:

- ID
- dispute ID
- format
- packet sections
- validation status
- created timestamp

### Outcome Feedback

Represents a user's real-life update after submitting a completed packet through their official issuer channel.

Key fields:

- dispute ID
- outcome: pending, success, or failure
- optional note
- updated timestamp

## 10. Success Metrics

### North Star Metric

Completed legitimate dispute packets per month.

### Primary Metrics

- Packet completion rate
- Average time to prepare packet
- Percent of packets with complete evidence checklists
- Percent of generated claims with valid citations
- User-reported confidence after packet preparation
- In-progress to completed packet conversion rate
- Completed packets with outcome feedback submitted

### Guardrail Metrics

- Unsupported claim rate
- AI refusal or safety intervention rate
- Evidence gap acknowledgement rate
- User confusion reports
- Complaint rate around misleading or overly aggressive language
- Outcome feedback misuse reports, such as interpreting results as guarantees or predictions

## 11. Responsible AI And Compliance Considerations

Chargeback Copilot handles sensitive financial and consumer information. The product must use a privacy-preserving design and clear boundaries.

Privacy requirements:

- Minimize collected data.
- Do not require full card numbers.
- Avoid storing unnecessary bank credentials.
- Clearly explain what user data is used for.
- Do not train models on user evidence without explicit consent.
- Support user data export and deletion for stored packet data.

Safety requirements:

- Include clear disclaimers that the tool is not legal, financial, or banking advice.
- Avoid promising outcomes.
- Refuse fabricated or misleading claim requests.
- Encourage contacting the merchant when appropriate.
- Preserve user control over final packet wording.

Fairness requirements:

- Use plain-language flows accessible to non-experts.
- Avoid assuming a user understands chargeback categories.
- Support common consumer situations without shaming or blaming users.

## 12. Launch Plan

### Internal Prototype

Use synthetic disputes to test the intake flow, checklist logic, gap detection, packet generation, and citation validation.

Exit criteria:

- 100% of generated factual claims have citations.
- At least one sample case exports cleanly.
- At least one weak case surfaces meaningful evidence gaps.

### Private Beta

Invite a small group of users to prepare packets using their own redacted dispute examples or synthetic examples.

Exit criteria:

- Users can complete a packet without support.
- Users understand that the tool does not guarantee outcomes.
- No observed cases of unsupported AI-generated claims passing validation.

### Public MVP

Launch with a public education/conversion page, prototype private workspace, manual export, clear disclaimers, outcome feedback tracking, and no direct bank submission.

Exit criteria:

- Stable packet completion rate.
- Low confusion reports.
- No material safety issues around false or unsupported claims.
- Users understand that outcome feedback is tracking only, not advice or prediction.

### Production Build

After the public MVP validates the core workflow, the product should move through a production build before handling real sensitive user evidence at scale.

Phases:

- Production Foundation: real backend framework, Postgres, migrations, authentication, session security, and user-owned packets.
- Evidence And Export: secure uploads, object storage, virus scanning, previews, delete controls, OCR where useful, and PDF export.
- AI-Assisted Preparation: optional citation-validated AI drafting, OCR/summarization, safety refusals, and deterministic template fallback.
- Compliance And Launch Readiness: privacy/security review, audit logs, user data export/deletion support, analytics, monitoring, backups, support flows, staging, and production deployment.

Exit criteria:

- Users can only access their own packets and evidence.
- Local authentication supports email verification and password reset flows, or a hosted auth provider replaces local auth.
- Uploaded files are validated, scanned, encrypted, and deletable.
- Full card numbers are never collected.
- Final export is blocked for unsupported claims or unresolved high-priority requirements.
- Privacy, terms, consent, monitoring, backups, and incident response basics are in place.

Current foundation work has begun with local session-based access, user-owned packet records, protected APIs, audit-log storage, email verification/password reset token flows, Postgres, and S3-backed uploads. This is a stepping stone toward hosted auth or configured transactional email, managed scanning, monitoring, and broader production operations, not a substitute for the full production build.

## 13. Open Questions

- Should the product require users to confirm they are submitting truthful information before export?
- Should weak cases be exportable with warnings, or should high-severity gaps block export?
- Should the MVP support file uploads immediately, or start with manual evidence entry first?
- Should the product include merchant-contact templates before recommending bank dispute preparation?
- Should the first version support only credit cards, or debit card disputes as well?
- Should outcome feedback be used only for user-visible tracking in v1, or later feed aggregate product analytics?
- Should completed packets remain editable after a user records success/failure?

## 14. Acceptance Criteria

- The PRD clearly describes a consumer-side product and does not depend on merchant representment workflows.
- The MVP scope is limited to preparing and exporting a dispute packet.
- Every generated factual claim must be backed by user-entered or uploaded evidence.
- Weak or unsupported cases are represented as evidence gaps.
- The product avoids legal advice, financial advice, guaranteed outcomes, and fabricated claims.
- Direct bank submission is explicitly out of scope for v1.
- Public page explains legitimate use, evidence needs, and product limitations.
- Prototype login clearly separates public and private experiences without implying real account security.
- Private workspace includes In Progress, Completed, and Start New Packet tabs.
- Completed packets allow users to record pending, success, or failure outcome feedback.
- Completed packet detail prioritizes export and outcome tracking, with evidence, timeline, checklist, and claims behind collapsible audit sections.
- Add Evidence is visible for In Progress packets and hidden for Completed packets.
- In Progress shows next best action, contextual missing-evidence cards, readiness progress, and Generate before optional review details.
- In Progress contextual `Add this evidence` actions preselect the likely evidence type.
- In Progress keeps Generate visible below 100% readiness and explains that the draft may remain blocked from export.
- Start New Packet uses two-step guided intake, category cards, and evidence preview before packet creation.
- Start New Packet does not create or save partial drafts before required charge details are submitted.
- Dashboard number cards are contextual by tab and do not show the same global metrics across all statuses.
- Outcome feedback is absent from In Progress and available only for Completed packets.
- Outcome feedback is never represented as prediction, guarantee, legal advice, financial advice, or issuer guidance.
- Production roadmap exists and describes authentication, user data boundaries, Postgres, secure evidence uploads, object storage, background jobs, PDF export, compliance, monitoring, deployment, and test strategy.
- Production build remains preparation/export only and does not introduce direct bank submission.
