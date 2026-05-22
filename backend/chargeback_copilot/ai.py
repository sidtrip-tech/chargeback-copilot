import json
import os
from datetime import datetime, timezone
from typing import List
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from .models import CitedClaim, ConsumerDispute, EvidenceArtifact, Packet
from .packets import DISCLAIMER
from .planning import find_gaps, get_plan
from .timeline import build_timeline
from .validation import validate_claims


OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.2")
AI_ENABLED = os.environ.get("AI_ENABLED", "false").lower() in {"1", "true", "yes"}
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ai_available() -> bool:
    return AI_ENABLED and bool(OPENAI_API_KEY)


def _schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["title", "summary", "suggested_bank_message", "claims", "next_steps"],
        "properties": {
            "title": {"type": "string"},
            "summary": {"type": "string"},
            "suggested_bank_message": {"type": "string"},
            "claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["id", "text", "citation_evidence_ids"],
                    "properties": {
                        "id": {"type": "string"},
                        "text": {"type": "string"},
                        "citation_evidence_ids": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
            "next_steps": {"type": "array", "items": {"type": "string"}},
        },
    }


def _evidence_payload(artifacts: List[EvidenceArtifact]) -> list[dict]:
    return [
        {
            "id": item.id,
            "type": item.type,
            "title": item.title,
            "source": item.source,
            "occurred_at": item.occurred_at,
            "summary": item.summary,
            "relevance": item.relevance,
        }
        for item in artifacts
        if item.relevance != "excluded"
    ]


def _extract_output_json(response: dict) -> dict:
    if response.get("output_text"):
        return json.loads(response["output_text"])
    text_parts: list[str] = []
    for output in response.get("output", []):
        if output.get("type") != "message":
            continue
        for content in output.get("content", []):
            if content.get("type") == "output_text":
                text_parts.append(content.get("text", ""))
            if content.get("type") == "refusal":
                raise RuntimeError(content.get("refusal") or "AI generation was refused.")
    if not text_parts:
        raise RuntimeError("AI generation returned no text output.")
    return json.loads("".join(text_parts))


def _call_openai(payload: dict) -> dict:
    request = Request(
        OPENAI_RESPONSES_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI request failed with HTTP {exc.code}: {body}") from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f"OpenAI request failed: {exc}") from exc


def generate_live_ai_packet(dispute: ConsumerDispute, artifacts: List[EvidenceArtifact]) -> Packet:
    if not ai_available():
        raise RuntimeError("AI generation is not configured.")

    plan = get_plan(dispute.category)
    gaps = find_gaps(plan, artifacts)
    timeline = build_timeline(artifacts)
    evidence_ids = {item.id for item in artifacts if item.relevance != "excluded"}
    prompt_payload = {
        "dispute": {
            "id": dispute.id,
            "merchant_name": dispute.merchant_name,
            "amount_cents": dispute.amount,
            "currency": dispute.currency,
            "charge_date": dispute.charge_date,
            "issuer_name": dispute.issuer_name,
            "category": dispute.category,
            "user_summary": dispute.user_summary,
        },
        "strategy": {
            "label": plan.label,
            "description": plan.description,
            "careful_guidance": plan.careful_guidance,
        },
        "evidence": _evidence_payload(artifacts),
        "evidence_gaps": [
            {
                "label": gap.label,
                "severity": gap.severity,
                "explanation": gap.explanation,
                "suggested_action": gap.suggested_action,
            }
            for gap in gaps
        ],
    }
    response = _call_openai(
        {
            "model": OPENAI_MODEL,
            "instructions": (
                "You draft careful consumer card-dispute packets. Use only the provided dispute and evidence JSON. "
                "Do not invent facts, dates, policies, bank rules, or outcomes. Do not give legal or financial advice. "
                "Every factual claim must cite one or more provided evidence IDs. If evidence is weak or missing, omit the claim "
                "and mention the gap in next_steps instead. Keep the bank message concise and factual."
            ),
            "input": json.dumps(prompt_payload, sort_keys=True),
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "chargeback_packet",
                    "strict": True,
                    "schema": _schema(),
                }
            },
        }
    )
    output = _extract_output_json(response)
    claims = [
        CitedClaim(
            id=str(item.get("id") or f"claim_ai_{index + 1}"),
            text=str(item.get("text", "")).strip(),
            citation_evidence_ids=[evidence_id for evidence_id in item.get("citation_evidence_ids", []) if evidence_id in evidence_ids],
        )
        for index, item in enumerate(output.get("claims", []))
        if str(item.get("text", "")).strip()
    ]
    validation_errors = validate_claims(claims, artifacts)
    has_high_gaps = any(gap.severity == "high" for gap in gaps)
    status = "blocked" if validation_errors or has_high_gaps else "ready"
    return Packet(
        id=f"pkt_{uuid4().hex[:12]}",
        dispute_id=dispute.id,
        title=str(output.get("title") or f"Dispute Packet: {dispute.merchant_name}"),
        summary=str(output.get("summary") or "AI-generated packet draft with cited claims."),
        suggested_bank_message=str(output.get("suggested_bank_message") or ""),
        claims=claims,
        timeline=timeline,
        evidence_gaps=gaps,
        next_steps=[str(step) for step in output.get("next_steps", [])],
        validation_errors=validation_errors,
        status=status,
        created_at=utc_now(),
        disclaimer=DISCLAIMER,
        mode="live_ai",
    )
