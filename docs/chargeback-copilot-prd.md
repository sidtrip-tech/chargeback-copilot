# Chargeback Copilot PRD

## 1. Overview

Chargeback Copilot is a consumer-facing assistant that helps people prepare legitimate payment dispute packets for their bank or card issuer. It guides users through the chargeback preparation process, helps them organize evidence, identifies missing support, and generates a bank-ready packet with cited claims and next steps.

The product is a careful helper, not an aggressive claims engine. It should help consumers understand whether they have enough evidence, present their case clearly, and avoid unsupported or misleading statements. It must not promise outcomes, provide legal advice, encourage false disputes, or help users bypass valid merchant policies.

### MVP Thesis

Consumers often know something went wrong with a charge, subscription, delivery, cancellation, or refund, but they do not know what evidence their bank needs. The MVP should reduce confusion and preparation time by turning scattered receipts, emails, screenshots, tracking details, and notes into a structured dispute packet.

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

- Guided dispute intake
- Reason/category selection
- Evidence checklist
- Evidence upload or manual evidence entry
- Timeline builder
- Claim strength and gap review
- Cited dispute explanation
- Bank-ready packet export
- Next-step checklist

### Out Of Scope For MVP

- Direct bank or card-network submission
- Real-time bank account integration
- Merchant negotiation automation
- Legal advice or regulatory interpretation
- Outcome prediction guarantees
- Multi-user household workflows
- Paid subscription management automation

## 6. Core User Flow

### 1. Start Dispute

The user starts a new dispute packet and enters:

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

## 7. Functional Requirements

### Dispute Intake

- Create a consumer dispute packet.
- Capture basic charge, merchant, and issuer information.
- Allow users to update dispute status and notes.

### Reason Selection

- Support first-pass categories for unauthorized charge, canceled subscription, not received, not as described, refund not received, and wrong amount.
- Provide plain-language examples for each category.
- Allow users to change the category before export.

### Evidence Management

- Support manual evidence entry in MVP.
- Future upload support should preserve file name, date, source, and user-written summary.
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

## 10. Success Metrics

### North Star Metric

Completed legitimate dispute packets per month.

### Primary Metrics

- Packet completion rate
- Average time to prepare packet
- Percent of packets with complete evidence checklists
- Percent of generated claims with valid citations
- User-reported confidence after packet preparation

### Guardrail Metrics

- Unsupported claim rate
- AI refusal or safety intervention rate
- Evidence gap acknowledgement rate
- User confusion reports
- Complaint rate around misleading or overly aggressive language

## 11. Responsible AI And Compliance Considerations

Chargeback Copilot handles sensitive financial and consumer information. The product must use a privacy-preserving design and clear boundaries.

Privacy requirements:

- Minimize collected data.
- Do not require full card numbers.
- Avoid storing unnecessary bank credentials.
- Clearly explain what user data is used for.
- Do not train models on user evidence without explicit consent.

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

Launch with manual export, clear disclaimers, and no direct bank submission.

Exit criteria:

- Stable packet completion rate.
- Low confusion reports.
- No material safety issues around false or unsupported claims.

## 13. Open Questions

- Should the product require users to confirm they are submitting truthful information before export?
- Should weak cases be exportable with warnings, or should high-severity gaps block export?
- Should the MVP support file uploads immediately, or start with manual evidence entry first?
- Should the product include merchant-contact templates before recommending bank dispute preparation?
- Should the first version support only credit cards, or debit card disputes as well?

## 14. Acceptance Criteria

- The PRD clearly describes a consumer-side product and does not depend on merchant representment workflows.
- The MVP scope is limited to preparing and exporting a dispute packet.
- Every generated factual claim must be backed by user-entered or uploaded evidence.
- Weak or unsupported cases are represented as evidence gaps.
- The product avoids legal advice, financial advice, guaranteed outcomes, and fabricated claims.
- Direct bank submission is explicitly out of scope for v1.
